from pydantic.networks import AnyUrl
import pydantic.errors as errors


class FtpUrl(AnyUrl):
    allowed_schemes = {'ftp'}
    host_required = True

class HttpUrl(AnyUrl):
    allowed_schemes = {'http'}
    host_required = True

class HttpsUrl(AnyUrl):
    allowed_schemes = {'https'}
    host_required = True

class S3Url(AnyUrl):
    allowed_schemes = {'s3'}
    host_required = True

    def parse_bucket(self):
        if not self.path:
            raise errors.UrlError()

        parts = self.path.split('/')

        if not parts or len(parts) < 2:
            raise errors.UrlError()

        self.bucket = parts[1]
        self.path_without_bucket = '/'.join(parts[2:])

class LocalFileUrl(AnyUrl):
    # No scheme needed for local file paths, but we don't need to enforce any particular scheme
    host_required = False  # Local files don't have a host
    allowed_schemes = {''}  # No scheme needed for file paths

    # Custom validation to check if it's a valid path
    @classmethod
    def __get_validators__(cls):
        yield from super().__get_validators__()
        yield cls.validate_local_path

    @classmethod
    def validate_local_path(cls, v):
        # Ensure the path is a valid file path (basic check for now, you can extend this)
        if not isinstance(v, str):
            raise errors.UrlError("Invalid local file path")
        # Optional: Add further validation if necessary (e.g., check if the file exists)
        return v
