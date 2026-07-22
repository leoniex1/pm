from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response

from backend.app import config
from backend.app.dependencies import is_authenticated

router = APIRouter(tags=["frontend"])


def _resolve_static_file(path: str) -> Path:
    requested_path = path.strip("/")
    candidate = (config.STATIC_DIR / requested_path).resolve()
    static_root = config.STATIC_DIR.resolve()

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

    return FileResponse(config.STATIC_INDEX)


def _frontend_path_from_request(full_path: str) -> str:
    normalized = full_path.strip("/")
    if not normalized:
        return "/"
    return f"/{normalized}"


def _is_frontend_asset_path(path: str) -> bool:
    return path.startswith("/_next/")


def _is_public_frontend_path(path: str) -> bool:
    return path in config.FRONTEND_PUBLIC_PATHS or _is_frontend_asset_path(path)


# Route registration order matters here: "/" must be registered before the
# "/{full_path:path}" catch-all below it, and this router itself must be the
# last one included in main.py, so none of the more specific /api/* routers
# are ever shadowed by the catch-all.


@router.get("/", response_class=Response)
def read_root(request: Request) -> Response:
    if not is_authenticated(request):
        return RedirectResponse(url=config.LOGIN_PATH, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return _serve_frontend_path("")


@router.get("/{full_path:path}", response_class=Response)
def serve_frontend(full_path: str, request: Request) -> Response:
    request_path = _frontend_path_from_request(full_path)

    if request_path.startswith("/api/"):
        raise HTTPException(status_code=404)

    if request_path == config.LOGIN_PATH and is_authenticated(request):
        return RedirectResponse(url="/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    if not _is_public_frontend_path(request_path) and not is_authenticated(request):
        return RedirectResponse(url=config.LOGIN_PATH, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return _serve_frontend_path(full_path)
