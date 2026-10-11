from unittest.mock import patch

from app.core import parent_watchdog


def test_watchdog_disabled_without_parent_pid(monkeypatch) -> None:
    monkeypatch.delenv(parent_watchdog.PARENT_PID_ENV, raising=False)
    assert parent_watchdog.start_parent_watchdog() is None


def test_watchdog_requests_shutdown_when_parent_exits(monkeypatch) -> None:
    monkeypatch.setenv(parent_watchdog.PARENT_PID_ENV, "4242")
    identities = iter([100.0, 100.0, None])  # start, alive once, then gone
    with (
        patch.object(parent_watchdog, "_parent_identity", side_effect=lambda pid: next(identities)),
        patch.object(parent_watchdog, "POLL_INTERVAL_SECONDS", 0),
        patch.object(parent_watchdog, "_request_shutdown") as shutdown,
    ):
        thread = parent_watchdog.start_parent_watchdog()
        assert thread is not None
        thread.join(timeout=5)

    shutdown.assert_called_once()


def test_reused_pid_counts_as_parent_gone() -> None:
    with patch.object(parent_watchdog, "_parent_identity", return_value=200.0):
        assert parent_watchdog.parent_is_alive(4242, created_at=100.0) is False
