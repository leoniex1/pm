from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.board_store import SessionLocal, authenticate_user, get_user_by_id
from backend.app.dependencies import is_authenticated, require_authenticated

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
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


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    require_authenticated(request)
    request.session.clear()
    return {"authenticated": False}


@router.get("/session")
def session_status(request: Request) -> dict[str, str | bool | None]:
    authenticated = is_authenticated(request)
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
