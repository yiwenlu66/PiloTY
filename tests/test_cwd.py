import anyio

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import Root, ListRootsResult

from piloty.core import PTY


def test_pty_respects_initial_cwd(tmp_path):
    pty = PTY(session_id="test_cwd", cwd=str(tmp_path))
    try:
        r = pty.type("pwd\n", timeout=5.0, quiescence_ms=300)
        assert str(tmp_path) in r["output"]
    finally:
        pty.terminate()


def test_server_uses_client_roots_for_initial_cwd(tmp_path):
    async def main():
        server = StdioServerParameters(
            command="./venv/bin/python",
            args=["-m", "piloty.mcp_server"],
            cwd="/home/yiwen/PiloTY",
        )

        async def list_roots_callback(_ctx):
            return ListRootsResult(roots=[Root(uri=f"file://{tmp_path}", name="test-root")])

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, list_roots_callback=list_roots_callback) as session:
                await session.initialize()
                res = await session.call_tool(
                    "run",
                    {"session_id": "roots-cwd", "command": "pwd", "timeout": 5.0},
                )
                txt = next(c.text for c in res.content if getattr(c, "type", None) == "text")
                assert str(tmp_path) in txt

    anyio.run(main)

