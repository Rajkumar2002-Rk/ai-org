import os
import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from backend.app.models import StripeAccount, StripeOAuthState
from backend.app.database import get_db
from backend.app.auth import get_current_admin_user
from cryptography.fernet import Fernet
import httpx
import secrets

logger = logging.getLogger(__name__)

router = APIRouter()

STRIPE_CLIENT_ID = os.getenv('STRIPE_CLIENT_ID')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_TOKEN_ENC_KEY = os.getenv('STRIPE_TOKEN_ENC_KEY')
STRIPE_API_BASE = 'https://connect.stripe.com'
STATE_TTL_MINUTES = 10

if not STRIPE_CLIENT_ID or not STRIPE_SECRET_KEY or not STRIPE_TOKEN_ENC_KEY:
    raise RuntimeError('Stripe configuration is incomplete.')

def encrypt_token(token: str) -> str:
    fernet = Fernet(STRIPE_TOKEN_ENC_KEY.encode())
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    fernet = Fernet(STRIPE_TOKEN_ENC_KEY.encode())
    return fernet.decrypt(encrypted_token.encode()).decode()

@router.get('/admin/stripe/connect')
async def stripe_connect(
    current_user=Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    state = secrets.token_urlsafe(32)  # Securely generate a random state

    # Persist the state tied to the authenticated admin so it can be
    # validated on callback (CSRF protection).
    oauth_state = StripeOAuthState(
        state=state,
        user_id=current_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)
    )
    db.add(oauth_state)
    await db.commit()

    redirect_uri = f'{STRIPE_API_BASE}/oauth/authorize?response_type=code&client_id={STRIPE_CLIENT_ID}&scope=read_write&state={state}'
    return {'redirect_uri': redirect_uri}

@router.get('/admin/stripe/callback')
async def stripe_callback(
    request: Request,
    current_user=Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    code = request.query_params.get('code')
    state = request.query_params.get('state')

    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid request parameters: code or state is missing.')

    # Validate the returned state against a stored value tied to the admin
    # session (CSRF protection).
    state_result = await db.execute(
        select(StripeOAuthState).where(StripeOAuthState.state == state)
    )
    stored_state = state_result.scalars().first()

    if stored_state is None or stored_state.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid or unknown OAuth state.')

    expires_at = stored_state.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.delete(stored_state)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='OAuth state has expired.')

    # Consume the state so it cannot be reused.
    await db.delete(stored_state)
    await db.commit()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'{STRIPE_API_BASE}/oauth/token',
                data={
                    'client_id': STRIPE_CLIENT_ID,
                    'client_secret': STRIPE_SECRET_KEY,
                    'grant_type': 'authorization_code',
                    'code': code
                }
            )
            response.raise_for_status()
            token_data = response.json()

            if 'access_token' not in token_data or 'refresh_token' not in token_data:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Token exchange failed: access_token or refresh_token not found.')

            encrypted_access_token = encrypt_token(token_data['access_token'])
            encrypted_refresh_token = encrypt_token(token_data['refresh_token'])

            stripe_account = StripeAccount(
                user_id=current_user.id,
                stripe_account_id=token_data['stripe_user_id'],
                access_token_encrypted=encrypted_access_token,
                refresh_token_encrypted=encrypted_refresh_token,
                scope=token_data['scope'],
                connected=True
            )

            db.add(stripe_account)
            await db.commit()

    except HTTPException:
        raise
    except httpx.HTTPStatusError:
        # Do not log response bodies as they may contain sensitive token data.
        logger.warning('Stripe token exchange returned an HTTP error status.')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Failed to exchange code for token: HTTP error.')
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Stripe account already connected.')
    except Exception:
        # Never log token_data or response bodies to avoid leaking secrets.
        await db.rollback()
        logger.error('Unexpected error during Stripe OAuth callback.')
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Internal server error.')

    return {'detail': 'Stripe account connected successfully.'}

@router.get('/admin/stripe/status')
async def stripe_status(
    current_user=Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        result = await db.execute(
            select(StripeAccount).where(
                StripeAccount.connected == True,
                StripeAccount.user_id == current_user.id
            )
        )
        stripe_account = result.scalars().first()

        if stripe_account:
            return {'connected': True}
        else:
            return {'connected': False}

    except Exception:
        logger.error('Unexpected error while checking Stripe status.')
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Internal server error.')

