
import requests
import jwt
import jwt.algorithms

from tesp_api.service.error import OAuth2TokenError

def verify_token(token):
    """
    WARNING: Verify validity of given JWT token for OAuth2.
    Accepts any valid tokens from any issuer including owns!
    Expects optional JWT parameters!
    """

    # Decode without verification to obtain usefull data
    try:
        token_header = jwt.get_unverified_header(token)
        token_payload = jwt.decode(token, options={"verify_signature": False})
    except Exception as e:
        raise OAuth2TokenError(f"Failed to decode token. Ex: {str(e)}")

    # Obtain desired data
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

    # Obtain issuer public key to verify the token
    try:
        response = requests.get(token_iss)
    except Exception as e:
        raise OAuth2TokenError("Contacting the token issuer failed.")

    if response.status_code != 200:
        raise OAuth2TokenError(f"Contacting the token issuer returns HTTP code {response.status_code}.")

    try:
        issuer_data = response.json()
    except requests.exceptions.JSONDecodeError as e:
        raise OAuth2TokenError("Failed to parse response from token issuer.")

    issuer_public = issuer_data.get('public_key')
    if not issuer_public:
        raise OAuth2TokenError("Failed to obtain issuer public key")

    # If the token does not contain the 'alg' parameter, try list of supported algorithms by the library
    if not token_alg:
        token_alg = list(jwt.algorithms.get_default_algorithms().keys())

    # Wrap the token to the standard format
    issuer_public = f"-----BEGIN PUBLIC KEY-----\n{issuer_public}\n-----END PUBLIC KEY-----"

    # Verify the token
    try:
        jwt.decode(
            token,
            key = issuer_public,
            algorithms = token_alg,
            issuer = token_iss
        )
    except Exception as e:
        raise OAuth2TokenError(f"Failed to verify token. Ex: {str(e)}")

    return token_sub
