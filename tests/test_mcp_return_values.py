import asyncio

from piloty import mcp_server


def test_mcp_tool_shapes_include_status_and_prompt(tmp_path):
    prev = mcp_server.QUIESCENCE_MS
    mcp_server.QUIESCENCE_MS = 50
    session_id = "test_mcp_shapes"
    try:
        created = asyncio.run(mcp_server.create_session(session_id=session_id, cwd=str(tmp_path)))
        assert created["created"] is True

        r = asyncio.run(mcp_server.run(session_id=session_id, command="echo hi", timeout=2.0))
        assert "screen" not in r
        assert set(r.keys()) >= {"status", "prompt", "output", "timed_out"}

        r = asyncio.run(mcp_server.send_input(session_id=session_id, text="echo si\n", timeout=2.0))
        assert "screen" not in r
        assert set(r.keys()) >= {"status", "prompt", "output", "timed_out"}

        r = asyncio.run(mcp_server.send_control(session_id=session_id, key="l", timeout=2.0))
        assert "screen" not in r
        assert set(r.keys()) >= {"status", "prompt", "output", "timed_out"}

        r = asyncio.run(mcp_server.poll_output(session_id=session_id, timeout=0.05))
        assert set(r.keys()) >= {"status", "prompt", "output", "timed_out"}

        r = asyncio.run(mcp_server.send_password(session_id=session_id, password="not_a_secret", timeout=2.0))
        assert "screen" not in r
        assert set(r.keys()) >= {"status", "prompt", "output", "timed_out"}
        assert r["output"].startswith("[password sent]")
        assert "not_a_secret" not in r["output"]

        s = asyncio.run(mcp_server.get_screen(session_id=session_id))
        assert set(s.keys()) >= {"status", "prompt", "screen"}
    finally:
        try:
            asyncio.run(mcp_server.terminate(session_id))
        except Exception:
            pass
        mcp_server.QUIESCENCE_MS = prev


def test_mcp_terminate_is_final(tmp_path):
    session_id = "test_mcp_terminate_final"
    try:
        asyncio.run(mcp_server.create_session(session_id=session_id, cwd=str(tmp_path)))
        asyncio.run(mcp_server.run(session_id=session_id, command="echo hi", timeout=2.0))
        asyncio.run(mcp_server.terminate(session_id))
        r = asyncio.run(mcp_server.run(session_id=session_id, command="echo nope", timeout=2.0))
        assert r["status"] == "terminated"
    finally:
        try:
            asyncio.run(mcp_server.terminate(session_id))
        except Exception:
            pass
