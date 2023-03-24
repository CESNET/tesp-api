from aiobotocore.session import get_session
from botocore import UNSIGNED
from botocore.config import Config

from tesp_api.utils.functional import maybe_of
from tesp_api.utils.types import AnyUrl
from tesp_api.service.client.client import Client


# TODO: Error handling, maybe_of
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
