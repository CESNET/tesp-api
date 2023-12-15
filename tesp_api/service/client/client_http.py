import aiohttp

from tesp_api.utils.functional import maybe_of
from tesp_api.utils.types import AnyUrl
from tesp_api.service.client.client import Client


# TODO: Error handling, authentication
class ClientHTTP(Client):

    @staticmethod
    async def download_file(http_url: AnyUrl):
        async with aiohttp.ClientSession() as session:
            async with session.get(http_url) as response:
                return await response.read()

    @staticmethod
    async def upload_file(http_url: AnyUrl, file_content: bytes):
        async with aiohttp.ClientSession() as session:
            await session.post(http_url, data=file_content)
            # curl --upload-file "/opt/pysetup/files/staging/6567036c3beccb6a89937c1d/outputs/dataset_2095604c-1ea9-4684-a3ed-b66f65dbe2ab.dat"