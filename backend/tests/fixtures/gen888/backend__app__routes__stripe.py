import os
import hmac
import hashlib
import secrets
import base64
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.app.models import StripeAccount
from backend.app.database import get_db
from backend.app.auth import get_current_admin_user
from cryptography.fernet import Fernet
import httpx

router = APIRouter()

STRIPE_CLIENT_ID = os.getenv('STRIPE_CLIENT_ID')
STRIPE_TOKEN_ENC_KEY = os.getenv('STRIPE_TOKEN_ENC_KEY')
STRIPE_STATE_SIGNING_KEY = os.getenv('STRIPE_STATE_SIGNING_KEY')
STRIPE_REDIRECT_URI = os.getenv('STRIPE_REDIRECT_URI')
STRIPE_API_BASE = 'https://connect.stripe.com'

if not STRIPE_CLIENT_ID or not STRIPE_TOKEN_ENC_KEY or not STRIPE_REDIRECT_URI:
    raise RuntimeError('Stripe environment variables are not set')

if not STRIPE_STATE_SIGNING_KEY:
    raise RuntimeError('STRIPE_STATE_SIGNING_KEY environment variable is not set')

fernet = Fernet(STRIPE_TOKEN_ENC_KEY)

_STATE_SIGNING_KEY_BYTES = STRIPE_STATE_SIGNING_KEY.encode()


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign_state(payload: dict) -> str:
    payload_bytes = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
    payload_b64 = _b64url_encode(payload_bytes)
    signature = hmac.new(_STATE_SIGNING_KEY_BYTES, payload_b64.encode(), hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{payload_b64}.{signature_b64}"


def _verify_state(state: str) -> dict:
    try:
        payload_b64, signature_b64 = state.split('.', 1)
        expected_sig = hmac.new(_STATE_SIGNING_KEY_BYTES, payload_b64.encode(), hashlib.sha256).digest()
        provided_sig = _b64url_decode(signature_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise ValueError('Signature mismatch')
        payload = json.loads(_b64url_decode(payload_b64))
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid state parameter')


@router.get('/admin/stripe/connect')
async def stripe_connect(request: Request, current_user=Depends(get_current_admin_user)):
    try:
        session = request.session
    except (AssertionError, KeyError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Session is not available')

    nonce = secrets.token_urlsafe(32)
    session['stripe_oauth_nonce'] = nonce

    payload = {'nonce': nonce, 'user_id': str(current_user.id)}
    state = _sign_state(payload)

    redirect_url = (
        f"{STRIPE_API_BASE}/oauth/authorize?response_type=code&client_id={STRIPE_CLIENT_ID}"
        f"&scope=read_write&state={state}&redirect_uri={STRIPE_REDIRECT_URI}"
    )
    return RedirectResponse(url=redirect_url)


@router.get('/admin/stripe/callback')
async def stripe_callback(request: Request, code: str = None, state: str = None, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_admin_user)):
    if code is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Missing code parameter')
    if state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Missing state parameter')

    try:
        session = request.session
    except (AssertionError, KeyError, AttributeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Session is not available')

    payload = _verify_state(state)

    stored_nonce = session.get('stripe_oauth_nonce')
    state_nonce = payload.get('nonce')
    if not stored_nonce or not state_nonce or not hmac.compare_digest(str(stored_nonce), str(state_nonce)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid state parameter')

    # Invalidate the nonce after use to prevent replay.
    session.pop('stripe_oauth_nonce', None)

    # Ensure the state was issued for the currently authenticated admin.
    if str(payload.get('user_id')) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid state parameter')

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{STRIPE_API_BASE}/oauth/token",
                data={
                    'client_secret': os.getenv('STRIPE_SECRET_KEY'),
                    'code': code,
                    'grant_type': 'authorization_code',
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail='Failed to exchange code')
        except httpx.RequestError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Network error while contacting Stripe')

        token_data = response.json()
        encrypted_access_token = fernet.encrypt(token_data['access_token'].encode()).decode()
        encrypted_refresh_token = fernet.encrypt(token_data['refresh_token'].encode()).decode()

        result = await db.execute(
            select(StripeAccount).where(StripeAccount.user_id == current_user.id)
        )
        stripe_account = result.scalar_one_or_none()

        if stripe_account is None:
            stripe_account = StripeAccount(
                user_id=current_user.id,
                stripe_account_id=token_data['stripe_user_id'],
                access_token_encrypted=encrypted_access_token,
                refresh_token_encrypted=encrypted_refresh_token,
                scope=token_data['scope'],
                connected=True,
                created_at=token_data['created_at'],
            )
            db.add(stripe_account)
        else:
            stripe_account.stripe_account_id = token_data['stripe_user_id']
            stripe_account.access_token_encrypted = encrypted_access_token
            stripe_account.refresh_token_encrypted = encrypted_refresh_token
            stripe_account.scope = token_data['scope']
            stripe_account.connected = True
            stripe_account.created_at = token_data['created_at']

        await db.commit()

    return JSONResponse(status_code=status.HTTP_200_OK, content={'message': 'Stripe account connected successfully'})


@router.get('/admin/stripe/status')
async def stripe_status(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_admin_user)):
    result = await db.execute(
        select(StripeAccount).where(StripeAccount.user_id == current_user.id)
    )
    stripe_account = result.scalar_one_or_none()
    if stripe_account and stripe_account.connected:
        return JSONResponse(status_code=status.HTTP_200_OK, content={'connected': True})
    return JSONResponse(status_code=status.HTTP_200_OK, content={'connected': False})

