import os
from tesp_api.service.client.client import Client

class ClientFile(Client):

    @staticmethod
    async def download_file(file_path: str):
        """
        Download a file from the local filesystem based on the given file path.
        The file_path is expected to be a local path (e.g., "/home/user/file.txt").
        """
        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, 'rb') as file:
                return file.read()
        else:
            raise FileNotFoundError(f"File not found: {file_path}")

    @staticmethod
    async def upload_file(file_path: str, file_content: bytes):
        """
        Upload a file to the local filesystem based on the given file path.
        The file_path is expected to be a local path (e.g., "/home/user/file.txt").
        """
        with open(file_path, 'wb') as file:
            file.write(file_content)

