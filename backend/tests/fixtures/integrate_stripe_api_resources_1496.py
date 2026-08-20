import os
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import Charge, StripeError
from stripe.api_resources import PaymentIntent
from backend.app.database import get_db
from backend.app.models import Order

router = APIRouter()

STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
STRIPE_CONNECTED_ACCOUNT_ID = os.getenv('STRIPE_CONNECTED_ACCOUNT_ID')

if not STRIPE_API_KEY:
    raise RuntimeError('STRIPE_API_KEY environment variable is not set')

# Initialize Stripe with the API key
import stripe
stripe.api_key = STRIPE_API_KEY

@router.post('/create-payment-intent')
async def create_payment_intent(order_id: int, db: AsyncSession = Depends(get_db)):
    """
    Create a payment intent for a given order.
    """
    # Retrieve the order from the database
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        # Create a payment intent
        payment_intent = PaymentIntent.create(
            amount=int(order.total_amount * 100),  # Convert to cents
            currency='usd',
            payment_method_types=['card'],
            stripe_account=STRIPE_CONNECTED_ACCOUNT_ID if STRIPE_CONNECTED_ACCOUNT_ID else None
        )
        return {'client_secret': payment_intent.client_secret}
    except StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

@router.post('/charge')
async def charge(order_id: int, payment_method_id: str, db: AsyncSession = Depends(get_db)):
    """
    Charge a customer for an order using a payment method.
    """
    # Retrieve the order from the database
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    try:
        # Confirm the payment intent
        payment_intent = PaymentIntent.confirm(
            payment_method_id,
            stripe_account=STRIPE_CONNECTED_ACCOUNT_ID if STRIPE_CONNECTED_ACCOUNT_ID else None
        )

        # Update order payment status
        order.payment_status = 'paid'
        db.add(order)
        await db.commit()

        return {'status': 'success', 'payment_intent': payment_intent.id}
    except StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {str(e)}")

import os
import logging
import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "orders@brewandbean.local")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

async def send_email(to_email: str, subject: str, body_text: str) -> bool:
    """
    Sends an email notification using SendGrid v3 Mail Send API.
    """
    if not SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY is not set. Skipping email delivery.")
        return False

    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "personalizations": [
            {
                "to": [{"email": to_email}]
            }
        ],
        "from": {"email": SENDGRID_FROM_EMAIL},
        "subject": subject,
        "content": [
            {
                "type": "text/plain",
                "value": body_text
            }
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            if response.status_code in (200, 201, 202):
                logger.info(f"Email successfully sent to {to_email}")
                return True
            else:
                logger.error(f"Failed to send email via SendGrid: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.exception(f"Exception occurred while sending email to {to_email}: {e}")
        return False


async def send_sms(to_phone: str, message_body: str) -> bool:
    """
    Sends an SMS notification using Twilio Messages API.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        logger.warning("Twilio credentials / phone number are not fully configured. Skipping SMS delivery.")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    data = {
        "To": to_phone,
        "From": TWILIO_PHONE_NUMBER,
        "Body": message_body
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                data=data,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=10.0
            )
            if response.status_code in (200, 201):
                logger.info(f"SMS successfully sent to {to_phone}")
                return True
            else:
                logger.error(f"Failed to send SMS via Twilio: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.exception(f"Exception occurred while sending SMS to {to_phone}: {e}")
        return False


async def send_order_confirmation_notifications(customer_email: str, customer_phone: str, order_id: int, total_amount: float) -> dict:
    """
    Orchestrates sending both Email and SMS notifications for a newly created coffee order.
    """
    if not customer_email:
        raise HTTPException(status_code=400, detail="Customer email is required for notifications.")

    subject = f"Order Confirmation #{order_id} - Brew and Bean"
    email_body = (
        f"Hello,\n\n"
        f"Thank you for ordering with Brew and Bean! Your order (#{order_id}) has been received "
        f"and is being prepared for pickup.\n\n"
        f"Total Amount: ${total_amount:.2f}\n\n"
        f"We will notify you when it's ready!"
    )

    email_sent = await send_email(customer_email, subject, email_body)

    sms_sent = False
    if customer_phone:
        sms_body = f"Brew and Bean: Order #{order_id} confirmed! Total: ${total_amount:.2f}. We're preparing your pickup order now."
        sms_sent = await send_sms(customer_phone, sms_body)
    else:
        logger.info("No customer phone number provided; skipping SMS notification.")

    return {
        "email_sent": email_sent,
        "sms_sent": sms_sent
    }

