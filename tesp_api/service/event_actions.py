import os
import datetime
from typing import List
from pathlib import Path
import asyncio

from loguru import logger

from pymonad.maybe import Just, Nothing
from bson.objectid import ObjectId
from pymonad.promise import Promise, _Promise

from tesp_api.utils.container import stage_in_command, run_command, stage_out_command, map_volumes
from tesp_api.service.pulsar_service import pulsar_service
from tesp_api.service.event_dispatcher import dispatch_event
from tesp_api.utils.functional import get_else_throw, maybe_of
from tesp_api.service.event_handler import Event, local_handler
from tesp_api.repository.task_repository import task_repository
from tesp_api.service.file_transfer_service import file_transfer_service
from tesp_api.service.error import pulsar_event_handle_error, TaskNotFoundError, TaskExecutorError
from tesp_api.service.pulsar_operations import PulsarRestOperations, PulsarAmqpOperations, DataType
from tesp_api.repository.model.task import (
    TesTaskState,
    TesTaskExecutor,
    TesTaskResources,
    TesTaskInput,
    TesTaskOutput,
    TesTaskIOType
)
from tesp_api.repository.task_repository_utils import append_task_executor_logs, update_last_task_log_time

CONTAINER_TYPE = os.getenv("CONTAINER_TYPE", "docker")


@local_handler.register(event_name="queued_task")
def handle_queued_task(event: Event) -> None:
    """
    Dispatches the task to a REST or AMQP specific handler based on Pulsar operations type.
    """
    event_name, payload = event
    logger.info(f"Queued task: {payload.get('task_id')}")
    match pulsar_service.get_operations():
        case PulsarRestOperations() as pulsar_rest_operations:
            dispatch_event('queued_task_rest', {**payload, 'pulsar_operations': pulsar_rest_operations})
        case PulsarAmqpOperations() as pulsar_amqp_operations:
            dispatch_event('queued_task_amqp', {**payload, 'pulsar_operations': pulsar_amqp_operations})


@local_handler.register(event_name="queued_task_rest")
async def handle_queued_task_rest(event: Event):
    """
    Sets up the job in Pulsar via REST operations and dispatches an 'initialize_task' event.
    """
    event_name, payload = event
    task_id: ObjectId = payload['task_id']
    pulsar_operations: PulsarRestOperations = payload['pulsar_operations']

    logger.debug(f"Queued task rest: {task_id}")

    await Promise(lambda resolve, reject: resolve(None)) \
        .then(lambda nothing: pulsar_operations.setup_job(task_id)) \
        .map(lambda setup_job_result: dispatch_event('initialize_task', {**payload, 'task_config': setup_job_result})) \
        .catch(lambda error: pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)) \
        .then(lambda x: x)  # Invokes promise, potentially from error handler


@local_handler.register(event_name="queued_task_amqp")
async def handle_queued_task_amqp(event: Event):
    """
    Sets up the job in Pulsar via AMQP operations and dispatches an 'initialize_task' event.
    """
    event_name, payload = event
    task_id: ObjectId = payload['task_id']
    pulsar_operations: PulsarAmqpOperations = payload['pulsar_operations']

    logger.debug(f"Queued task AMQP: {task_id}")

    try:
        # Setup job via AMQP
        setup_job_result = await pulsar_operations.setup_job(task_id)

        # Dispatch initialize event
        await dispatch_event('initialize_task', {
            **payload,
            'task_config': setup_job_result
        })
    except Exception as error:
        await pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)


