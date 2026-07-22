import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app import config
from backend.app.board_store import SessionLocal, get_board, save_board
from backend.app.dependencies import require_authenticated, require_session_user_id
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

router = APIRouter(prefix="/api/ai", tags=["ai"])

# In-memory per-user sliding-window rate limit for AI endpoints. This is
# process-local (resets on restart, not shared across multiple workers),
# which is acceptable for the current single-instance local MVP deployment.
_AI_RATE_LIMIT_WINDOW_SECONDS = config.AI_RATE_LIMIT_WINDOW_SECONDS
_AI_RATE_LIMIT_MAX_REQUESTS = config.AI_RATE_LIMIT_MAX_REQUESTS
_ai_request_log: dict[int, deque[float]] = defaultdict(deque)


class ConnectivityRequest(BaseModel):
    prompt: str = Field(default="What is 2 + 2?", max_length=config.AI_MESSAGE_MAX_LENGTH)


class AIKanbanRequest(BaseModel):
    message: str = Field(min_length=1, max_length=config.AI_MESSAGE_MAX_LENGTH)
    history: list[ConversationTurn] = Field(default_factory=list)


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


@router.post("/connectivity")
def openrouter_connectivity(payload: ConnectivityRequest, request: Request) -> dict[str, str]:
    require_authenticated(request)
    user_id = require_session_user_id(request)
    _enforce_ai_rate_limit(user_id)

    prompt = payload.prompt.strip() or "What is 2 + 2?"
    try:
        reply = query_openrouter(prompt)
    except OpenRouterConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except OpenRouterRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"model": reply.model, "response": reply.text}


@router.post("/respond")
def ai_kanban_respond(payload: AIKanbanRequest, request: Request) -> dict[str, object]:
    require_authenticated(request)
    user_id = require_session_user_id(request)
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
