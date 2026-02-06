import json

import anyio

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from piloty.core import PTY


def test_pty_respects_initial_cwd(tmp_path):
    pty = PTY(session_id="test_cwd", cwd=str(tmp_path))
    try:
        r = pty.type("pwd\n", timeout=5.0, quiescence_ms=300)
        assert str(tmp_path) in r["output"]
    finally:
        pty.terminate()


def test_server_requires_explicit_session_cwd(tmp_path):
    async def main():
        server = StdioServerParameters(
            command="./venv/bin/python",
            args=["-m", "piloty.mcp_server"],
            cwd="/home/yiwen/PiloTY",
        )

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                missing = await session.call_tool(
                    "run",
                    {"session_id": "roots-cwd", "command": "pwd", "timeout": 5.0},
                )
                missing_txt = next(c.text for c in missing.content if getattr(c, "type", None) == "text")
                missing_payload = json.loads(missing_txt)
                assert missing_payload["status"] == "unknown"
                assert "create_session" in missing_payload["state_reason"]

                created = await session.call_tool(
                    "create_session",
                    {"session_id": "roots-cwd", "cwd": str(tmp_path)},
                )
                created_txt = next(c.text for c in created.content if getattr(c, "type", None) == "text")
                created_payload = json.loads(created_txt)
                assert created_payload["created"] is True
                assert created_payload["cwd"] == str(tmp_path)

                res = await session.call_tool(
                    "run",
                    {"session_id": "roots-cwd", "command": "pwd", "timeout": 5.0},
                )
                txt = next(c.text for c in res.content if getattr(c, "type", None) == "text")
                assert str(tmp_path) in txt

    anyio.run(main)
