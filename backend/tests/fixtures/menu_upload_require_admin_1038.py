"""Captured bug fixture — project 1038 (2026-08-13).

A fresh generation of the menu-upload route imported `require_admin` from
backend.app.auth, but auth.py exports ONLY `get_current_user` /
`get_current_admin_user` (AUTH_EXPORTS). The app died at boot with
`ImportError: cannot import name 'require_admin' from 'backend.app.auth'`.

Everything ELSE in this file imports real, exported symbols (get_db from
database, MenuItem from models) — so the symbol-resolution gate must flag the ONE
bad import and NOTHING else. Kept verbatim-shaped for the fix #16 regression test.
"""
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth import require_admin          # BUG: not an auth export
from backend.app.database import get_db              # OK
from backend.app.models import MenuItem              # OK

router = APIRouter(prefix="/admin/menu", tags=["menu"])
logger = logging.getLogger("menu_upload")


def parse_menu_items(text: str) -> list[dict]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        items.append({"name": line, "price": None})
    return items


@router.post("/upload")
async def upload_menu(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    text = io.BytesIO(raw).read().decode("utf-8", errors="ignore")
    parsed = parse_menu_items(text)
    for p in parsed:
        db.add(MenuItem(name=p["name"], status="pending_review",
                        created_at=datetime.now(timezone.utc)))
    await db.commit()
    return {"extracted": len(parsed)}
