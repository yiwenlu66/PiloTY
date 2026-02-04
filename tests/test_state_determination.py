import asyncio
from types import SimpleNamespace

from piloty import mcp_server


def test_determine_terminal_state_uses_heuristic_without_ctx():
    state, reason = asyncio.run(mcp_server.determine_terminal_state(None, "bash-5.3$", cursor_x=10))
    assert state == "READY"
    assert "shell prompt" in reason


def test_determine_terminal_state_uses_heuristic_without_sampling_capability():
    caps = SimpleNamespace(sampling=None)
    client_params = SimpleNamespace(capabilities=caps)
    session = SimpleNamespace(client_params=client_params)
    ctx = SimpleNamespace(session=session)

    state, reason = asyncio.run(mcp_server.determine_terminal_state(ctx, "bash-5.3$", cursor_x=10))
    assert state == "READY"
    assert "shell prompt" in reason


def test_determine_terminal_state_falls_back_when_sampling_raises():
    class BrokenSession:
        client_params = SimpleNamespace(capabilities=SimpleNamespace(sampling=SimpleNamespace()))

        async def create_message(self, *args, **kwargs):
            raise RuntimeError("sampling unavailable")

    ctx = SimpleNamespace(session=BrokenSession())
    state, reason = asyncio.run(mcp_server.determine_terminal_state(ctx, "no prompt here", cursor_x=0))
    assert state == "RUNNING"
    assert "sampling=UNKNOWN" in reason
    assert "sampling unavailable" in reason


def test_determine_terminal_state_uses_sampling_when_parsable():
    class GoodSession:
        client_params = SimpleNamespace(capabilities=SimpleNamespace(sampling=SimpleNamespace()))

        async def create_message(self, *args, **kwargs):
            return SimpleNamespace(content=SimpleNamespace(type="text", text="CONFIRM: waiting for confirmation"))

    ctx = SimpleNamespace(session=GoodSession())
    state, reason = asyncio.run(mcp_server.determine_terminal_state(ctx, "anything", cursor_x=0))
    assert state == "CONFIRM"
    assert reason == "waiting for confirmation"


def test_determine_terminal_state_falls_back_when_sampling_unparsable():
    class WeirdSession:
        client_params = SimpleNamespace(capabilities=SimpleNamespace(sampling=SimpleNamespace()))

        async def create_message(self, *args, **kwargs):
            return SimpleNamespace(content=SimpleNamespace(type="text", text="I refuse to follow instructions"))

    ctx = SimpleNamespace(session=WeirdSession())
    state, reason = asyncio.run(mcp_server.determine_terminal_state(ctx, "no prompt here", cursor_x=0))
    assert state == "RUNNING"
    assert "sampling=UNKNOWN" in reason


def test_heuristic_prefers_pdb_prompt_over_traceback_text():
    screen = "\n".join(
        [
            "Traceback (most recent call last):",
            "  File \"x.py\", line 1, in <module>",
            "IndexError: list index out of range",
            "(Pdb) ",
        ]
    )
    state, reason = mcp_server.detect_state_heuristic(screen, cursor_x=6)
    assert state == "REPL"
    assert "pdb prompt" in reason


def test_error_state_does_not_produce_error_status():
    # "ERROR" is a heuristic label for screen contents. Transport status remains
    # in the processed status enum and is not derived from terminal text.
    assert mcp_server._status_from_state(terminated=False, alive=True, state="ERROR") == "unknown"


def test_sampling_ready_does_not_override_running_command_line():
    class ReadySession:
        client_params = SimpleNamespace(capabilities=SimpleNamespace(sampling=SimpleNamespace()))

        async def create_message(self, *args, **kwargs):
            return SimpleNamespace(content=SimpleNamespace(type="text", text="READY: prompt visible"))

    ctx = SimpleNamespace(session=ReadySession())
    screen = "bash-5.3$ sleep 60"
    state, reason = asyncio.run(mcp_server.determine_terminal_state(ctx, screen, cursor_x=0))
    assert state == "RUNNING"
    assert "sampling=READY" in reason


