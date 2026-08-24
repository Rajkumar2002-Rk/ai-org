from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.app.models import Order
from backend.app.database import get_db
from pydantic import BaseModel, EmailStr, condecimal, constr
from typing import Any

router = APIRouter()


class OrderCreate(BaseModel):
    customer_name: constr(min_length=1)
    customer_email: EmailStr
    order_details: dict
    total_amount: condecimal(gt=0)
    tip_amount: condecimal(ge=0) = 0
    payment_status: constr(min_length=1)


class OrderResponse(BaseModel):
    id: int
    customer_name: str
    customer_email: str
    order_details: dict
    total_amount: float
    tip_amount: float
    payment_status: str
    created_at: Any


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/orders", response_model=OrderResponse)
async def create_order(order: OrderCreate, db: AsyncSession = Depends(get_db)):
    new_order = Order(
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        order_details=order.order_details,
        total_amount=order.total_amount,
        tip_amount=order.tip_amount,
        payment_status=order.payment_status
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)
    return new_order
