import secrets
from tesp_api.config.properties import properties
from tesp_api.service.error import BasicAuthError

def verify_basic_auth(username: str, password: str):
    valid_username = properties.basic_auth.username
    valid_password = properties.basic_auth.password
    
    if secrets.compare_digest(username, valid_username) and secrets.compare_digest(password, valid_password):
        return username 

    raise BasicAuthError("Invalid BasicAuth credentials")
