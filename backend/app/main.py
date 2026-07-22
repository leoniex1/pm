import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from backend.app.board_store import (
    BoardData,
    SessionLocal,
    authenticate_user,
    get_user_by_id,
    get_board,
    init_database,
    reset_database,
    save_board,
)
from backend.app.openrouter_service import (
    OpenRouterConfigurationError,
    OpenRouterRequestError,
    query_openrouter,
)
from backend.app.structured_output import (
    ConversationTurn,
    StructuredOutputError,
    build_structured_prompt,
    parse_structured_response,
    validate_and_apply_operations,
)

app = FastAPI(title="PM MVP Backend")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "pm-mvp-dev-session-secret"),
    same_site="lax",
    https_only=False,
)

# No CORS middleware: the frontend is always served same-origin (either the
# static export served by this backend, or the FastAPI-served build used for
# local full-stack development/e2e — see scripts/serve.mjs). Every fetch call
# in the frontend uses a relative path, so no cross-origin request is ever
# issued and no CORS configuration is needed.

init_database()

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
_STATIC_INDEX = _STATIC_DIR / "index.html"
_LOGIN_PATH = "/login"

_FRONTEND_PUBLIC_PATHS = {
    _LOGIN_PATH,
    "/favicon.ico",
    "/robots.txt",
}

_AI_MESSAGE_MAX_LENGTH = 4000

# In-memory per-user sliding-window rate limit for AI endpoints. This is
# process-local (resets on restart, not shared across multiple workers),
# which is acceptable for the current single-instance local MVP deployment.
_AI_RATE_LIMIT_WINDOW_SECONDS = 60
_AI_RATE_LIMIT_MAX_REQUESTS = 20
_ai_request_log: dict[int, deque[float]] = defaultdict(deque)


class LoginRequest(BaseModel):
    username: str
    password: str


class ConnectivityRequest(BaseModel):
    prompt: str = Field(default="What is 2 + 2?", max_length=_AI_MESSAGE_MAX_LENGTH)


class AIKanbanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=_AI_MESSAGE_MAX_LENGTH)
    history: list[ConversationTurn] = Field(default_factory=list)


def _is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def _require_authenticated(request: Request) -> None:
    if not _is_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def _require_session_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return user_id


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


def _enforce_ai_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    log = _ai_request_log[user_id]

    while log and now - log[0] > _AI_RATE_LIMIT_WINDOW_SECONDS:
        log.popleft()

    if len(log) >= _AI_RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many AI requests. Please wait a moment and try again.",
        )

    log.append(now)


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> dict[str, str | bool]:
    with SessionLocal() as session:
        user = authenticate_user(session, payload.username, payload.password)
        if user is not None:
            user_id = user.id
            username = user.username

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    request.session["authenticated"] = True
    request.session["username"] = username
    request.session["user_id"] = user_id
    return {"authenticated": True, "username": username}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    _require_authenticated(request)
    request.session.clear()
    return {"authenticated": False}


@app.get("/api/auth/session")
def session_status(request: Request) -> dict[str, str | bool | None]:
    authenticated = _is_authenticated(request)
    if not authenticated:
        return {"authenticated": False, "username": None}

    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        request.session.clear()
        return {"authenticated": False, "username": None}

    with SessionLocal() as session:
        user = get_user_by_id(session, user_id)

    if user is None:
        request.session.clear()
        return {"authenticated": False, "username": None}

    request.session["username"] = user.username
    return {"authenticated": True, "username": user.username}


@app.get("/api/board")
def read_board(request: Request) -> BoardData:
    _require_authenticated(request)
    user_id = _require_session_user_id(request)
    with SessionLocal() as session:
        return get_board(session, user_id)


@app.put("/api/board")
def update_board(payload: BoardData, request: Request) -> BoardData:
    _require_authenticated(request)
    user_id = _require_session_user_id(request)
    with SessionLocal() as session:
        return save_board(session, user_id, payload)


@app.post("/api/board/reset")
def reset_board(request: Request) -> dict[str, bool]:
    _require_authenticated(request)
    if os.getenv("ALLOW_TEST_RESET", "0") != "1":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    reset_database()
    return {"ok": True}


@app.post("/api/ai/connectivity")
def openrouter_connectivity(payload: ConnectivityRequest, request: Request) -> dict[str, str]:
    _require_authenticated(request)
    user_id = _require_session_user_id(request)
    _enforce_ai_rate_limit(user_id)

    prompt = payload.prompt.strip() or "What is 2 + 2?"
    try:
        reply = query_openrouter(prompt)
    except OpenRouterConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"model": reply.model, "response": reply.text}


@app.post("/api/ai/respond")
def ai_kanban_respond(payload: AIKanbanRequest, request: Request) -> dict[str, object]:
    _require_authenticated(request)
    user_id = _require_session_user_id(request)
    _enforce_ai_rate_limit(user_id)

    with SessionLocal() as session:
        current_board = get_board(session, user_id)

    prompt = build_structured_prompt(
        board=current_board,
        user_message=payload.message,
        history=payload.history,
    )

    try:
        reply = query_openrouter(prompt)
        structured = parse_structured_response(reply.text)
        next_board = validate_and_apply_operations(current_board, structured.operations)
    except OpenRouterConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except StructuredOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with SessionLocal() as session:
        try:
            with session.begin():
                persisted_board = save_board(session, user_id, next_board, commit=False)
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=500, detail="Failed to apply operations atomically") from exc

    return {
        "assistant_message": structured.assistant_message,
        "operations": [operation.model_dump(mode="json") for operation in structured.operations],
        "board": persisted_board.model_dump(mode="json"),
    }


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
