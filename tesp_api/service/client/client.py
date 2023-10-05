from abc import ABC, abstractmethod

from tesp_api.utils.types import AnyUrl

class Client(ABC):
    @abstractmethod
    async def download_file(self, url: AnyUrl):
        raise NotImplementedError("Must override method \"download_file(url)\"")

    @abstractmethod
    async def upload_file(self, url: AnyUrl, file_content: bytes):
        raise NotImplementedError("Must override method \"upload_file(url, file_content)\"")
