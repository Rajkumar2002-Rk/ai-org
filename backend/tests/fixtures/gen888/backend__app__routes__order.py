from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field, condecimal, constr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from backend.app.models import Order, Product
from backend.app.database import async_session
from backend.app.auth import get_current_user
from datetime import datetime
from decimal import Decimal
import json

router = APIRouter()

class OrderItem(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)

class OrderCreateRequest(BaseModel):
    items: list[OrderItem] = Field(min_items=1)

class OrderCreateResponse(BaseModel):
    id: int
    customer_name: str
    customer_email: str
    order_details: dict
    total_price: float
    status: str
    created_at: datetime
    updated_at: datetime

@router.post("/orders", response_model=OrderCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_order(order_request: OrderCreateRequest, db: AsyncSession = Depends(async_session), user: dict = Depends(get_current_user)):
    if not order_request.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order details cannot be empty")
    try:
        # Server-side price calculation against the product catalog.
        total_price = Decimal("0")
        computed_details = {"items": []}
        for item in order_request.items:
            result = await db.execute(select(Product).where(Product.id == item.product_id))
            product = result.scalar_one_or_none()
            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Product {item.product_id} not found"
                )
            unit_price = Decimal(str(product.price))
            line_total = unit_price * item.quantity
            total_price += line_total
            computed_details["items"].append({
                "product_id": product.id,
                "name": product.name,
                "unit_price": float(unit_price),
                "quantity": item.quantity,
                "line_total": float(line_total)
            })

        if total_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order total must be greater than zero"
            )

        # Bind the order to the authenticated user; derive identity fields
        # from the authenticated principal rather than the request body.
        new_order = Order(
            user_id=user["id"],
            customer_name=user.get("name") or user.get("username") or "",
            customer_email=user["email"],
            order_details=computed_details,
            total_price=total_price,
            status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(new_order)
        await db.commit()
        await db.refresh(new_order)
        return OrderCreateResponse(
            id=new_order.id,
            customer_name=new_order.customer_name,
            customer_email=new_order.customer_email,
            order_details=new_order.order_details,
            total_price=float(new_order.total_price),
            status=new_order.status,
            created_at=new_order.created_at,
            updated_at=new_order.updated_at
        )
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Validation error")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")

