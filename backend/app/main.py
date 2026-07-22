from fastapi import FastAPI

from backend.app.board_store import init_database
from backend.app.middleware import configure_middleware
from backend.app.routers import ai, auth, board, frontend, health

app = FastAPI(title="PM MVP Backend")

configure_middleware(app)

init_database()

app.include_router(auth.router)
app.include_router(board.router)
app.include_router(ai.router)
app.include_router(health.router)
# frontend.router contains the "/{full_path:path}" catch-all and must be
# included last, or it would shadow the more specific routers above.
app.include_router(frontend.router)
