import os
import re
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


@local_handler.register(event_name="queued_task")
def handle_queued_task(event: Event) -> None:
    event_name, payload = event
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

        print(output_confs)

        return resource_conf, volume_confs, input_confs, output_confs

    await Promise(lambda resolve, reject: resolve(None))\
        .then(lambda nothing: task_repository.update_task(
            {'_id': task_id, "state": TesTaskState.QUEUED},
            {'$set': {'state': TesTaskState.INITIALIZING}}
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
    resource_conf: dict = payload['resource_conf']
    volume_confs: List[Path] = payload['volume_confs']
    input_confs: List[dict] = payload['input_confs']
    output_confs: List[dict] = payload['output_confs']
    pulsar_operations: PulsarRestOperations = payload['pulsar_operations']

    print("PAYLOAD !!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print(payload)

    # init task
    task_monad = await task_repository.update_task(
        {'_id': task_id, "state": TesTaskState.INITIALIZING},
        {'$set': {'state': TesTaskState.RUNNING}}
    )
    try:
        task = get_else_throw(task_monad, TaskNotFoundError(task_id, Just(TesTaskState.INITIALIZING)))

        await update_last_task_log_time(
            task_id, TesTaskState.RUNNING,
            start_time=Just(datetime.datetime.now(datetime.timezone.utc)))

        print("TASK EXECUTORS !!!!!")
        print(task.executors)
        print("Resource conf")
        print(resource_conf)
        print("Volume conf")
        print(volume_confs)
        print("Input conf")
        print(input_confs)
        print("Output conf")
        print(output_confs)
        print("!!!!!!!!!!!!!!!!!!!!")

        # prepare docker commands
        docker_cmds = list()
        # stage-in
        stage_in_mount = payload['task_config']['inputs_directory']
        stage_in_exec = TesTaskExecutor(image="willdockerhub/curl-wget:latest",
                                        command=[],
                                        workdir=Path("/downloads"))
        stage_in_command = docker_stage_in_command(stage_in_exec, resource_conf, stage_in_mount, input_confs)
        docker_cmds.append(stage_in_command)
        
        for executor in task.executors:
            print("Executor:")
            print(executor)
            run_command, script_content = docker_run_command(executor, resource_conf, volume_confs,
                                                             input_confs, output_confs, stage_in_mount)
            print("Docker command:")
            print(run_command)
            docker_cmds.append(run_command)

        await pulsar_operations.upload(
            payload['task_id'], DataType.INPUT,
            file_content=Just(script_content),
            file_path=f'run_script.sh')

        run_command = f"set -xe && " + " && ".join(docker_cmds)

        command_start_time = datetime.datetime.now(datetime.timezone.utc)

        # start the task (docker container/s) in the pulsar
        await pulsar_operations.run_job(task_id, run_command)

        # wait for the task
        command_status = await pulsar_operations.job_status_complete(str(task_id))

        command_end_time = datetime.datetime.now(datetime.timezone.utc)
        await append_task_executor_logs(
            task_id, TesTaskState.RUNNING, command_start_time, command_end_time, command_status['stdout'],
            command_status['stderr'], command_status['returncode'])
        if command_status['returncode'] != 0:
            task = await task_repository.update_task(
                {'_id': task_id, "state": TesTaskState.RUNNING},
                {'$set': {'state': TesTaskState.EXECUTOR_ERROR}}
            )

            raise TaskExecutorError()

        dispatch_event('finalize_task', payload)

    except Exception as error:
        pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)


@local_handler.register(event_name='finalize_task')
async def handle_finalize_task(event: Event) -> None:
    event_name, payload = event
    task_id: ObjectId = payload['task_id']
    output_confs: List[dict] = payload['output_confs']
    volume_confs: List[dict] = payload['volume_confs']
    resource_conf: dict = payload['resource_conf']
    pulsar_outputs_dir_path: str = payload['task_config']['outputs_directory']
    pulsar_operations: PulsarRestOperations = payload['pulsar_operations']

    async def transfer_files():
        stage_out_exec = TesTaskExecutor(image="willdockerhub/curl-wget:latest",
                                        command=[],
                                        workdir=Path("/"))
        stage_out_command = docker_stage_out_command(stage_out_exec, resource_conf, output_confs, volume_confs)
        run_command = f"set -xe && " + stage_out_command
        # start the task (docker container/s) in the pulsar
        await pulsar_operations.run_job(task_id, run_command)
        command_status = await pulsar_operations.job_status_complete(str(task_id))

    await transfer_files()

    await Promise(lambda resolve, reject: resolve(None)) \
        .then(lambda ignored: task_repository.update_task(
        {'_id': task_id, "state": TesTaskState.RUNNING},
        {'$set': {'state': TesTaskState.COMPLETE}}
    )).map(lambda task: get_else_throw(
        task, TaskNotFoundError(task_id, Just(TesTaskState.RUNNING))
    )).then(lambda ignored: pulsar_operations.erase_job(task_id)) \
        .catch(lambda error: pulsar_event_handle_error(error, task_id, event_name, pulsar_operations)) \
        .then(lambda x: x) # invokes promise returned by error handler, otherwise acts as identity function