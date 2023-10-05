import aioftp

from tesp_api.utils.functional import maybe_of
from tesp_api.utils.types import AnyUrl
from tesp_api.service.client.client import Client


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
