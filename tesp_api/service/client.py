
# Client
from abc import ABC, abstractmethod

# ClientS3
import asyncio
from aiobotocore.session import get_session
from botocore import UNSIGNED
from botocore.config import Config

from tesp_api.utils.functional import maybe_of
from tesp_api.utils.types import AnyUrl

# ClientFtp
import aioftp

from tesp_api.utils.functional import maybe_of
from tesp_api.utils.types import AnyUrl


class Client(ABC):
    @abstractmethod
    async def download_file(self, url: AnyUrl):
        raise NotImplementedError("Must override method \"download_file(url)\"")

    @abstractmethod
    async def upload_file(self, url: AnyUrl, file_content: bytes):
        raise NotImplementedError("Must override method \"upload_file(url, file_content)\"")


# TODO: Error handling
class ClientS3(Client):

    @staticmethod
    async def download_file(s3_url: AnyUrl):
        s3_url.parse_bucket()

        endpoint = f"http://{s3_url.host}:{s3_url.port}"

        auth: bool = s3_url.user and s3_url.password
        async with get_session().create_client(
            's3',
            config=Config(signature_version=UNSIGNED) if not auth else None,
            aws_access_key_id=s3_url.user,
            aws_secret_access_key=s3_url.password,
            endpoint_url=endpoint
        ) as client:
            async with (await client.get_object(Bucket=s3_url.bucket, Key=s3_url.path_without_bucket))['Body'] as stream:
                return await stream.read()

    @staticmethod
    async def upload_file(s3_url: AnyUrl, file_content: bytes):
        s3_url.parse_bucket()

        endpoint = f"http://{s3_url.host}:{s3_url.port}"

        auth: bool = s3_url.user and s3_url.password
        async with get_session().create_client(
            's3',
            config=Config(signature_version=UNSIGNED) if not auth else None,
            aws_access_key_id=s3_url.user,
            aws_secret_access_key=s3_url.password,
            endpoint_url=endpoint
        ) as client:
            await client.put_object(Bucket=s3_url.bucket, Key=s3_url.path_without_bucket, Body=file_content)


# TODO: Error handling
class ClientFTP(Client):

    def __init__(self):
        self.ftp_client = aioftp.Client()

    @staticmethod
    async def download_file(ftp_url: AnyUrl):
        async with aioftp.Client.context(
                host=ftp_url.host,
                port=maybe_of(ftp_url.port).maybe(aioftp.DEFAULT_PORT, lambda x: int(x)),
                user=maybe_of(ftp_url.user).maybe(aioftp.DEFAULT_USER, lambda x: x),
                password=maybe_of(ftp_url.password).maybe(aioftp.DEFAULT_PASSWORD, lambda x: x)) as client:
            async with client.download_stream(ftp_url.path) as stream:
                return await stream.read()

    @staticmethod
    async def upload_file(ftp_url: AnyUrl, file_content: bytes):
        async with aioftp.Client.context(
                host=ftp_url.host, port=maybe_of(ftp_url.port).maybe(aioftp.DEFAULT_PORT, lambda x: int(x)),
                user=maybe_of(ftp_url.user).maybe(aioftp.DEFAULT_USER, lambda x: x),
                password=maybe_of(ftp_url.password).maybe(aioftp.DEFAULT_PASSWORD, lambda x: x)) as client:
            async with client.upload_stream(ftp_url.path) as stream:
                await stream.write(file_content)


client_s3 = ClientS3()
client_ftp = ClientFTP()
