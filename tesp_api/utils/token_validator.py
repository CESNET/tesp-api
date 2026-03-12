import requests
import posixpath
import jwt
import jwt.algorithms
from jwt import PyJWKClient, PyJWKClientError

from tesp_api.config.properties import properties
from tesp_api.service.error import OAuth2TokenError


# Cache JWKS clients to avoid repeated HTTP requests
_jwks_cache: dict = {}


def _get_allowed_issuers() -> list:
    """
    Get list of allowed token issuers from configuration.
    Returns empty list if not configured (security enforcement happens elsewhere).
    """
    # Dynaconf may return different types, handle both string and list
    issuers = getattr(properties.oauth, 'allowed_issuers', [])
    if isinstance(issuers, str):
        return [issuers] if issuers else []
    return issuers if issuers else []


def _get_required_audience() -> str | None:
    """
    Get required audience for token validation.
    May be None indicating no audience check is required.
    """
    return getattr(properties.oauth, 'required_audience', None)


def _get_cached_jwks_client(issuer_jwk_uri: str, ttl_seconds: int = 300) -> PyJWKClient:
    """
    Get or create a cached JWKS client for the given issuer's JWKS URI.
    Cache reduces HTTP requests to the identity provider.

    Args:
        issuer_jwk_uri: The JWKS endpoint URI
        ttl_seconds: Time-to-live for cache entries (default 5 minutes)

    Returns:
        PyJWKClient instance
    """
    import time

    cache_entry = _jwks_cache.get(issuer_jwk_uri)
    current_time = time.time()

    # Return cached client if still valid
    if cache_entry and (current_time - cache_entry['timestamp']) < ttl_seconds:
        return cache_entry['client']

    # Create new client
    client = PyJWKClient(issuer_jwk_uri)
    _jwks_cache[issuer_jwk_uri] = {
        'client': client,
        'timestamp': current_time
    }

    return client


def verify_token(token: str) -> str:
    """
    Verify OAuth2 JWT token with strict security validation.

    Security features:
    - Enforces allow-list of trusted issuers (prevents malicious issuers)
    - Validates token signature using issuer's public keys (JWKS)
    - Verifies token expiration, not-before, and issued-at claims
    - Verifies audience when configured
    - Enforces algorithm restrictions (RS256 or better for security)
    - Caches JWKS to reduce network calls and improve performance

    Args:
        token: JWT token string to verify

    Returns:
        Token subject ('sub' claim) if valid

    Raises:
        OAuth2TokenError: If token is invalid, malformed, or from untrusted issuer
    """
    # Get security configuration
    allowed_issuers = _get_allowed_issuers()
    required_audience = _get_required_audience()

    # Phase 1: Decode without verification to extract claims
    # ====================================================
    try:
        token_header = jwt.get_unverified_header(token)
        token_payload = jwt.decode(token, options={"verify_signature": False})
    except Exception as e:
        raise OAuth2TokenError(f"Failed to decode token: {str(e)}")

    # Extract essential claims
    token_sub = token_payload.get('sub')
    token_iss = token_payload.get('iss')
    token_alg = token_header.get('alg')

    # Validate required claims
    if not token_sub:
        raise OAuth2TokenError("Missing 'sub' (subject) claim in token payload.")

    if not token_iss:
        raise OAuth2TokenError("Missing 'iss' (issuer) claim in token payload.")

    # Phase 2: Security - Verify issuer is in allow-list
    # ==================================================
    # This prevents attackers from using tokens from their own identity providers
    if allowed_issuers and token_iss not in allowed_issuers:
        raise OAuth2TokenError(
            f"Unauthorized token issuer '{token_iss}'. "
            f"Token must be from one of the following trusted issuers: {allowed_issuers}"
        )

    # Phase 3: Fetch issuer's signing keys (JWKS)
    # ==========================================
    # First, get the OpenID Connect configuration
    issuer_wk_config_url = posixpath.join(token_iss, ".well-known/openid-configuration")

    try:
        response = requests.get(
            issuer_wk_config_url,
            timeout=10,
            headers={'Accept': 'application/json'}
        )
        response.raise_for_status()
        issuer_wk_config_data = response.json()
    except requests.exceptions.RequestException as e:
        raise OAuth2TokenError(
            f"Failed to contact token issuer's OpenID configuration at {issuer_wk_config_url}: {str(e)}"
        )

    # Extract JWKS URI from configuration
    issuer_jwk_uri = issuer_wk_config_data.get('jwks_uri')
    if not issuer_jwk_uri:
        raise OAuth2TokenError(
            f"Token issuer '{token_iss}' configuration missing 'jwks_uri' field."
        )

    # Phase 4: Get signing key from JWKS (with caching)
    # ================================================
    cache_ttl = getattr(properties.oauth, 'cache_jwks_ttl', 300)

    try:
        jwks_client = _get_cached_jwks_client(issuer_jwk_uri, ttl_seconds=cache_ttl)
        issuer_signing_key = jwks_client.get_signing_key_from_jwt(token).key
    except PyJWKClientError as e:
        raise OAuth2TokenError(
            f"Failed to obtain signing key from issuer's JWKS endpoint: {str(e)}"
        )
    except Exception as e:
        raise OAuth2TokenError(
            f"Unexpected error retrieving signing key: {str(e)}"
        )

    # Phase 5: Security - Enforce allowed algorithms
    # ==============================================
    # For security, prefer asymmetric algorithms (RS256, RS384, RS512, ES256, etc.)
    # Symmetric algorithms (HS256) should only be used with prior agreement
    if not token_alg:
        # If token doesn't specify algorithm, only allow secure defaults
        # Never accept all algorithms
        token_alg = ['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512']
    elif isinstance(token_alg, str):
        # Prevent use of insecure algorithms like 'none' or weak symmetric algorithms
        if token_alg.lower() == 'none':
            raise OAuth2TokenError(
                f"Token algorithm 'none' is not allowed for security reasons."
            )
        if token_alg.startswith('HS') and token_alg not in ['HS256', 'HS384', 'HS512']:
            raise OAuth2TokenError(
                f"Unsupported symmetric algorithm '{token_alg}'. "
                f"Only HS256, HS384, HS512 are allowed for symmetric signing."
            )

    # Phase 6: Complete token verification
    # =====================================
    verify_options = {
        "verify_signature": True,
        "verify_exp": True,       # Token expiration
        "verify_nbf": True,       # Not before time
        "verify_iat": True,       # Issued at time
        "verify_aud": required_audience is not None,  # Only verify if audience is configured
        "verify_iss": True,       # Issuer verification
        "require": ["exp", "iat", "sub", "iss"]  # Require essential claims
    }

    try:
        decoded = jwt.decode(
            token,
            key=issuer_signing_key,
            algorithms=token_alg,
            issuer=token_iss,
            audience=required_audience,
            options=verify_options
        )
    except jwt.ExpiredSignatureError:
        raise OAuth2TokenError("Token has expired.")
    except jwt.InvalidTokenError as e:
        raise OAuth2TokenError(f"Token verification failed: {str(e)}")
    except Exception as e:
        raise OAuth2TokenError(f"Unexpected error during token verification: {str(e)}")

    # Phase 7: Additional security checks
    # ===================================
    # Verify subject matches what was extracted earlier (should match)
    if decoded.get('sub') != token_sub:
        raise OAuth2TokenError("Token subject mismatch during verification.")

    return token_sub
