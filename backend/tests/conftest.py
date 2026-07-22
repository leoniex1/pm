import pytest

from backend.app.main import _ai_request_log


@pytest.fixture(autouse=True)
def _reset_ai_rate_limit() -> None:
    """Prevent AI rate-limit state from leaking between tests.

    _ai_request_log is process-global (see main.py), so without this reset,
    tests across different files that call /api/ai/respond or
    /api/ai/connectivity as the same seeded user could start tripping the
    rate limit purely because of test ordering/count, not because of
    anything the test itself is doing.
    """
    _ai_request_log.clear()
