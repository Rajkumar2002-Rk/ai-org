import os
import time
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2AuthorizationCodeBearer
from jose import JWTError, jwt
from pydantic import BaseModel, field_validator
from typing import Optional
import httpx

# Read Auth0 configuration from environment variables
AUTH0_DOMAIN = os.getenv('AUTH0_DOMAIN')
AUTH0_CLIENT_ID = os.getenv('AUTH0_CLIENT_ID')
AUTH0_CLIENT_SECRET = os.getenv('AUTH0_CLIENT_SECRET')
AUTH0_AUDIENCE = os.getenv('AUTH0_AUDIENCE')

if not all([AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, AUTH0_AUDIENCE]):
    raise RuntimeError('Auth0 environment variables are not set')

# OAuth2 scheme for Auth0
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=f'https://{AUTH0_DOMAIN}/authorize',
    tokenUrl=f'https://{AUTH0_DOMAIN}/oauth/token'
)

# Expected signing algorithm
EXPECTED_ALGORITHM = 'RS256'

# Pydantic model for token payload
class TokenPayload(BaseModel):
    sub: str
    email: Optional[str] = None
    permissions: list[str] = []

    @field_validator('permissions', mode='before')
    @classmethod
    def ensure_permissions_list(cls, v):
        # Enforce a non-null list even if the token includes 'permissions': null
        if v is None:
            return []
        return v

# Caching JWKS with TTL
JWKS_CACHE_TTL = 3600  # seconds
jwks_cache = None
jwks_cache_time = 0.0

async def _fetch_jwks_from_auth0():
    async with httpx.AsyncClient() as client:
        jwks_url = f'https://{AUTH0_DOMAIN}/.well-known/jwks.json'
        response = await client.get(jwks_url)
        response.raise_for_status()
        return response.json()

async def fetch_jwks(force_refresh: bool = False):
    global jwks_cache, jwks_cache_time
    now = time.monotonic()
    is_expired = (now - jwks_cache_time) >= JWKS_CACHE_TTL
    if jwks_cache is None or force_refresh or is_expired:
        try:
            jwks_cache = await _fetch_jwks_from_auth0()
            jwks_cache_time = now
        except httpx.HTTPStatusError as e:
            # If we have a stale cache, keep serving it rather than failing hard
            if jwks_cache is not None and not force_refresh:
                return jwks_cache
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail='Failed to fetch JWKS',
            ) from e
    return jwks_cache

def _find_rsa_key(jwks: dict, kid: str):
    return next((key for key in jwks['keys'] if key['kid'] == kid), None)

async def decode_token(token: str, rsa_key: dict) -> TokenPayload:
    payload = jwt.decode(
        token,
        rsa_key,
        algorithms=[EXPECTED_ALGORITHM],
        audience=AUTH0_AUDIENCE,
        issuer=f'https://{AUTH0_DOMAIN}/'
    )
    return TokenPayload(**payload)

# Function to verify JWT token
async def verify_token(token: str) -> TokenPayload:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Token is empty or malformed',
        )
    try:
        # Inspect unverified header
        unverified_header = jwt.get_unverified_header(token)

        # Validate the header 'alg' matches the expected algorithm before use
        if unverified_header.get('alg') != EXPECTED_ALGORITHM:
            raise JWTError('Unexpected token algorithm')

        kid = unverified_header.get('kid')
        if not kid:
            raise JWTError('Token header missing kid')

        # Fetch JWKS (cached with TTL)
        jwks = await fetch_jwks()
        rsa_key = _find_rsa_key(jwks, kid)

        # If the kid is unknown, keys may have rotated: force a refresh and retry
        if rsa_key is None:
            jwks = await fetch_jwks(force_refresh=True)
            rsa_key = _find_rsa_key(jwks, kid)

        if rsa_key:
            return await decode_token(token, {
                'kty': rsa_key['kty'],
                'kid': rsa_key['kid'],
                'use': rsa_key['use'],
                'n': rsa_key['n'],
                'e': rsa_key['e']
            })
        else:
            raise JWTError('RSA key not found')
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Could not validate credentials',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from e

# Dependency to get the current user
async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    return await verify_token(token)

# Dependency to get the current admin user
async def get_current_admin_user(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
    permissions = current_user.permissions or []
    if 'admin' not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Not enough permissions'
        )
    return current_user

