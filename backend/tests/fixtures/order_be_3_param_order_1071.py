from fastapi import APIRouter, HTTPException, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, constr
from backend.app.models import Order
from backend.app.database import get_db
from backend.app.auth import get_current_user

router = APIRouter()

class OrderUpdateRequest(BaseModel):
    status: constr(min_length=1, max_length=50)

@router.put("/orders/{order_id}", response_model=None)
async def update_order_status(
    order_id: int = Path(..., description="The ID of the order to update"),
    order_update: OrderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    try:
        # Fetch the order by ID
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalars().first()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Update the order status
        order.status = order_update.status
        await db.commit()

        return {"message": "Order status updated successfully"}

    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred") from e

