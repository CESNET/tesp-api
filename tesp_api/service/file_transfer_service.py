from tesp_api.utils.functional import maybe_of
from tesp_api.utils.types import AnyUrl
from typing import Union

from tesp_api.service.client import client_s3, client_ftp, client_http, client_file  # Import ClientFile
from tesp_api.service.error import UnsupportedProtocolError


# TODO: Error handling
class FileTransferService:

    @staticmethod
    def _choose_client(url: Union[AnyUrl, str]):
        if not url.scheme:
            # If there is no scheme (i.e., a local file), use the file client
            return client_file
        
        if url.scheme == "s3":  return client_s3
        elif url.scheme == "ftp":  return client_ftp
        elif url.scheme == "http": return client_http
        elif url.scheme == "https": return client_http
        else: 
            raise UnsupportedProtocolError(f"Unsupported protocol: {url.scheme}")

    @staticmethod
    async def download_file(url: AnyUrl):
        return await FileTransferService._choose_client(url).download_file(url)

    @staticmethod
    async def upload_file(url: AnyUrl, file_content: bytes):
        await FileTransferService._choose_client(url).upload_file(url, file_content)


file_transfer_service = FileTransferService()
