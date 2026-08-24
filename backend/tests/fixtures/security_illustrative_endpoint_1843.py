import os
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from backend.app.auth import get_current_user, get_current_admin_user
from backend.app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import logging

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security settings
SECRET_KEY = os.getenv('SECRET_KEY')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost').split(',')

# Initialize FastAPI app
app = FastAPI()

# Middleware for HTTPS redirection
app.add_middleware(HTTPSRedirectMiddleware)

# Middleware for trusted hosts
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# Rate Limiting
@app.on_event("startup")
async def startup_event():
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        logger.error("REDIS_URL is not set. Rate limiting will not work.")
    else:
        await FastAPILimiter.init(redis_url)

# Security dependencies
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    # Here you would add logic to verify the token with your identity provider
    # For example, using Auth0's SDK to verify the token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token

# Example of a protected endpoint
@app.get("/protected-endpoint", dependencies=[Depends(get_current_user), Depends(RateLimiter(times=5, seconds=60))])
async def protected_endpoint():
    return {"message": "This is a protected endpoint."}

# Example of an admin-only endpoint
@app.get("/admin/protected-endpoint", dependencies=[Depends(get_current_admin_user), Depends(RateLimiter(times=5, seconds=60))])
async def admin_protected_endpoint():
    return {"message": "This is an admin-only protected endpoint."}

# Example of input validation
from pydantic import BaseModel, constr

class OrderRequest(BaseModel):
    customer_name: constr(min_length=1, max_length=100)
    customer_email: constr(min_length=5, max_length=100)
    order_details: dict
    total_amount: float
    tip_amount: float = 0.0

@app.post("/orders", dependencies=[Depends(get_current_user)])
async def create_order(order: OrderRequest, db: AsyncSession = Depends(get_db)):
    # Logic to create an order
    return {"message": "Order created successfully."}

# Ensure all secrets are read from environment variables
if not SECRET_KEY:
    logger.error("SECRET_KEY is not set. The application will not start.")
    raise RuntimeError("SECRET_KEY is not set.")

# Ensure HTTPS is enforced
if not os.getenv('FORCE_HTTPS', 'true').lower() in ('true', '1', 'yes'):
    logger.warning("HTTPS is not enforced. This is not recommended for production.")