@local_handler.register(event_name="initialize_task")
async def handle_initializing_task(event: Event) -> None:
    """
    Updates task state to INITIALIZING, prepares data/volumes/inputs/outputs,
    and dispatches a 'run_task' event.
    """
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

        output_confs, volume_confs = map_volumes(str(job_id), volumes, outputs)

        for i, input_item in enumerate(inputs):
            if input_item.type == TesTaskIOType.DIRECTORY:
                pulsar_path = payload['task_config']['inputs_directory'] + f'/input_dir_{i}'
            elif input_item.content is not None and input_item.url is None:
                pulsar_path = await pulsar_operations.upload(
                    job_id, DataType.INPUT,
                    file_content=Just(input_item.content),
                    file_path=f'input_file_{i}'
                )
            else:
                pulsar_path = payload['task_config']['inputs_directory'] + f'/input_file_{i}'

            input_confs.append({
                'container_path': input_item.path,
                'pulsar_path': pulsar_path,
                'url': input_item.url,
                'type': input_item.type
            })

        return resource_conf, volume_confs, input_confs, output_confs

    logger.info(f"Initializing task: {task_id}")

    await Promise(lambda resolve, reject: resolve(None)) \
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
    })).catch(lambda error: pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)) \
        .then(lambda x: x)


@local_handler.register(event_name="run_task")
async def handle_run_task(event: Event) -> None:
    """
    Updates task state to RUNNING, prepares and executes job commands in Pulsar,
    waits for completion, logs results, and updates task state accordingly (COMPLETE, EXECUTOR_ERROR).
    Handles cancellations and other exceptions during its lifecycle.
    """
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

    try:
        logger.info(f"Running task: {task_id}")
        # Set task state to RUNNING
        task_monad_init = await task_repository.update_task_state(
            task_id,
            TesTaskState.INITIALIZING,
            TesTaskState.RUNNING
        )
        task = get_else_throw(task_monad_init, TaskNotFoundError(task_id, Just(TesTaskState.INITIALIZING)))

        # Early check for cancellation
        current_task_after_init_monad = await task_repository.get_task(maybe_of(author), {'_id': task_id})
        current_task_after_init = get_else_throw(current_task_after_init_monad, TaskNotFoundError(task_id))
        if current_task_after_init.state == TesTaskState.CANCELED:
            logger.warning(f"Task {task_id} found CANCELED shortly after RUNNING state update. Aborting handler.")
            return

        await update_last_task_log_time(
            task_id,
            author,
            TesTaskState.RUNNING,
            start_time=Just(datetime.datetime.now(datetime.timezone.utc))
        )

        stage_exec = TesTaskExecutor(image="willdockerhub/curl-wget:latest", command=[], workdir=Path("/downloads"))

        # Stage-in command
        stage_in_cmd = ""
        stage_in_mount = ""
        if input_confs:
            stage_in_mount = payload['task_config']['inputs_directory']
            stage_in_cmd = stage_in_command(stage_exec, resource_conf, stage_in_mount, input_confs, CONTAINER_TYPE)

        # Main execution commands
        container_cmds = []
        for i, executor in enumerate(task.executors):
            run_cmd = run_command(
                executor=executor, job_id=str(task_id), resource_conf=resource_conf,
                volume_confs=volume_confs, input_confs=input_confs, output_confs=output_confs,
                inputs_directory=stage_in_mount, container_type=CONTAINER_TYPE,
                job_directory=payload['task_config'].get('job_directory') if CONTAINER_TYPE == "singularity" else None,
                executor_index=i
            )
            container_cmds.append(run_cmd)

        # Stage-out command
        stage_out_cmd = ""
        if output_confs:
            stage_out_cmd = stage_out_command(
                stage_exec, resource_conf, output_confs, volume_confs,
                container_type=CONTAINER_TYPE,
                bind_mount=payload['task_config'].get('inputs_directory') if CONTAINER_TYPE == "singularity" else None,
                job_directory=payload['task_config'].get('job_directory') if CONTAINER_TYPE == "singularity" else None
            )

        # Combine all commands into a single string for Pulsar
        executors_commands_joined_str = " && ".join(filter(None, container_cmds))
        parts = ["set -xe", stage_in_cmd, executors_commands_joined_str, stage_out_cmd]
        non_empty_parts = [p.strip() for p in parts if p and p.strip()]
        run_command_str = " && ".join(non_empty_parts) if non_empty_parts else None

        command_start_time = datetime.datetime.now(datetime.timezone.utc)
        command_status: dict

        if run_command_str is None:
            logger.warning(f"Task {task_id} has no commands to run. Treating as successful no-op.")
            command_status = {'stdout': '', 'stderr': 'No commands to run.', 'returncode': 0}
        else:
            logger.debug(f"Submitting job to Pulsar for task {task_id}: {run_command_str}")
            await pulsar_operations.run_job(task_id, run_command_str)
            command_status = await pulsar_operations.job_status_complete(str(task_id))

        command_end_time = datetime.datetime.now(datetime.timezone.utc)
        await append_task_executor_logs(
            task_id, author, TesTaskState.RUNNING,
            command_start_time, command_end_time,
            command_status.get('stdout', ''), command_status.get('stderr', ''),
            command_status.get('returncode', -1)
        )

        current_task_monad = await task_repository.get_task(maybe_of(author), {'_id': task_id})
        current_task_obj = get_else_throw(current_task_monad, TaskNotFoundError(task_id))

        if current_task_obj.state == TesTaskState.CANCELED:
            logger.warning(f"Task {task_id} found CANCELED after job completion polling. Aborting state changes.")
            return

        if command_status.get('returncode', -1) != 0:
            logger.error(
                f"Task {task_id} executor error (return code: {command_status.get('returncode', -1)}). Setting state to EXECUTOR_ERROR.")
            await task_repository.update_task_state(task_id, TesTaskState.RUNNING, TesTaskState.EXECUTOR_ERROR)
            await pulsar_operations.erase_job(task_id)
            return

        logger.info(f"Task {task_id} completed successfully. Setting state to COMPLETE.")
        await Promise(lambda resolve, reject: resolve(None)) \
            .then(lambda ignored: task_repository.update_task_state(
            task_id, TesTaskState.RUNNING, TesTaskState.COMPLETE
        )) \
            .map(lambda task_after_complete_update: get_else_throw(
            task_after_complete_update, TaskNotFoundError(task_id, Just(TesTaskState.RUNNING))
        )) \
            .then(lambda ignored: pulsar_operations.erase_job(task_id)) \
            .catch(lambda error: pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)) \
            .then(lambda x: x)

    except asyncio.CancelledError:
        logger.warning(f"handle_run_task for task {task_id} was explicitly cancelled (asyncio.CancelledError).")
        await task_repository.update_task_state(task_id, None, TesTaskState.CANCELED)
        await pulsar_operations.kill_job(task_id)
        await pulsar_operations.erase_job(task_id)
        logger.info(f"Task {task_id} Pulsar job cleanup attempted after asyncio cancellation.")

    except Exception as error:
        logger.error(f"Exception in handle_run_task for task {task_id}: {type(error).__name__} - {error}")

        task_state_after_error_monad = await task_repository.get_task(maybe_of(author), {'_id': task_id})
        if task_state_after_error_monad.is_just() and task_state_after_error_monad.value.state == TesTaskState.CANCELED:
            logger.info(
                f"Task {task_id} is already CANCELED. Exception '{type(error).__name__}' likely due to this. No further error processing by handler.")
            return

        logger.debug(f"Task {task_id} not CANCELED; proceeding with pulsar_event_handle_error for '{type(error).__name__}'.")
        error_handler_result = pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)
        if asyncio.iscoroutine(error_handler_result) or isinstance(error_handler_result, _Promise):
            await error_handler_result

        # try:
        #     print(f"Ensuring Pulsar job for task {task_id} is erased after general error handling in run_task.")
        #     await pulsar_operations.erase_job(task_id)
        # except Exception as final_erase_error:
        #     print(
        #        f"Error during final Pulsar erase attempt for task {task_id} after general error: {final_erase_error}")
