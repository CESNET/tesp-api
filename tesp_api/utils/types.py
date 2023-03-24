from pydantic.networks import AnyUrl
import pydantic.errors as errors


class FtpUrl(AnyUrl):
    allowed_schemes = {'ftp'}
    host_required = True

class HttpUrl(AnyUrl):
    allowed_schemes = {'http'}
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
