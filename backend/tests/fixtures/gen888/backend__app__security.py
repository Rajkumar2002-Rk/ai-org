import os
import logging
import time
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.ratelimit import RateLimitMiddleware
from cryptography.fernet import Fernet
import jwt

logger = logging.getLogger(__name__)

# Read secrets from environment variables
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY environment variable is not set')

FERNET_KEY = os.getenv('FERNET_KEY')
if not FERNET_KEY:
    raise RuntimeError('FERNET_KEY environment variable is not set')

JWT_SECRET = os.getenv('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError('JWT_SECRET environment variable is not set')

JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_ISSUER = os.getenv('JWT_ISSUER')
if not JWT_ISSUER:
    raise RuntimeError('JWT_ISSUER environment variable is not set')

JWT_AUDIENCE = os.getenv('JWT_AUDIENCE')

fernet = Fernet(FERNET_KEY)

# Initialize FastAPI app
app = FastAPI()

# Middleware for HTTPS redirection
app.add_middleware(HTTPSRedirectMiddleware)

# Middleware for trusted hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["example.com", "*.example.com"]
)

# Middleware for CORS
# Tightened allowed methods/headers for credentialed requests instead of wildcards.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"]
)

# Middleware for GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Middleware for session management
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Middleware for rate limiting
app.add_middleware(
    RateLimitMiddleware,
    rate_limit="100/hour"
)

# Security scheme for HTTP Bearer authentication
security = HTTPBearer()

# Function to encrypt sensitive data
def encrypt_data(data: str) -> str:
    try:
        return fernet.encrypt(data.encode()).decode()
    except Exception as e:
        # Do not leak internal cryptography error details to the client.
        logger.exception("Encryption failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process request"
        )

# Function to decrypt sensitive data
def decrypt_data(data: str) -> str:
    try:
        return fernet.decrypt(data.encode()).decode()
    except Exception as e:
        # Do not leak internal cryptography error details (padding/decrypt oracle).
        logger.exception("Decryption failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to process request"
        )

# Dependency to validate the bearer token and return the authenticated identity.
async def enforce_authorization(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    decode_kwargs = {
        "algorithms": [JWT_ALGORITHM],
        "issuer": JWT_ISSUER,
        "options": {"require": ["exp", "iss", "sub"]},
    }
    if JWT_AUDIENCE:
        decode_kwargs["audience"] = JWT_AUDIENCE

    try:
        payload = jwt.decode(token, JWT_SECRET, **decode_kwargs)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        # Signature, issuer, audience, or claim validation failed.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return payload

# Authorization check binding the token identity to the resource owner.
def enforce_object_ownership(current_subject: str, resource_owner: str):
    if not current_subject or current_subject != resource_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this resource"
        )

# Example usage of encryption with per-user ownership binding.
async def store_sensitive_data(data: str, owner: str, current_subject: str):
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input data cannot be empty or None")
    enforce_object_ownership(current_subject, owner)
    encrypted_data = encrypt_data(data)
    # Store encrypted_data in the database associated with `owner`.
    return encrypted_data

# Example usage of decryption with per-user ownership binding.
async def retrieve_sensitive_data(encrypted_data: str, owner: str, current_subject: str) -> str:
    if not encrypted_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Encrypted data cannot be empty or None")
    enforce_object_ownership(current_subject, owner)
    return decrypt_data(encrypted_data)

# Example endpoint with authorization
@app.get("/secure-endpoint")
async def secure_endpoint(payload: dict = Depends(enforce_authorization)):
    return {"message": "This is a secure endpoint", "user": payload.get("sub")}

