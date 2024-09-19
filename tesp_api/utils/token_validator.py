
import requests
import posixpath
import jwt
import jwt.algorithms
from jwt import PyJWKClient

from tesp_api.service.error import OAuth2TokenError

def verify_token(token):
    """
    WARNING: Verify validity of given JWT token for OAuth2.
    Accepts any valid tokens from any issuer including owns!
    Expects optional JWT parameters!
    """

    # Decode without verification to obtain usefull data
    #=====================================================

    try:
        token_header = jwt.get_unverified_header(token)
        token_payload = jwt.decode(token, options={"verify_signature": False})
    except Exception as e:
        raise OAuth2TokenError(f"Failed to decode token. Ex: {str(e)}")

    # Obtain desired data
    #======================

    # 'sub' - user identification
    token_sub = token_payload.get('sub')
    # 'alg' - used algorithm - not desired
    token_alg = token_header.get('alg')
    # 'iss' - issuer of the token, required for verification
    token_iss = token_payload.get('iss')

    if not token_sub:
        raise OAuth2TokenError("Missing 'sub' parameter in JWT token payload.")

    if not token_iss:
        raise OAuth2TokenError("Missing 'iss' parameter in JWT token payload.")

    # Obtain issuer signing key to verify the token
    #================================================

    # Get "jwk_uri" endpoint
    issuer_wk_config_url = posixpath.join(token_iss, ".well-known/openid-configuration")
    try:
        response = requests.get(issuer_wk_config_url)
    except Exception as e:
        raise OAuth2TokenError("Contacting the token issuer failed.")

    if response.status_code != 200:
        raise OAuth2TokenError(f"Contacting the token issuer returns HTTP code {response.status_code}.")

    try:
        issuer_wk_config_data = response.json()
    except requests.exceptions.JSONDecodeError as e:
        raise OAuth2TokenError("Failed to parse response from token issuer.")

    issuer_jwk_uri = issuer_wk_config_data.get('jwks_uri')
    if not issuer_jwk_uri:
        raise OAuth2TokenError("Failed to obtain issuer signing key.")

    # Get signing key from the "jwk_uri"
    try:
        jwks_client = PyJWKClient(issuer_jwk_uri)
        issuer_signing = jwks_client.get_signing_key_from_jwt(token).key
    except (PyJWKClientError, Exception) as e:
        raise OAuth2TokenError(f"Failed to obtain issuer signing key. Ex: {str(e)}")

    # If the token does not contain the 'alg' parameter, try list of supported algorithms by the library
    if not token_alg:
        token_alg = list(jwt.algorithms.get_default_algorithms().keys())

    # Verify the token
    #===================

    # (ignore audience)
    try:
        jwt.decode(
            token,
            key = issuer_signing,
            algorithms = token_alg,
            issuer = token_iss,
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": False,
                "verify_iss": True,
            }
        )
    except Exception as e:
        raise OAuth2TokenError(f"Failed to verify token. Ex: {str(e)}")

    return token_sub
