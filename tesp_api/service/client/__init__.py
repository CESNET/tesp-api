from tesp_api.service.client.client_s3 import ClientS3
from tesp_api.service.client.client_ftp import ClientFTP
from tesp_api.service.client.client_http import ClientHTTP
from tesp_api.service.client.client_file import ClientFile

client_s3 = ClientS3()
client_ftp = ClientFTP()
client_http = ClientHTTP()
client_file = ClientFile()
