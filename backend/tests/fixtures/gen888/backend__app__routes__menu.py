from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, constr, condecimal
from typing import List, Optional
from backend.app.models import MenuItem
from backend.app.database import get_db
from backend.app.auth import get_current_admin_user
from fastapi import Query
from datetime import datetime

router = APIRouter()

# Pydantic schemas
class MenuItemBase(BaseModel):
    name: constr(min_length=1, max_length=255)
    price: condecimal(gt=0)
    category: constr(min_length=1, max_length=255)
    description: constr(min_length=0, max_length=1000)

class MenuItemCreate(MenuItemBase):
    pass

class MenuItemUpdate(MenuItemBase):
    status: constr(min_length=1, max_length=50)

class MenuItemResponse(MenuItemBase):
    id: int
    status: str
    source_name: str

# GET /menu - Public: list PUBLISHED menu items for customers
@router.get('/menu', response_model=List[MenuItemResponse])
async def get_published_menu_items(skip: int = Query(0, ge=0), limit: int = Query(10, gt=0), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.status == 'published').offset(skip).limit(limit))
        items = result.scalars().all()
        return items
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve menu items")

# GET /admin/menu - Owner: list all menu items
@router.get('/admin/menu', response_model=List[MenuItemResponse], dependencies=[Depends(get_current_admin_user)])
async def get_all_menu_items(skip: int = Query(0, ge=0), limit: int = Query(10, gt=0), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(MenuItem).offset(skip).limit(limit))
        items = result.scalars().all()
        return items
    except SQLAlchemyError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve menu items")

# POST /admin/menu - Owner: add a menu item manually (published)
@router.post('/admin/menu', response_model=MenuItemResponse, dependencies=[Depends(get_current_admin_user)])
async def create_menu_item(item: MenuItemCreate, db: AsyncSession = Depends(get_db)):
    if not item.name or not item.category or item.price <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data")
    new_item = MenuItem(
        name=item.name,
        price=str(item.price),
        category=item.category,
        description=item.description,
        status='published',
        source='manual',
        created_at=datetime.utcnow()
    )
    db.add(new_item)
    try:
        await db.commit()
        await db.refresh(new_item)
        return new_item
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create menu item")

# PUT /admin/menu/{item_id} - Owner: edit a menu item
@router.put('/admin/menu/{item_id}', response_model=MenuItemResponse, dependencies=[Depends(get_current_admin_user)])
async def update_menu_item(item_id: int, item: MenuItemUpdate, db: AsyncSession = Depends(get_db)):
    if not item.name or not item.category or item.price <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid input data")
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
        menu_item = result.scalar_one_or_none()
        if menu_item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")

        menu_item.name = item.name
        menu_item.price = str(item.price)
        menu_item.category = item.category
        menu_item.description = item.description
        menu_item.status = item.status
        await db.commit()
        await db.refresh(menu_item)
        return menu_item
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update menu item")

# DELETE /admin/menu/{item_id} - Owner: delete a menu item
@router.delete('/admin/menu/{item_id}', status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_current_admin_user)])
async def delete_menu_item(item_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.id == item_id))
        menu_item = result.scalar_one_or_none()
        if menu_item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found")

        await db.delete(menu_item)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not delete menu item")
