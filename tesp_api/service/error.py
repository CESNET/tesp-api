from loguru import logger
from bson.objectid import ObjectId
from pymonad.maybe import Maybe, Nothing, Just
from pymonad.promise import Promise

from tesp_api.repository.model.task import TesTaskState
from tesp_api.repository.error import CustomDataLayerError
from tesp_api.repository.task_repository import task_repository
from tesp_api.service.pulsar_operations import PulsarOperations, PulsarLayerConnectionError, PulsarOperationsError


class TaskNotFoundError(Exception):

    def __init__(self, task_id: ObjectId, state: Maybe[TesTaskState] = Nothing):
        state_part = state.maybe('', lambda x: f', state: {x}')
        self.message = f'Expected task [id: {str(task_id)}{state_part}] not found'
        super().__init__(self.message)

    def __repr__(self):
        return f'TaskNotFoundError [message: {self.message}]'


class TaskExecutorError(Exception):

    def __init(self):
        super().__init__()

class UnsupportedProtocolError(Exception):

    def __init(self):
        super().__init__()


def repo_update_error_task_promise(task_id: ObjectId, state: TesTaskState, sys_log: Maybe[str]):
    update_query = {
        '$set': {'state': state},
        **sys_log.maybe({}, lambda x: {'$push': {'logs.$[].system_logs': x}})}
    return task_repository.update_task({'_id': task_id}, update_query)\
        .catch(lambda _error: logger.error(
            f'Failed to update task [id: {task_id}] to reflect its real state after error '
            f'occurred while executing one of the pulsar events'
        ))


def pulsar_cancel_task_promise(task_id: str, pulsar_operations: PulsarOperations):
    return pulsar_operations.erase_job(task_id)\
        .catch(lambda _error: logger.error(
            f'Failed to cancel pulsar job [id: {task_id}, error: {str(_error)}]. '
            f'This job future is in Pulsar hands from now on.'
        ))


def pulsar_event_handle_error(error: Exception, task_id: ObjectId,
                              event_name: str, pulsar_operations: PulsarOperations) -> Promise:
    task_id_str = str(task_id)
    match error:
        case TaskExecutorError():
            logger.warning(f'One of the task [id: {task_id_str}] executors execution finished with error while '
                           f'executing event [event_name: {event_name}]. This log is here just for reference and can be'
                           f' ignored since it originates from executor. Will try to cancel respective Pulsar job.')
            return repo_update_error_task_promise(task_id, TesTaskState.EXECUTOR_ERROR, Nothing)\
                .then(lambda ignored: pulsar_cancel_task_promise(task_id, pulsar_operations))

        case TaskNotFoundError() as task_not_found_error:
            logger.warning(f'Task reached unexpected state [msg: {task_not_found_error}] while executing event '
                           f'[event_name: {event_name}]. This might be a result of client canceling task. '
                           f'Execution will not continue')
            return Promise(lambda resolve, reject: resolve(None))

        case CustomDataLayerError():
            logger.error(f'Data layer error occurred while executing task event [event_name: {event_name}, '
                         f'task_id: {task_id_str}]. Will try to request Pulsar for job cancellation if possible.')
            return pulsar_cancel_task_promise(str(task_id), pulsar_operations)

        case PulsarLayerConnectionError() as pulsar_layer_connection_error:
            logger.error(f'Pulsar connection error occurred while executing task event [event_name: {event_name}, '
                         f'task_id: {task_id_str}, msg: {pulsar_layer_connection_error}]. Will try to cancel task '
                         f'and set it up with error message in the syslog attribute.')
            syslog: Maybe[str] = Just('Connection error with underlying task executor')
            return repo_update_error_task_promise(task_id, TesTaskState.SYSTEM_ERROR, syslog)

        case PulsarOperationsError() as pulsar_operations_error:
            logger.warning(f'Pulsar operations error occurred while executing task event [event_name: {event_name}, '
                           f'task_id: {task_id_str}, msg: {pulsar_operations_error}]. This indicates uncommon problem '
                           f'with processing/executing task therefore it will be set up with error message in the '
                           f'syslog attribute. Will try to cancel task and respective Pulsar job.')
            syslog: Maybe[str] = Just(f"Uncommon error occurred while working with underlying task executor. "
                                      f"[msg: {pulsar_operations_error.message}]")
            return pulsar_cancel_task_promise(task_id_str, pulsar_operations)\
                .then(lambda ignored: repo_update_error_task_promise(task_id, TesTaskState.SYSTEM_ERROR, syslog))

        case _ as unknown_error:
            logger.error(f'Unknown error occurred while executing task event [event_name: {event_name}, '
                         f'task_id: {task_id_str}, msg: {unknown_error}]. Such error was not expected leading to '
                         f'unrecoverable state. Will try to cancel task and respective Pulsar job.')
            syslog: Maybe[str] = Just("Unexpected error occurred while processing/executing the task")
            return pulsar_cancel_task_promise(task_id_str, pulsar_operations)\
                .then(lambda ignored: repo_update_error_task_promise(task_id, TesTaskState.SYSTEM_ERROR, syslog))
