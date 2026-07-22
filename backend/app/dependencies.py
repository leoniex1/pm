from fastapi import HTTPException, Request, status


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def require_authenticated(request: Request) -> None:
    if not is_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def require_session_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return user_id
