import os
import io
import html
import base64
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from backend.app.models import MenuItem
from backend.app.database import get_db
from backend.app.auth import get_current_admin_user
from anthropic import Anthropic
import pdfplumber

router = APIRouter()

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
CHUNK_SIZE = 64 * 1024  # 64 KB

# A menu arrives either as a PDF (a real text layer, OR a scanned/image-only PDF)
# or as a photo of the menu. The endpoint accepts exactly those and routes each to
# the right extractor, so the "scanned menu" path actually accepts what it claims.
PDF_CONTENT_TYPE = 'application/pdf'
PDF_MAGIC = b'%PDF-'
IMAGE_MAGIC = {
    'image/jpeg': b'\xff\xd8\xff',
    'image/png': b'\x89PNG\r\n\x1a\n',
    'image/webp': b'RIFF',
    'image/gif': b'GIF8',
}

# A real, current Claude model that supports both text and vision (images + PDFs).
MENU_EXTRACTION_MODEL = 'claude-haiku-4-5-20251001'

MAX_NAME_LEN = 200
MAX_CATEGORY_LEN = 100
MAX_DESCRIPTION_LEN = 2000
MAX_PRICE = Decimal('100000')

_EXTRACTION_SYSTEM = (
    "You extract the items from a restaurant menu. Return ONLY a JSON array; each "
    'element is an object {"name": string, "price": number, "category": string, '
    '"description": string}. Use the prices exactly as they appear. Infer a '
    'reasonable category (e.g. Starter, Pasta, Main, Dessert, Drink) when the menu '
    'gives none. Use "" for a missing description. Output nothing but the JSON array '
    "— no prose, no explanation, no markdown code fences."
)


@router.post("/admin/menu/upload", dependencies=[Depends(get_current_admin_user)])
async def upload_menu(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content_type = file.content_type
    if content_type != PDF_CONTENT_TYPE and content_type not in IMAGE_MAGIC:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a PDF, or a photo/scan of your "
                   "menu as an image (JPEG, PNG, WebP or GIF).",
        )

    # Read the file in bounded chunks to enforce the size limit reliably.
    file_bytes = await _read_bounded(file)

    # Validate real content via magic bytes rather than trusting the client-supplied
    # Content-Type header, which is trivially spoofable.
    if content_type == PDF_CONTENT_TYPE:
        if not file_bytes.startswith(PDF_MAGIC):
            raise HTTPException(status_code=400, detail="Invalid file content. Only valid PDFs are allowed.")
    elif not file_bytes.startswith(IMAGE_MAGIC[content_type]):
        raise HTTPException(status_code=400, detail="Invalid image content for the declared type.")

    filename = sanitize_filename(file.filename)

    try:
        menu_items = extract_menu_items(file_bytes, content_type)
        saved_count = await save_menu_items(menu_items, db)

        return JSONResponse(content={
            "message": "Menu uploaded and processed successfully. Items require admin review before publishing.",
            "filename": filename,
            "pending_review_count": saved_count,
        })
    except HTTPException:
        raise
    except Exception as e:
        # Do not leak internal exception details to the client.
        logger.exception("Failed to process uploaded menu: %s", e)
        raise HTTPException(status_code=500, detail="Failed to process the uploaded file.")


async def _read_bounded(file: UploadFile) -> bytes:
    """Read the uploaded file in bounded chunks, enforcing MAX_FILE_SIZE."""
    await file.seek(0)
    buffer = bytearray()
    total = 0
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds the maximum limit of 5 MB.",
            )
        buffer.extend(chunk)
    return bytes(buffer)


def sanitize_filename(filename: str) -> str:
    return os.path.basename(filename or "")


def _client() -> Anthropic:
    return Anthropic(api_key=os.environ['MENU_EXTRACTION_API_KEY'])


def _items_from_response(resp) -> list:
    """Pull the JSON array of items out of a Claude messages response, tolerating an
    accidental code fence. Never raises — malformed output yields an empty list so a
    bad model reply degrades gracefully instead of 500-ing."""
    try:
        raw = (resp.content[0].text or "").strip()
    except (AttributeError, IndexError):
        return []
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ''.join(page.extract_text() or '' for page in pdf.pages)
        return text
    except Exception:
        return ''


def parse_menu_items(text: str) -> list:
    """Parse extracted menu TEXT into structured items with the extraction model.

    This is REAL parsing logic: it sends the text to the model and returns the
    structured items it reads back. It must never be a placeholder that blindly
    returns an empty list — an empty result here means the menu genuinely had no
    items, not that parsing was left unimplemented.
    """
    if not text or not text.strip():
        return []
    resp = _client().messages.create(
        model=MENU_EXTRACTION_MODEL, max_tokens=4000, system=_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": f"Menu text:\n\n{text}"}],
    )
    return _items_from_response(resp)


