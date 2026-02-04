from piloty.core import PTY


def test_background_process_output_does_not_deadlock():
    pty = PTY(session_id="test_bg")
    try:
        r = pty.type("sleep 1 &\n", timeout=2.0, quiescence_ms=300)
        assert r["status"] == "quiescent"
        r = pty.type("echo done\n", timeout=2.0, quiescence_ms=300)
        assert "done" in r["output"]
    finally:
        pty.terminate()
