from fastapi import APIRouter, HTTPException, Request, status

from backend.app import config
from backend.app.board_store import BoardData, SessionLocal, get_board, reset_database, save_board
from backend.app.dependencies import require_authenticated, require_session_user_id

router = APIRouter(prefix="/api/board", tags=["board"])


@router.get("")
def read_board(request: Request) -> BoardData:
    require_authenticated(request)
    user_id = require_session_user_id(request)
    with SessionLocal() as session:
        return get_board(session, user_id)


@router.put("")
def update_board(payload: BoardData, request: Request) -> BoardData:
    require_authenticated(request)
    user_id = require_session_user_id(request)
    with SessionLocal() as session:
        return save_board(session, user_id, payload)


@router.post("/reset")
def reset_board(request: Request) -> dict[str, bool]:
    require_authenticated(request)
    if not config.allow_test_reset():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    reset_database()
    return {"ok": True}
