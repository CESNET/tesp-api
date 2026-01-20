import asyncio
import json
import aio_pika
from enum import Enum
from typing import Literal
from abc import ABC, abstractmethod
from urllib.parse import quote

from pymonad.maybe import Maybe, Nothing
from bson.objectid import ObjectId
from pymonad.promise import Promise
from aiohttp import ClientSession, ClientError

from tesp_api.repository.model.task import TesTaskIOType


class DataType(str, Enum):
    INPUT = "input",
    OUTPUT = "output"


class PulsarLayerConnectionError(Exception):
    def __init__(self, error: Exception):
        self.message = f'Pulsar connection error occurred [msg: {str(error)}]'
        super().__init__(self.message)

    def __repr__(self):
        return f'PulsarLayerConnectionError [message: {self.message}]'


class PulsarOperationsError(Exception):
    def __init__(self, error: Exception):
        self.message = f'Pulsar operations error occurred [msg: {str(error)}]'
        super().__init__(self.message)

    def __repr__(self):
        return f'PulsarOperationsError [message: {self.message}]'


class PulsarOperations(ABC):

    @abstractmethod
    def erase_job(self, task_id: ObjectId): pass

    @abstractmethod
    def setup_job(self, job_id: ObjectId): pass

    @abstractmethod
    def run_job(self, job_id: ObjectId, run_command: str): pass

    @abstractmethod
    def job_status_complete(self, job_id: str): pass

    @abstractmethod
    def upload(self, job_id: ObjectId, io_type: TesTaskIOType, file_path: str, file_content: Maybe[str]): pass

    @abstractmethod
    def download_output(self, job_id: ObjectId, file_name: str): pass

class PulsarRestOperations(PulsarOperations):

    def __init__(self, pulsar_client: ClientSession, base_url: str,
                 status_poll_interval: int, status_max_polls: int):
        self.pulsar_client = pulsar_client
        self.base_url = base_url
        self.status_poll_interval = status_poll_interval
        self.status_max_polls = status_max_polls

    @staticmethod
    def _reraise_custom(error: Exception):
        match error:
            case PulsarLayerConnectionError() as client_error: raise client_error
            case _ as any_error: raise PulsarOperationsError(any_error)

    async def _pulsar_request(self, path: str, method: Literal['GET', 'POST', 'PUT', 'DELETE'],
                              response_type: Literal['JSON', 'BYTES'], params=None, data=None):
        try:
            async with self.pulsar_client.request(
                    url=f'{self.base_url}{path}', method=method, params=params, data=data) as response:
                match response_type:
                    case 'JSON': return await response.json(content_type='text/html')
                    case 'BYTES': return await response.read()
                    case _ as value: raise ValueError(f'Got unexpected value [{value}] for response_type parameter')
        except (ClientError, asyncio.TimeoutError) as err:
            raise PulsarLayerConnectionError(err)

    async def job_status_complete(self, job_id: str):
        for i in range(0, self.status_max_polls):
            await asyncio.sleep(self.status_poll_interval)
            json_response = await self._pulsar_request(
                path=f'/jobs/{job_id}/status', method='GET', response_type='JSON')
            if json_response['complete'] == 'true':
                return json_response
        raise LookupError()

    def setup_job(self, job_id: ObjectId) -> Promise:
        return Promise(lambda resolve, reject: resolve(None))\
            .then(lambda nothing: self._pulsar_request(
                path="/jobs", method='POST',
                response_type='JSON', params={'job_id': str(job_id)}
            )).catch(self._reraise_custom)

    def upload(self, job_id: ObjectId, io_type: TesTaskIOType, file_path: str, file_content: Maybe[str] = Nothing):
        return Promise(lambda resolve, reject: resolve({'type': io_type.value, 'name': file_path}))\
            .then(lambda query_params: self._pulsar_request(
                path=f'/jobs/{str(job_id)}/files', method='POST', response_type='JSON',
                params=query_params, data=file_content.maybe("", lambda x: x)
            )).map(lambda json_result: json_result['path'])

    def run_job(self, job_id: ObjectId, run_command: str):
        return Promise(lambda resolve, reject: resolve(None))\
            .then(lambda nothing: self._pulsar_request(
                path=f'/jobs/{str(job_id)}/submit', method='POST', response_type='BYTES',
                params={'command_line': run_command})) \
            .catch(self._reraise_custom)

    def download_output(self, job_id: ObjectId, file_name: str):
        return Promise(lambda resolve, reject: resolve(None))\
            .then(lambda nothing: self._pulsar_request(
                path=f'/jobs/{str(job_id)}/files', method='GET', response_type='BYTES',
                params={'name': file_name}
            )).catch(self._reraise_custom)

    def erase_job(self, job_id: ObjectId):
        return Promise(lambda resolve, reject: resolve(None)) \
           .then(lambda nothing: self._pulsar_request(
               path=f'/jobs/{str(job_id)}/cancel',
               method='PUT', response_type='BYTES'
           )).catch(lambda error: None)\
           .then(lambda nothing: self._pulsar_request(
               path=f'/jobs/{str(job_id)}',
               method='DELETE', response_type='BYTES'
           )).catch(self._reraise_custom)


