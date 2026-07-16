import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="PM MVP Backend")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "pm-mvp-dev-session-secret"),
    same_site="lax",
    https_only=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
_STATIC_INDEX = _STATIC_DIR / "index.html"
_LOGIN_PATH = "/login"

_FRONTEND_PUBLIC_PATHS = {
    _LOGIN_PATH,
    "/favicon.ico",
    "/robots.txt",
}


class LoginRequest(BaseModel):
    username: str
    password: str


def _is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def _require_authenticated(request: Request) -> None:
    if not _is_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _resolve_static_file(path: str) -> Path:
    requested_path = path.strip("/")
    candidate = (_STATIC_DIR / requested_path).resolve()
    static_root = _STATIC_DIR.resolve()

    if candidate != static_root and static_root not in candidate.parents:
        raise HTTPException(status_code=404)

    return candidate


def _serve_frontend_path(path: str) -> FileResponse:
    candidate = _resolve_static_file(path)

    if candidate.is_dir():
        index_candidate = candidate / "index.html"
        if index_candidate.is_file():
            return FileResponse(index_candidate)

    html_candidate = candidate.with_suffix(".html")
    if html_candidate.is_file():
        return FileResponse(html_candidate)

    if candidate.is_file():
        return FileResponse(candidate)

    return FileResponse(_STATIC_INDEX)


def _frontend_path_from_request(full_path: str) -> str:
    normalized = full_path.strip("/")
    if not normalized:
        return "/"
    return f"/{normalized}"


def _is_frontend_asset_path(path: str) -> bool:
    return path.startswith("/_next/")


def _is_public_frontend_path(path: str) -> bool:
    return path in _FRONTEND_PUBLIC_PATHS or _is_frontend_asset_path(path)


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> dict[str, str | bool]:
    if payload.username != "user" or payload.password != "password":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    request.session["authenticated"] = True
    request.session["username"] = payload.username
    return {"authenticated": True, "username": payload.username}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    _require_authenticated(request)
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/auth/session")
def session_status(request: Request) -> dict[str, str | bool | None]:
    authenticated = _is_authenticated(request)
    username = request.session.get("username") if authenticated else None
    return {"authenticated": authenticated, "username": username}


@app.get("/", response_class=Response)
def read_root(request: Request) -> Response:
    if not _is_authenticated(request):
        return RedirectResponse(url=_LOGIN_PATH, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return _serve_frontend_path("")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@app.get("/{full_path:path}", response_class=Response)
def serve_frontend(full_path: str, request: Request) -> Response:
    request_path = _frontend_path_from_request(full_path)

    if request_path.startswith("/api/"):
        raise HTTPException(status_code=404)

    if request_path == _LOGIN_PATH and _is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    if not _is_public_frontend_path(request_path) and not _is_authenticated(request):
        return RedirectResponse(url=_LOGIN_PATH, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return _serve_frontend_path(full_path)
