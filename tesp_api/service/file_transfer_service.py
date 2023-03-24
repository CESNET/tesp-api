
from tesp_api.utils.functional import maybe_of
from tesp_api.utils.types import AnyUrl

from tesp_api.service.client import client_s3, client_ftp
from tesp_api.service.error import UnsupportedProtocolError


# TODO: Error handling
class FileTransferService:

    @staticmethod
    def _choose_client(url: AnyUrl):
        if not url or not url.scheme:
            raise UnsupportedProtocolError()

        if   url.scheme ==  "s3": return client_s3
        elif url.scheme == "ftp": return client_ftp
        else: raise UnsupportedProtocolError()

    @staticmethod
    async def download_file(url: AnyUrl):
        await FileTransferService._choose_client(url).download_file(url)

    @staticmethod
    async def upload_file(url: AnyUrl, file_content: bytes):
        await FileTransferService._choose_client(url).upload_file(url, file_content)


file_transfer_service = FileTransferService()
