import time

from piloty.core import PTY


def test_poll_wait_returns_output_or_timeout():
    pty = PTY(session_id="test_poll_wait")
    try:
        # Schedule output in the future without producing immediate output.
        r = pty.type("sh -c 'sleep 0.6; echo POLLWAIT' &\n", timeout=2.0, quiescence_ms=300)
        assert r["status"] == "quiescent"

        r = pty.poll_output(timeout=2.0, quiescence_ms=200)
        assert r["status"] == "quiescent"
        assert "POLLWAIT" in r["output"]

        # Schedule output after the poll timeout.
        r = pty.type("sh -c 'sleep 0.5; echo LATE' &\n", timeout=2.0, quiescence_ms=300)
        assert r["status"] == "quiescent"

        t0 = time.monotonic()
        r = pty.poll_output(timeout=0.1, quiescence_ms=200)
        t1 = time.monotonic()
        assert r["status"] == "timeout"
        assert r["output"] == ""
        assert (t1 - t0) >= 0.08
    finally:
        pty.terminate()


def test_clear_scrollback_preserves_screen():
    pty = PTY(session_id="test_clear_scrollback")
    try:
        pty.type("echo one\n", timeout=2.0, quiescence_ms=200)
        before = pty.screen_snapshot(drain=False)["screen"]
        assert "one" in before
        pty.clear_scrollback()
        after = pty.screen_snapshot(drain=False)["screen"]
        assert after == before
    finally:
        pty.terminate()
