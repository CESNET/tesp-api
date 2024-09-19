from datetime import datetime
from typing import List

from bson.objectid import ObjectId
from fastapi.encoders import jsonable_encoder
from pymonad.maybe import Just, Maybe, Nothing

from tesp_api.service.error import TaskNotFoundError
from tesp_api.utils.functional import get_else_throw, maybe_of
from tesp_api.repository.task_repository import task_repository
from tesp_api.repository.model.task import RegisteredTesTask, TesTaskState, TesTaskLog, TesTaskExecutorLog


async def append_task_executor_logs(
        task_id: ObjectId,
        author: str,
        state: TesTaskState,
        command_start_time: datetime,
        command_end_time: datetime,
        stdout: str,
        stderr: str,
        exit_code: int
    ):
    task: RegisteredTesTask = await task_repository.get_task(maybe_of(author), {'_id': task_id, 'state': state}) \
        .map(lambda _task: get_else_throw(_task, TaskNotFoundError(task_id, Just(state))))
    logs: List[TesTaskLog] = task.logs.copy()
    logs[-1].end_time = command_end_time
    logs[-1].logs.append(TesTaskExecutorLog(
        start_time=command_start_time, end_time=command_end_time,
        stdout=stdout, stderr=stderr, exit_code=exit_code))
    await task_repository.update_task(
        {'_id': task_id, 'state': state},
        {'$set': {'logs': jsonable_encoder(logs)}}
    ).map(lambda _task: get_else_throw(_task, TaskNotFoundError(task_id, Just(state))))


async def update_last_task_log_time(
        task_id: ObjectId,
        author : str,
        state: TesTaskState,
        start_time: Maybe[datetime] = Nothing
    ):
    task: RegisteredTesTask = await task_repository.get_task(maybe_of(author), {'_id': task_id, 'state': state}) \
        .map(lambda _task: get_else_throw(_task, TaskNotFoundError(task_id, Just(state))))
    logs: List[TesTaskLog] = task.logs.copy()
    logs[-1].start_time = start_time.maybe(logs[-1].start_time, lambda x: x)
    await task_repository.update_task(
        {'_id': task_id, 'state': state},
        {'$set': {'logs': jsonable_encoder(logs)}}
    ).map(lambda _task: get_else_throw(_task, TaskNotFoundError(task_id, Just(state))))
