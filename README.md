<p align="center">
  <img src="assets/logo.png" alt="PiloTY logo" width="220" />
</p>

# PiloTY

PiloTY (PTY for your AI Copilot) is an MCP server that gives an agent a persistent, interactive terminal.

If you have used Claude Code / Codex to run shell commands, you have probably hit the same wall: tool calls tend to be stateless. Each call starts "fresh", so environment variables disappear, interactive programs cannot be driven reliably, and long-running processes get cut off or orphaned while the agent is thinking.

PiloTY exists to make the agent's terminal behave more like a human's: start something in a real terminal, come back later, and keep going.

Warning: PiloTY exposes unrestricted terminal access. Treat it like giving the agent your keyboard.

## What it enables

- Long-running commands: builds, installs, migrations, test suites. Start once, check output later.
- Log monitoring: `tail -f`, `journalctl -f`, `kubectl logs -f`, CI logs, service restarts.
- "Vibe debugging": keep a REPL/debugger open while the agent reads code and tries ideas (`python`, `ipython`, `pdb`).
- Privileged operations: handle interactive password prompts (`sudo`, SSH passwords, key passphrases).
- SSH-based devops: keep a remote login session alive across tool calls; run remote commands in the same shell.
- Terminal UIs: `less`, `man`, `top`, `vim` can work, but cursor-heavy programs often require screen snapshots instead of plain text output.

## Quickstart

PiloTY is meant to be launched by an MCP client over stdio.

Add it to Codex CLI as an MCP server:

```bash
codex mcp add piloty -- uvx --from git+https://github.com/yiwenlu66/PiloTY.git piloty
```

If you prefer SSH-based Git fetch:

```bash
codex mcp add piloty -- uvx --from git+ssh://git@github.com/yiwenlu66/PiloTY.git piloty
```

If you already have a local clone:

```bash
codex mcp add piloty -- uv --directory /path/to/PiloTY run piloty
```

Run the server command directly (without adding it to an MCP client):

```bash
uvx --from git+https://github.com/yiwenlu66/PiloTY.git piloty
```

## Mental model

One session is one real interactive terminal that stays alive across tool calls.

- State persists: cwd, environment variables, foreground process, remote SSH connection, REPL/debugger state.
- PiloTY tracks both the raw output stream and a rendered screen/scrollback view.

PiloTY keeps two representations:

- `output`: incremental text stream (optionally ANSI-stripped)
- Rendered screen/scrollback: what a human would see in a terminal

Sessions are addressed by a `session_id` string. Reusing the same id is what keeps state.

## Tool reference (for MCP integrators)

All tools take a `session_id` string.

Input/output:

- `run(...)`: send a line (adds newline)
- `poll_output(...)`: wait up to `timeout` for new output without sending input
- `send_input(...)`: send text without newline
- `send_control(...)`: send a control key (`c`, `d`, `z`, `l`, `[` for escape)
- `send_password(...)`: send a password (no transcript logging; echo suppressed for this send)
- `expect_prompt(...)`: wait for a shell prompt (useful after `ssh`/login output where the prompt appears later)

Rendered view:

- `get_screen(...)`: rendered screen snapshot (cursor position, rendering status)
- `get_scrollback(...)`: rendered scrollback (best-effort)

Session management:

- `get_metadata(...)`: cwd, foreground pid, dimensions, timestamps, tag
- `transcript(...)`: transcript path (includes on-disk path if a session was evicted/restarted)
- `terminate(...)`: terminate a session (final; later calls reject the id)

For tool signatures and return fields, read `piloty/mcp_server.py`.

## Limitations

- Status/prompt detection is best-effort and can be wrong (especially for custom prompts and cursor-heavy TUIs).
- Plain text output can be misleading for full-screen programs; use screen snapshots when layout matters.
- `send_password()` suppresses transcript logging and terminal echo for that send. It does not prevent other prompts/programs from echoing secrets later.
- Quiescence-based output collection can be confused by programs that print periodic noise. Tune with `PILOTY_QUIESCENCE_MS` (default `1000`).

## Logs

Each session writes logs under `~/.piloty/`:

- `~/.piloty/sessions/<session-id>/transcript.log`: raw PTY bytes (combined stdout/stderr)
- `~/.piloty/sessions/<session-id>/commands.log`: inputs sent (best-effort)
- `~/.piloty/sessions/<session-id>/interaction.log`: inputs plus captured output (best-effort)
- `~/.piloty/sessions/<session-id>/session.json`: metadata snapshot
- `~/.piloty/active/<session-id>`: symlink to the current session directory (when symlinks are supported)

Server logs default to `/tmp/piloty.log`.

`tools/session_viewer.py` can inspect sessions:

```bash
python tools/session_viewer.py list
python tools/session_viewer.py info <session-id>
python tools/session_viewer.py tail -f <session-id>
```

## Development

Repository layout:

```
piloty/
  core.py        # PTY + terminal renderer + session logs
  mcp_server.py  # MCP tools + state inference
tests/
tools/
  pty_playground.py
  session_viewer.py
```

Run tests:

```bash
python -m pytest -q
```

License: Apache License 2.0, see `LICENSE`.