def test_expect_matches_already_visible_screen():
    import asyncio

    from piloty import mcp_server

    session_id = "test_expect_visible"
    try:
        asyncio.run(mcp_server.run(session_id=session_id, command="echo EXPECTME", timeout=2.0))
        r = asyncio.run(mcp_server.expect(session_id=session_id, pattern="EXPECTME", timeout=0.1))
        assert r["matched"] is True
        assert r["timed_out"] is False
        assert r["match"] == "EXPECTME"
    finally:
        try:
            asyncio.run(mcp_server.terminate(session_id))
        except Exception:
            pass


def test_expect_prompt_waits_for_prompt_after_timeout_run():
    import asyncio

    from piloty import mcp_server

    session_id = "test_expect_prompt"
    try:
        r = asyncio.run(
            mcp_server.run(
                session_id=session_id,
                command="sh -c 'sleep 0.4'",
                timeout=0.05,
            )
        )
        assert r["status"] in {"running", "unknown"}

        r2 = asyncio.run(mcp_server.expect_prompt(session_id=session_id, timeout=2.0))
        assert r2["matched"] is True
        assert r2["timed_out"] is False
        assert r2["status"] == "ready"
        assert r2["prompt"] == "shell"
    finally:
        try:
            asyncio.run(mcp_server.terminate(session_id))
        except Exception:
            pass


def test_traceback_in_scrollback_does_not_override_prompt():
    screen = "\n".join(
        [
            "Traceback (most recent call last):",
            "  File \"x.py\", line 1, in <module>",
            "IndexError: list index out of range",
            "",
            "more unrelated output",
            "",
            "bash-5.3$",
            "",
        ]
    )
    state, _reason = mcp_server.detect_state_heuristic(screen, cursor_x=10)
    assert state == "READY"


def test_old_password_text_in_scrollback_does_not_override_prompt():
    screen = "\n".join(
        [
            "Password:",
            "Authentication failed",
            "",
            "bash-5.3$",
        ]
    )
    state, _reason = mcp_server.detect_state_heuristic(screen, cursor_x=10)
    assert state == "READY"


def test_old_confirm_text_in_scrollback_does_not_override_prompt():
    screen = "\n".join(
        [
            "Proceed? [y/n]",
            "",
            "bash-5.3$",
        ]
    )
    state, _reason = mcp_server.detect_state_heuristic(screen, cursor_x=10)
    assert state == "READY"


def test_password_prompt_without_ready_is_password():
    screen = "Enter passphrase for key '/home/user/.ssh/id_ed25519':"
    state, _reason = mcp_server.detect_state_heuristic(screen, cursor_x=40)
    assert state == "PASSWORD"


def test_shell_prompt_not_detected_from_command_line_bash():
    screen = "bash-5.3$ sleep 5"
    state, _reason = mcp_server.detect_state_heuristic(screen, cursor_x=0)
    assert state == "RUNNING"


def test_shell_prompt_not_detected_from_command_line_user_host():
    screen = "user@host:~$ sleep 5"
    state, _reason = mcp_server.detect_state_heuristic(screen, cursor_x=0)
    assert state == "RUNNING"


def test_pdb_prompt_in_scrollback_does_not_override_shell_prompt():
    screen = "\n".join(["(Pdb) ", "bash-5.3$"])
    state, _reason = mcp_server.detect_state_heuristic(screen, cursor_x=10)
    assert state == "READY"


def test_cursor_column_0_prevents_ready_on_stale_prompt_line():
    state, _reason = mcp_server.detect_state_heuristic("bash-5.3$", cursor_x=0)
    assert state == "RUNNING"

    state, _reason = mcp_server.detect_state_heuristic("bash-5.3$", cursor_x=10)
    assert state == "READY"
