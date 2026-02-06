import json
import os

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


def _env_value_from_output(output: str, key: str) -> str:
    for raw_line in output.splitlines():
        line = raw_line.replace("\r", "").strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    raise AssertionError(f"missing key in output: {key}")


def test_pty_strips_python_venv_env_vars(tmp_path, monkeypatch):
    leaked_venv = str(tmp_path / "fake-venv")
    leaked_bin = os.path.join(leaked_venv, "bin")

    monkeypatch.setenv("VIRTUAL_ENV", leaked_venv)
    monkeypatch.setenv("VIRTUAL_ENV_PROMPT", "(fake)")
    monkeypatch.setenv("PYTHONHOME", "/tmp/fake-pythonhome")
    monkeypatch.setenv("PYTHONPATH", "/tmp/fake-pythonpath")
    monkeypatch.setenv("__PYVENV_LAUNCHER__", "/tmp/fake-launcher")
    monkeypatch.setenv("PATH", f"{leaked_bin}{os.pathsep}{os.environ.get('PATH', '')}")

    pty = PTY(session_id="test_env_strip", cwd=str(tmp_path))
    try:
        command = (
            'printf "VIRTUAL_ENV=%s\\n" "$VIRTUAL_ENV"; '
            'printf "PYTHONHOME=%s\\n" "$PYTHONHOME"; '
            'printf "PYTHONPATH=%s\\n" "$PYTHONPATH"; '
            'printf "__PYVENV_LAUNCHER__=%s\\n" "$__PYVENV_LAUNCHER__"; '
            'printf "PATH=%s\\n" "$PATH"'
        )
        output = pty.type(f"{command}\n", timeout=5.0, quiescence_ms=300)["output"]

        assert _env_value_from_output(output, "VIRTUAL_ENV") == ""
        assert _env_value_from_output(output, "PYTHONHOME") == ""
        assert _env_value_from_output(output, "PYTHONPATH") == ""
        assert _env_value_from_output(output, "__PYVENV_LAUNCHER__") == ""
        assert leaked_bin not in _env_value_from_output(output, "PATH")
    finally:
        pty.terminate()
