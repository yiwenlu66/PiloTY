import shutil

from piloty.core import PTY


def test_ssh_client_invocation_isolated():
    if shutil.which("ssh") is None:
        return
    pty = PTY(session_id="test_ssh_help")
    try:
        r = pty.type("ssh -G localhost >/dev/null 2>&1; echo $?\n", timeout=5.0)
        assert r["status"] == "quiescent"
    finally:
        pty.terminate()

