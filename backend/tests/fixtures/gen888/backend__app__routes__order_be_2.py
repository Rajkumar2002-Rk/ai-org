from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.app.models import Order
from backend.app.database import get_db
from backend.app.auth import get_current_user
from pydantic import BaseModel, Field

router = APIRouter()

class OrderResponse(BaseModel):
    id: int
    customer_name: str
    customer_email: str
    order_details: dict
    total_price: float
    status: str
    created_at: str
    updated_at: str

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if order_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid order_id provided"
        )
    try:
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalars().first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        # Broken object level authorization / IDOR protection:
        # Ensure the requesting user actually owns this order (or is an admin).
        is_admin = getattr(current_user, "is_admin", False)
        order_owner_id = getattr(order, "user_id", None)
        current_user_id = getattr(current_user, "id", None)

        if not is_admin and order_owner_id != current_user_id:
            # Return 404 rather than 403 to avoid leaking existence of the order.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        return OrderResponse(
            id=order.id,
            customer_name=order.customer_name,
            customer_email=order.customer_email,
            order_details=order.order_details,
            total_price=float(order.total_price),
            status=order.status,
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        if "timeout" in str(e) or "connection" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database connection error"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving the order"
        ) from e

