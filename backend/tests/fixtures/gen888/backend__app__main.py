import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routes.menu import router as menu_router
from backend.app.routes.menu_upload import router as menu_upload_router

app = FastAPI()

allowed_origins = os.getenv('ALLOWED_ORIGINS')
if not allowed_origins:
    raise RuntimeError('ALLOWED_ORIGINS environment variable is not set')
allowed_origins_list = allowed_origins.split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(menu_router)
app.include_router(menu_upload_router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