def extract_items_from_image(image_bytes: bytes, media_type: str) -> list:
    """Read a menu PHOTO/image with the vision model and return structured items."""
    b64 = base64.standard_b64encode(image_bytes).decode('utf-8')
    resp = _client().messages.create(
        model=MENU_EXTRACTION_MODEL, max_tokens=4000, system=_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": "Extract every item from this menu image."},
        ]}],
    )
    return _items_from_response(resp)


def extract_items_from_scanned_pdf(pdf_bytes: bytes) -> list:
    """A scanned / image-only PDF has no text layer, so hand the PDF itself to the
    model (which reads it visually) rather than mis-treating PDF bytes as an image."""
    b64 = base64.standard_b64encode(pdf_bytes).decode('utf-8')
    resp = _client().messages.create(
        model=MENU_EXTRACTION_MODEL, max_tokens=4000, system=_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
            {"type": "text", "text": "Extract every item from this menu document."},
        ]}],
    )
    return _items_from_response(resp)


def extract_menu_items(file_bytes: bytes, content_type: str) -> list:
    """Route the upload to the right extractor: a PDF with a text layer is parsed
    from its text; a scanned/image-only PDF is read as a document; an uploaded image
    is read with vision."""
    if content_type == PDF_CONTENT_TYPE:
        text = extract_text_from_pdf(file_bytes)
        if text and text.strip():
            return parse_menu_items(text)
        return extract_items_from_scanned_pdf(file_bytes)
    return extract_items_from_image(file_bytes, content_type)


def _validate_and_coerce_item(item: dict):
    """Validate and sanitize a single untrusted parsed/LLM-derived menu item.

    Returns a sanitized dict or None if the item is invalid and should be skipped.
    """
    if not isinstance(item, dict):
        return None

    name = item.get('name')
    category = item.get('category')
    description = item.get('description')
    price_raw = item.get('price')

    # Name is required.
    if not isinstance(name, str):
        return None
    name = html.escape(name.strip())
    if not name or len(name) > MAX_NAME_LEN:
        return None

    # Category (optional).
    if category is None:
        category = ''
    elif isinstance(category, str):
        category = html.escape(category.strip())[:MAX_CATEGORY_LEN]
    else:
        return None

    # Description (optional).
    if description is None:
        description = ''
    elif isinstance(description, str):
        description = html.escape(description.strip())[:MAX_DESCRIPTION_LEN]
    else:
        return None

    # Price must be coercible to a non-negative number within a sane range.
    try:
        if isinstance(price_raw, bool):
            return None
        if isinstance(price_raw, (int, float, str, Decimal)):
            price = Decimal(str(price_raw).strip())
        else:
            return None
    except (InvalidOperation, ValueError, TypeError):
        return None

    if not price.is_finite() or price < 0 or price > MAX_PRICE:
        return None
    # Normalize to two decimal places.
    price = price.quantize(Decimal('0.01'))

    return {
        'name': name,
        'price': price,
        'category': category,
        'description': description,
    }


async def save_menu_items(menu_items: list, db: AsyncSession) -> int:
    try:
        saved = 0
        # The MenuItem.created_at column is a naive TIMESTAMP (no tz), so store a
        # naive UTC value — a tz-aware datetime is rejected by that column type.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for item in menu_items:
            validated = _validate_and_coerce_item(item)
            if validated is None:
                logger.warning("Skipping invalid parsed menu item.")
                continue
            menu_item = MenuItem(
                name=validated['name'],
                price=validated['price'],
                category=validated['category'],
                description=validated['description'],
                # All uploaded/LLM-derived items must be human-reviewed before
                # being published.
                status='pending_review',
                source_name='pdf',
                created_at=now,
            )
            db.add(menu_item)
            saved += 1
        await db.commit()
        return saved
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred while saving menu items.")


@router.get("/admin/menu/pending", dependencies=[Depends(get_current_admin_user)])
async def get_pending_menu_items(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(MenuItem).where(MenuItem.status == 'pending_review'))
        items = result.scalars().all()
        return items
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Failed to retrieve pending menu items.")


@router.post("/admin/menu/confirm", dependencies=[Depends(get_current_admin_user)])
async def confirm_menu_items(item_ids: list[int], db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(MenuItem).where(
                MenuItem.id.in_(item_ids),
                MenuItem.status == 'pending_review',
            )
        )
        items = result.scalars().all()
        for item in items:
            item.status = 'published'
        await db.commit()
        return JSONResponse(content={"message": "Menu items published successfully.", "published_count": len(items)})
    except SQLAlchemyError:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to publish menu items.")

