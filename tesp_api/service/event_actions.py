import os
import datetime
from typing import List
from pathlib import Path
import asyncio

from pymonad.maybe import Just, Nothing 
from bson.objectid import ObjectId
from pymonad.promise import Promise, _Promise

from tesp_api.utils.docker import (
    docker_run_command,
    docker_stage_in_command,
    docker_stage_out_command,
    map_volumes
)
from tesp_api.utils.singularity import (
    singularity_run_command,
    singularity_stage_in_command,
    singularity_stage_out_command
)
from tesp_api.service.pulsar_service import pulsar_service
from tesp_api.service.event_dispatcher import dispatch_event
from tesp_api.utils.functional import get_else_throw, maybe_of 
from tesp_api.service.event_handler import Event, local_handler
from tesp_api.repository.task_repository import task_repository
from tesp_api.service.file_transfer_service import file_transfer_service
from tesp_api.service.error import pulsar_event_handle_error, TaskNotFoundError, TaskExecutorError
from tesp_api.service.pulsar_operations import PulsarRestOperations, PulsarAmpqOperations, DataType
from tesp_api.repository.task_repository_utils import append_task_executor_logs, update_last_task_log_time
from tesp_api.repository.model.task import (
    TesTaskState,
    TesTaskExecutor,
    TesTaskResources,
    TesTaskInput,
    TesTaskOutput
)
CONTAINER_TYPE = os.getenv("CONTAINER_TYPE", "both") # change both to docker only?

@local_handler.register(event_name="queued_task")
def handle_queued_task(event: Event) -> None:
    event_name, payload = event
    print("Queued task:")
    print(payload)
    match pulsar_service.get_operations():
        case PulsarRestOperations() as pulsar_rest_operations:
            dispatch_event('queued_task_rest', {**payload, 'pulsar_operations': pulsar_rest_operations})
        case PulsarAmpqOperations() as pulsar_ampq_operations:
            dispatch_event('queued_task_ampq', {**payload, 'pulsar_operations': pulsar_ampq_operations})

@local_handler.register(event_name="queued_task_rest")
async def handle_queued_task_rest(event: Event):
    event_name, payload = event
    task_id: ObjectId = payload['task_id']
    pulsar_operations: PulsarRestOperations = payload['pulsar_operations']

    print("Queued task rest:")
    print(payload)

    await Promise(lambda resolve, reject: resolve(None))\
        .then(lambda nothing: pulsar_operations.setup_job(task_id))\
        .map(lambda setup_job_result: dispatch_event('initialize_task', {**payload, 'task_config': setup_job_result}))\
        .catch(lambda error: pulsar_event_handle_error(error, payload['task_id'], event_name, pulsar_operations))\
        .then(lambda x: x)


@local_handler.register(event_name="initialize_task")
async def handle_initializing_task(event: Event) -> None:
    event_name, payload = event
    task_id: ObjectId = payload['task_id']
    pulsar_operations: PulsarRestOperations = payload['pulsar_operations']

    async def setup_data(job_id: ObjectId,
            resources: TesTaskResources,
            volumes: List[str],
            inputs: List[TesTaskInput],
            outputs: List[TesTaskOutput]):
        resource_conf: dict
        volume_confs: List[dict] = []
        input_confs: List[dict] = []
        output_confs: List[dict] = []

        resource_conf = ({
            'cpu_cores': resources.cpu_cores if resources else None,
            'ram_gb': resources.ram_gb if resources else None
        })

        print("Volumes:")
        print(volumes)
        output_confs_mapped, volume_confs_mapped = map_volumes(str(job_id), volumes, outputs)
        output_confs.extend(output_confs_mapped)
        volume_confs.extend(volume_confs_mapped)


        print(inputs)

        for i in range(0, len(inputs)):
            content = inputs[i].content
            pulsar_path = payload['task_config']['inputs_directory'] + f'/input_file_{i}'
            if content is not None and inputs[i].url is None:
                pulsar_path = await pulsar_operations.upload(
                    job_id, DataType.INPUT,
                    file_content=Just(content),
                    file_path=f'input_file_{i}')
            input_confs.append({'container_path': inputs[i].path, 'pulsar_path': pulsar_path, 'url':inputs[i].url})

        return resource_conf, volume_confs, input_confs, output_confs

    await Promise(lambda resolve, reject: resolve(None))\
        .then(lambda nothing: task_repository.update_task_state(
            task_id,
            TesTaskState.QUEUED,
            TesTaskState.INITIALIZING
        )).map(lambda updated_task: get_else_throw(
            updated_task, TaskNotFoundError(task_id, Just(TesTaskState.QUEUED))
        )).then(lambda updated_task: setup_data(
            task_id,
            maybe_of(updated_task.resources).maybe(None, lambda x: x),
            maybe_of(updated_task.volumes).maybe([], lambda x: x),
            maybe_of(updated_task.inputs).maybe([], lambda x: x),
            maybe_of(updated_task.outputs).maybe([], lambda x: x)
        )).map(lambda res_input_output_confs: dispatch_event('run_task', {
            **payload,
            'resource_conf': res_input_output_confs[0],
            'volume_confs': res_input_output_confs[1],
            'input_confs': res_input_output_confs[2],
            'output_confs': res_input_output_confs[3]
        })).catch(lambda error: pulsar_event_handle_error(error, task_id, event_name, pulsar_operations))\
        .then(lambda x: x)


