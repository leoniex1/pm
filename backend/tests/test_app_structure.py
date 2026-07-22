from backend.app.main import app


def _route_map() -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if methods is None:
            continue
        routes.setdefault(route.path, set()).update(methods)
    return routes


def test_all_expected_routes_are_registered() -> None:
    routes = _route_map()

    assert "GET" in routes["/api/health"]
    assert "POST" in routes["/api/auth/login"]
    assert "POST" in routes["/api/auth/logout"]
    assert "GET" in routes["/api/auth/session"]
    assert {"GET", "PUT"}.issubset(routes["/api/board"])
    assert "POST" in routes["/api/board/reset"]
    assert "POST" in routes["/api/ai/connectivity"]
    assert "POST" in routes["/api/ai/respond"]
    assert "GET" in routes["/"]
    assert "GET" in routes["/{full_path:path}"]


def test_catch_all_frontend_route_is_registered_last() -> None:
    """The "/{full_path:path}" catch-all must stay the last registered route,
    or it would shadow every /api/* route added after it."""
    paths = [route.path for route in app.routes if hasattr(route, "path")]
    assert paths.index("/{full_path:path}") == len(paths) - 1


def test_routers_are_organized_into_dedicated_modules() -> None:
    from backend.app.routers import ai, auth, board, frontend, health

    assert any(route.path == "/api/auth/login" for route in auth.router.routes)
    assert any(route.path == "/api/board" for route in board.router.routes)
    assert any(route.path == "/api/ai/respond" for route in ai.router.routes)
    assert any(route.path == "/api/health" for route in health.router.routes)
    assert any(route.path == "/{full_path:path}" for route in frontend.router.routes)
