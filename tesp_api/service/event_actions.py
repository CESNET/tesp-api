import os
import datetime
from typing import List
from pathlib import Path

from pymonad.maybe import Just
from bson.objectid import ObjectId
from pymonad.promise import Promise

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
from tesp_api.repository.model.task import (
    TesTaskState,
    TesTaskExecutor,
    TesTaskResources,
    TesTaskInput,
    TesTaskOutput
)
from tesp_api.repository.task_repository_utils import append_task_executor_logs, update_last_task_log_time

CONTAINER_TYPE = os.getenv("CONTAINER_TYPE", "both")


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
        .then(lambda x: x)  # invokes promise returned by error handler, otherwise acts as identity function


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
        output_confs, volume_confs = map_volumes(str(job_id), volumes, outputs)

        print(inputs)

        for i in range(0, len(inputs)):
            content = inputs[i].content
            pulsar_path = payload['task_config']['inputs_directory'] + f'/input_file_{i}'
            if content is not None and inputs[i].url is None:
                #content = await file_transfer_service.download_file(inputs[i].url)
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
            maybe_of(updated_task.resources).maybe([], lambda x: x),
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
        .then(lambda x: x)  # invokes promise returned by error handler, otherwise acts as identity function


@local_handler.register(event_name="run_task")
async def handle_run_task(event: Event) -> None:
    event_name, payload = event
    task_id: ObjectId = payload['task_id']
    author: str = payload['author']
    resource_conf: dict = payload['resource_conf']
    volume_confs: List[Path] = payload['volume_confs']
    input_confs: List[dict] = payload['input_confs']
    output_confs: List[dict] = payload['output_confs']
    pulsar_operations: PulsarRestOperations = payload['pulsar_operations']

    # init task
    task_monad = await task_repository.update_task_state(
        task_id,
        TesTaskState.INITIALIZING,
        TesTaskState.RUNNING
    )
    try:
        task = get_else_throw(task_monad, TaskNotFoundError(task_id, Just(TesTaskState.INITIALIZING)))

        await update_last_task_log_time(
            task_id,
            author,
            TesTaskState.RUNNING,
            start_time=Just(datetime.datetime.now(datetime.timezone.utc))
        )

        # prepare container commands, initialize to None
        container_cmds = list()
        stage_in_command = None
        stage_out_command = None

        # stage-in preparation
        print("Payload:")
        print(payload)
        stage_in_mount = payload['task_config']['inputs_directory']
        # Define a generic executor for staging operations
        stage_exec = TesTaskExecutor(image="willdockerhub/curl-wget:latest",
                                        command=[],
                                        workdir=Path("/downloads"))

        if CONTAINER_TYPE == "docker":
            stage_in_command = docker_stage_in_command(stage_exec, resource_conf, stage_in_mount, input_confs)
        elif CONTAINER_TYPE == "singularity":
            # Adapt image name if needed for singularity
            singularity_stage_exec = TesTaskExecutor(image="docker://" + stage_exec.image, command=[], workdir=stage_exec.workdir)
            stage_in_command = singularity_stage_in_command(singularity_stage_exec, resource_conf, stage_in_mount, input_confs)
            # Note: Assumes singularity_stage_in_command was also modified to return None if input_confs is empty. If not, this part needs adjustment.


        # Main execution commands
        for i, executor in enumerate(task.executors):
            run_command = ""
            script_content = ""
            if CONTAINER_TYPE == "docker":
                run_command, script_content = docker_run_command(executor, str(task_id), resource_conf, volume_confs,
                                                                 input_confs, output_confs, stage_in_mount, i)
            elif CONTAINER_TYPE == "singularity":
                mount_job_dir = payload['task_config']['job_directory']
                run_command, script_content = singularity_run_command(executor, str(task_id), resource_conf, volume_confs,
                                                                 input_confs, output_confs, stage_in_mount, mount_job_dir, i)

            if run_command and script_content: # Ensure command generation was successful
                await pulsar_operations.upload(
                    payload['task_id'], DataType.INPUT,
                    file_content=Just(script_content),
                    file_path=f'run_script_{i}.sh')
                container_cmds.append(run_command)

        # Stage-out preparation
        if CONTAINER_TYPE == "docker":
             stage_out_command = docker_stage_out_command(stage_exec, resource_conf, output_confs, volume_confs)
        elif CONTAINER_TYPE == "singularity":
            mount_job_dir = payload['task_config']['job_directory']
            bind_mount = payload['task_config']['inputs_directory'] # This might need adjustment based on actual stage-out needs
            # Adapt image name if needed for singularity
            singularity_stage_exec = TesTaskExecutor(image="docker://" + stage_exec.image, command=[], workdir=stage_exec.workdir)
            stage_out_command = singularity_stage_out_command(singularity_stage_exec, resource_conf, bind_mount,
                                                              output_confs, volume_confs, mount_job_dir)
            # Note: Assumes singularity_stage_out_command was also modified to return None if output_confs is empty. If not, this part needs adjustment.


        # Build the final command string conditionally
        final_command_parts = ['set -xe'] # Start with execution options

        if stage_in_command:
            final_command_parts.append(stage_in_command)

        if container_cmds: # Only add run commands if there are any
            final_command_parts.append(" && ".join(container_cmds))

        if stage_out_command:
             final_command_parts.append(stage_out_command)

        # Join the parts that exist with ' && '
        # Filter out potential empty strings just in case, though the logic above should prevent them
        final_run_command = " && ".join(filter(None, final_command_parts))


        # Ensure there's actually something to run
        if len(final_command_parts) <= 1 : # Only 'set -xe' is present
             print(f"Task {task_id}: No commands to execute (no stage-in, no main executors, no stage-out). Skipping Pulsar job run.")
             # Decide how to proceed - mark as complete? Error? For now, let's proceed to completion logic.
             # We might skip pulsar interaction entirely here.

        else:
            print(f"Task {task_id}: Final command to run in Pulsar:")
            print(final_run_command)
            command_start_time = datetime.datetime.now(datetime.timezone.utc)

            # start the task (docker container/s) in the pulsar
            await pulsar_operations.run_job(task_id, final_run_command)

            # wait for the task
            command_status = await pulsar_operations.job_status_complete(str(task_id))

            command_end_time = datetime.datetime.now(datetime.timezone.utc)
            await append_task_executor_logs(
                task_id,
                author,
                TesTaskState.RUNNING,
                command_start_time,
                command_end_time,
                command_status['stdout'],
                command_status['stderr'],
                command_status['returncode']
            )
            if command_status['returncode'] != 0:
                await task_repository.update_task_state( # Await the update
                    task_id,
                    TesTaskState.RUNNING,
                    TesTaskState.EXECUTOR_ERROR
                )
                # Log the error details before raising
                print(f"Task {task_id} executor error. Pulsar job return code: {command_status['returncode']}")
                print(f"Stdout:\n{command_status['stdout']}")
                print(f"Stderr:\n{command_status['stderr']}")
                raise TaskExecutorError(f"Pulsar job failed with return code {command_status['returncode']}")


    except Exception as error:
        print(f"Error during task {task_id} execution in event {event_name}: {type(error).__name__} - {error}")
        import traceback
        traceback.print_exc()
        # Call the existing error handler
        await pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)
        # Rethrow or handle cleanup if pulsar_event_handle_error doesn't terminate execution flow
        return # Stop further processing in this handler after error

    # Finalize task - This part runs only if no exceptions occurred or were caught and handled above
    # If an error occurred and was handled by pulsar_event_handle_error which updated state,
    # this final update to COMPLETE might be incorrect. Consider state check if needed.
    print(f"Task {task_id}: Execution seemingly successful, proceeding to finalize.")
    await Promise(lambda resolve, reject: resolve(None)) \
        .then(lambda ignored: task_repository.update_task_state(
            task_id,
            TesTaskState.RUNNING, # Original state before completion
            TesTaskState.COMPLETE
        )) \
        .map(lambda task: get_else_throw(
            task, TaskNotFoundError(task_id, Just(TesTaskState.RUNNING)) # Expect RUNNING if successful
            )) \
        .then(lambda ignored: pulsar_operations.erase_job(task_id)) \
        .catch(lambda error: pulsar_event_handle_error(error, task_id, "finalize_task", pulsar_operations)) \
        .then(lambda x: x) # invokes promise returned by error handler, otherwise acts as identity function
