from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import router
from app.campus import router as campus_router
from app.config import get_settings
from app.db import initialize_database

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    initialize_database()
    yield


app = FastAPI(
    title="Recovr",
    description="Lost-and-found reporting with OpenCV-powered image matching.",
    version="0.1.0",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
upload_dir = get_settings().upload_dir
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")
app.include_router(router, prefix="/api")
app.include_router(router, prefix="/api/v1")
app.include_router(campus_router, prefix="/api")
app.include_router(campus_router, prefix="/api/v1")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "landing.html")


@app.get("/staff", response_class=HTMLResponse)
def staff_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "staff.html")


@app.get("/portal", response_class=HTMLResponse)
def portal_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "portal.html")


@app.get("/app", response_class=HTMLResponse)
def legacy_app(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if _wants_json(request):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
    return templates.TemplateResponse(request, "error.html", {"code": exc.status_code}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    logging.getLogger("recovr").exception("Unhandled error on %s", request.url.path)
    if _wants_json(request):
        return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)
    return templates.TemplateResponse(request, "error.html", {"code": 500}, status_code=500)


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "admin.html")


@app.get("/guide", response_class=HTMLResponse)
def guide_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "guide.html")
