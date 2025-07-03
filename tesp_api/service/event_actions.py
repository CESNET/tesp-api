import os
import datetime
from typing import List
from pathlib import Path

from pymonad.maybe import Just
from bson.objectid import ObjectId
from pymonad.promise import Promise

#from tesp_api.utils.docker import (
#    docker_run_command,
#    docker_stage_in_command,
#    docker_stage_out_command,
#    map_volumes
#)
#from tesp_api.utils.singularity import (
#    singularity_run_command,
#    singularity_stage_in_command,
#    singularity_stage_out_command
#)
from tesp_api.utils.container import stage_in_command, run_command, stage_out_command, map_volumes
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
    TesTaskOutput,
    TesTaskIOType
)
from tesp_api.repository.task_repository_utils import append_task_executor_logs, update_last_task_log_time

CONTAINER_TYPE = os.getenv("CONTAINER_TYPE", "docker")


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

        container_cmds = list()
        stage_exec = TesTaskExecutor(image="willdockerhub/curl-wget:latest",
                                         command=[],
                                         workdir=Path("/downloads"))
        # stage-in
        stage_in_cmd = ""
        if input_confs:
            stage_in_mount = payload['task_config']['inputs_directory']
            stage_in_cmd = stage_in_command(
                stage_exec,
                resource_conf,
                stage_in_mount,
                input_confs,
                CONTAINER_TYPE
            )

        # main execution
        container_cmds = []
        for i, executor in enumerate(task.executors):
            run_cmd = run_command(
                executor=executor,
                job_id=task_id,
                resource_conf=resource_conf,
                volume_confs=volume_confs,
                input_confs=input_confs,
                output_confs=output_confs,
                inputs_directory=stage_in_mount if input_confs else "",
                container_type=CONTAINER_TYPE,
                job_directory=payload['task_config']['job_directory'] if CONTAINER_TYPE == "singularity" else None,
                executor_index=i
            )
            container_cmds.append(run_cmd)

        # stage-out
        stage_out_cmd = ""
        if output_confs:
            stage_out_cmd = stage_out_command(
                stage_exec,
                resource_conf,
                output_confs,
                volume_confs,
                container_type=CONTAINER_TYPE,
                bind_mount=payload['task_config']['inputs_directory'] if CONTAINER_TYPE == "singularity" else None,
                job_directory=payload['task_config']['job_directory'] if CONTAINER_TYPE == "singularity" else None
            )

        # Combine commands
        run_commands = " && ".join(container_cmds)
        parts = ["set -xe", stage_in_cmd, run_commands, stage_out_cmd]
        non_empty_parts = [p.strip() for p in parts if p and p.strip()]
        full_command = " && ".join(non_empty_parts)
        print(full_command)

        command_start_time = datetime.datetime.now(datetime.timezone.utc)

        # start the task (docker container/s) in the pulsar
        await pulsar_operations.run_job(task_id, full_command)

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
            task = await task_repository.update_task_state(
                task_id,
                TesTaskState.RUNNING,
                TesTaskState.EXECUTOR_ERROR
            )

            raise TaskExecutorError()

    except Exception as error:
        pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)

    #    dispatch_event('finalize_task', payload)
    await Promise(lambda resolve, reject: resolve(None)) \
        .then(lambda ignored: task_repository.update_task_state(
            task_id,
            TesTaskState.RUNNING,
            TesTaskState.COMPLETE
        )) \
        .map(lambda task: get_else_throw(
            task, TaskNotFoundError(task_id, Just(TesTaskState.RUNNING))
            )) \
        .then(lambda ignored: pulsar_operations.erase_job(task_id)) \
        .catch(lambda error: pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)) \
        .then(lambda x: x) # invokes promise returned by error handler, otherwise acts as identity function