@local_handler.register(event_name="run_task")
async def handle_run_task(event: Event) -> None:
    event_name, payload = event
    task_id: ObjectId = payload['task_id']
    author: str = payload['author']
    resource_conf: dict = payload['resource_conf']
    volume_confs: List[dict] = payload['volume_confs']
    input_confs: List[dict] = payload['input_confs']
    output_confs: List[dict] = payload['output_confs']
    pulsar_operations: PulsarRestOperations = payload['pulsar_operations']
    
    run_command_str = None 
    command_start_time = datetime.datetime.now(datetime.timezone.utc)
    # Flag to indicate if the main job logic completed without an exception during pulsar interaction
    job_logic_completed_normally = False


    try:
        # Initial state update to RUNNING
        task_monad_init = await task_repository.update_task_state(
            task_id,
            TesTaskState.INITIALIZING,
            TesTaskState.RUNNING
        )
        task = get_else_throw(task_monad_init, TaskNotFoundError(task_id, Just(TesTaskState.INITIALIZING)))

        # Check if task was cancelled between INITIALIZING and this point (quick cancel)
        # This check is early, before significant Pulsar interaction.
        current_task_after_init_monad = await task_repository.get_task(maybe_of(author), {'_id': task_id})
        current_task_after_init = get_else_throw(current_task_after_init_monad, TaskNotFoundError(task_id))
        if current_task_after_init.state == TesTaskState.CANCELED:
            print(f"Task {task_id} found CANCELED shortly after being set to RUNNING. Aborting handle_run_task early.")
            # The API cancel path should handle Pulsar cleanup.
            return


        await update_last_task_log_time(
            task_id,
            author,
            TesTaskState.RUNNING,
            start_time=Just(datetime.datetime.now(datetime.timezone.utc))
        )

        container_cmds = list()
        stage_in_mount = payload['task_config']['inputs_directory']
        stage_exec = TesTaskExecutor(image="willdockerhub/curl-wget:latest",
                                     command=[],
                                     workdir=Path("/downloads"))
        
        stage_in_command_str_val = None
        if CONTAINER_TYPE == "docker":
            stage_in_command_str_val = docker_stage_in_command(stage_exec, resource_conf, stage_in_mount, input_confs)
        elif CONTAINER_TYPE == "singularity":
            stage_exec.image = "docker://" + stage_exec.image
            stage_in_command_str_val = singularity_stage_in_command(stage_exec, resource_conf, stage_in_mount, input_confs)

        for i, executor in enumerate(task.executors):
            run_script_cmd_str, script_content = "", ""
            if CONTAINER_TYPE == "docker":
                run_script_cmd_str, script_content = docker_run_command(executor, task_id, resource_conf, volume_confs,
                                                                 input_confs, output_confs, stage_in_mount, i)
            elif CONTAINER_TYPE == "singularity":
                mount_job_dir = payload['task_config']['job_directory']
                run_script_cmd_str, script_content = singularity_run_command(executor, task_id, resource_conf, volume_confs,
                                                                 input_confs, output_confs, stage_in_mount, mount_job_dir, i)

            await pulsar_operations.upload(
                payload['task_id'], DataType.INPUT,
                file_content=Just(script_content),
                file_path=f'run_script_{i}.sh')
            container_cmds.append(run_script_cmd_str)
        
        stage_out_command_str_val = None
        if CONTAINER_TYPE == "docker":
            stage_out_command_str_val = docker_stage_out_command(stage_exec, resource_conf, output_confs, volume_confs)
        elif CONTAINER_TYPE == "singularity":
            mount_job_dir = payload['task_config']['job_directory']
            bind_mount = payload['task_config']['inputs_directory']
            stage_out_command_str_val = singularity_stage_out_command(stage_exec, resource_conf, bind_mount,
                                                              output_confs, volume_confs, mount_job_dir)

        executors_commands_joined_str = " && ".join(filter(None, container_cmds))
        
        command_list_for_join = [cmd for cmd in [stage_in_command_str_val, executors_commands_joined_str, stage_out_command_str_val] if cmd and cmd.strip()]
        if command_list_for_join:
            run_command_str = f"set -xe && {' && '.join(command_list_for_join)}"
        else:
            run_command_str = None

        command_start_time = datetime.datetime.now(datetime.timezone.utc)

        command_status: dict
        if run_command_str is None:
            print(f"Task {task_id} has no commands to run. Treating as successful no-op.")
            command_status = {'stdout': '', 'stderr': 'No commands to run.', 'returncode': 0}
        else:
            print(f"Running command for task {task_id}: {run_command_str}")
            await pulsar_operations.run_job(task_id, run_command_str)
            # This is the polling call
            command_status = await pulsar_operations.job_status_complete(str(task_id))

        # If we reach here, job_status_complete returned without an exception during its polling.
        job_logic_completed_normally = True 

        command_end_time = datetime.datetime.now(datetime.timezone.utc)
        await append_task_executor_logs(
            task_id,
            author,
            TesTaskState.RUNNING, # Log is associated with this phase
            command_start_time,
            command_end_time,
            command_status.get('stdout', ''),
            command_status.get('stderr', ''),
            command_status.get('returncode', -1)
        )

        # Check current task state from DB. It might have been changed to CANCELED 
        # by an external request while job_status_complete was polling or after it returned.
        current_task_monad = await task_repository.get_task(maybe_of(author), {'_id': task_id}) 
        current_task_obj = get_else_throw(current_task_monad, TaskNotFoundError(task_id)) 

        if current_task_obj.state == TesTaskState.CANCELED:
            print(f"Task {task_id} is in CANCELED state after job execution/polling. Aborting further state changes by handle_run_task.")
            # The API cancel path should have handled Pulsar erase.
            return 

        if command_status.get('returncode', -1) != 0:
            # Job failed, and it wasn't due to user cancellation (CANCELED state check passed)
            await task_repository.update_task_state(
                task_id,
                TesTaskState.RUNNING, # Expected from state
                TesTaskState.EXECUTOR_ERROR
            )
            # No need to raise TaskExecutorError here if we want the promise chain below to handle cleanup
            # pulsar_event_handle_error will be called by the .catch of the promise chain if this update fails
            # or if we want to centralize error handling.
            # For now, let the promise chain handle it for consistency.
            # However, to ensure Pulsar job erasure on executor error:
            print(f"Task {task_id} executor returned non-zero: {command_status.get('returncode', -1)}. Setting state to EXECUTOR_ERROR.")
            await pulsar_operations.erase_job(task_id) # Erase on executor error
            return # Stop further processing

        # If job completed successfully and was not cancelled:
        # Proceed to set state to COMPLETE and cleanup.
        await Promise(lambda resolve, reject: resolve(None)) \
            .then(lambda ignored: task_repository.update_task_state(
                task_id,
                TesTaskState.RUNNING, 
                TesTaskState.COMPLETE
            )) \
            .map(lambda task_after_complete_update: get_else_throw(
                task_after_complete_update, TaskNotFoundError(task_id, Just(TesTaskState.RUNNING))
            )) \
            .then(lambda ignored: pulsar_operations.erase_job(task_id)) \
            .catch(lambda error: pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)) \
            .then(lambda x: x)

    except asyncio.CancelledError:
        print(f"handle_run_task for task {task_id} was cancelled via asyncio.CancelledError.")
        await task_repository.update_task_state(task_id, None, TesTaskState.CANCELED)
        # Ensure Pulsar job is cleaned up if this task is cancelled mid-flight
        await pulsar_operations.kill_job(task_id) 
        await pulsar_operations.erase_job(task_id) 
        print(f"Task {task_id} cleaned up after asyncio cancellation.")
        # Not re-raising, as this handler is managing the lifecycle.
    except Exception as error:
        # This block is now primarily for errors from job_status_complete or other unexpected issues
        print(f"Exception caught in handle_run_task for task {task_id}: {type(error).__name__} - {error}")

        # Check if the error is due to a prior cancellation
        # (e.g., LookupError because Pulsar job was erased by the cancel API)
        task_state_after_error_monad = await task_repository.get_task(maybe_of(author), {'_id': task_id})
        if task_state_after_error_monad.is_just() and task_state_after_error_monad.value.state == TesTaskState.CANCELED:
            print(f"Task {task_id} is already CANCELED. Exception '{type(error).__name__}' likely due to cancellation. No further error processing by handle_run_task.")
            # The cancel_task API path should have handled Pulsar job erasure.
            # No need to call pulsar_event_handle_error or erase_job again here.
            return # Exit gracefully

        # If not due to a prior cancellation, then it's an actual error during run.
        print(f"Task {task_id} not CANCELED, proceeding with generic error handling for '{type(error).__name__}'.")
        error_handler_result = pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)
        if asyncio.iscoroutine(error_handler_result) or isinstance(error_handler_result, _Promise):
            await error_handler_result
        
        # Fallback: Ensure Pulsar job is erased if pulsar_event_handle_error didn't.
        # This is a safeguard, as pulsar_event_handle_error should ideally manage this.
        try:
            print(f"Ensuring Pulsar job for task {task_id} is erased after general error handling.")
            await pulsar_operations.erase_job(task_id)
        except Exception as final_erase_error:
            print(f"Error during final erase attempt for task {task_id} after general error: {final_erase_error}")