class PulsarAmqpOperations(PulsarOperations):
    def __init__(self, amqp_url: str, pulsar_client: ClientSession, base_url: str,
                 status_poll_interval: int, status_max_polls: int):
        self.amqp_url = amqp_url
        self.pulsar_client = pulsar_client
        self.base_url = base_url
        self.status_poll_interval = status_poll_interval
        self.status_max_polls = status_max_polls
        self.connection: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.Channel | None = None

    async def _connect(self):
        if self.connection is None or self.connection.is_closed:
            self.connection = await aio_pika.connect_robust(self.amqp_url)
            self.channel = await self.connection.channel()

    async def _send_message(self, message: dict, routing_key: str = "pulsar.queue"):
        await self._connect()
        await self.channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(message).encode()),
            routing_key=routing_key
        )

    @staticmethod
    def _reraise_custom(error: Exception):
        match error:
            case PulsarLayerConnectionError() as client_error: raise client_error
            case _ as any_error: raise PulsarOperationsError(any_error)

    async def _pulsar_request(self, path: str, method: Literal['GET', 'POST', 'PUT', 'DELETE'],
                              response_type: Literal['JSON', 'BYTES'], params=None, data=None):
        try:
            async with self.pulsar_client.request(
                    url=f'{self.base_url}{path}', method=method, params=params, data=data) as response:
                match response_type:
                    case 'JSON': return await response.json(content_type='text/html')
                    case 'BYTES': return await response.read()
                    case _ as value: raise ValueError(f'Unexpected response_type: {value}')
        except ClientError as err:
            raise PulsarLayerConnectionError(err)

    async def job_status_complete(self, job_id: str):
        """
        Submit via AMQP, but Poll via REST for completion.
        """
        for i in range(0, self.status_max_polls):
            await asyncio.sleep(self.status_poll_interval)
            # Reuse the REST endpoint to check status
            json_response = await self._pulsar_request(
                path=f'/jobs/{job_id}/status', method='GET', response_type='JSON')
            if json_response['complete'] == 'true':
                return json_response
        raise LookupError()

    def setup_job(self, job_id: str):
        return Promise(lambda resolve, reject: resolve(None))\
            .then(lambda _: self._send_message({
                "type": "job",
                "job_id": str(job_id)
            })).catch(lambda e: PulsarOperationsError(e))

    def run_job(self, job_id: ObjectId, run_command: str):
        return Promise(lambda resolve, reject: resolve(None))\
            .then(lambda _: self._send_message({
                "type": "submit",
                "job_id": str(job_id),
                "command_line": run_command
            })).catch(lambda e: PulsarOperationsError(e))

    def erase_job(self, task_id: ObjectId):
        return Promise(lambda resolve, reject: resolve(None))\
            .then(lambda _: self._send_message({
                "type": "cancel",
                "job_id": str(task_id)
            })).catch(lambda e: PulsarOperationsError(e))

    def upload(self, job_id: ObjectId, io_type: TesTaskIOType, file_path: str, file_content: Maybe[str] = Nothing):
        return Promise(lambda resolve, reject: resolve({'type': io_type.value, 'name': file_path}))\
            .then(lambda query_params: self._pulsar_request(
                path=f'/jobs/{str(job_id)}/files', method='POST', response_type='JSON',
                params=query_params, data=file_content.maybe("", lambda x: x)
            )).map(lambda json_result: json_result['path'])

    def download_output(self, job_id: ObjectId, file_name: str):
        return Promise(lambda resolve, reject: resolve(None))\
            .then(lambda _: self._pulsar_request(
                path=f'/jobs/{str(job_id)}/files', method='GET', response_type='BYTES',
                params={'name': file_name}
            )).catch(self._reraise_custom)
