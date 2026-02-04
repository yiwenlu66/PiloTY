# PiloTY

PiloTY is an MCP server that provides stateful terminal sessions via a PTY. A `session_id` is a persistent handle to a running shell, so agents can drive SSH, debuggers, REPLs, pagers, and full-screen TUIs without losing state between tool calls.

## Security model

PiloTY exposes unrestricted terminal access. Treat it like giving the agent your keyboard.

- Secrets can appear in the rendered screen and the transcript.
- `send_password()` suppresses transcript logging and terminal echo for that specific send, but it does not prevent other prompts from echoing sensitive data.

## Session model

One PTY per `session_id`.

- Session state persists: cwd, environment, foreground process, job control, remote SSH connection, REPL/debugger state.
- Sessions are created by tools that send input (`run`, `send_input`, `send_control`, `send_password`, `poll_output`, `expect`). View-only tools do not create sessions.
- `terminate(session_id)` is final. Later calls with the same `session_id` return `status="terminated"`.

### Initial cwd

For a newly created session, PiloTY uses the MCP client root directory (if the client supports roots and provides one). Otherwise it uses the server process cwd.

### Default shell

Sessions spawn `bash --noprofile --norc`. If you need another shell, start it inside that bash (`zsh`, `fish`, etc).

### Quiescence

Output collection uses quiescence: "silence for N ms". Configure with `PILOTY_QUIESCENCE_MS` (default `1000`).

## Output vs rendered views

PiloTY keeps two representations of terminal state:

- Incremental stream output ("what arrived since the last ingestion call")
- VT100-rendered screen and scrollback ("what the terminal looks like")

Tools that ingest PTY output advance the VT100 renderer. View tools do not read from the PTY stream (no hidden output consumption).

## Agent-facing tools

All tools take `session_id`.

- `run(session_id, command, timeout=30, strip_ansi=true)`: send a line (adds newline)
- `send_input(session_id, text, timeout=30, strip_ansi=true)`: send text without a newline
- `send_control(session_id, key, timeout=5, strip_ansi=true)`: send a control key (`c`, `d`, `z`, `l`, `[` for escape)
- `send_password(session_id, password, timeout=30)`: send a password (no transcript logging; echo suppressed)
- `send_signal(session_id, signal, strip_ansi=true)`: send an OS signal to the foreground process group

- `poll_output(session_id, timeout=0.1, strip_ansi=true)`: wait up to `timeout` for any new output without sending input (returns empty output only on timeout)
- `expect(session_id, pattern, timeout=30, strip_ansi=true)`: wait for a regex; checks already-rendered text first, then waits for new output
- `expect_prompt(session_id, timeout=30)`: wait until a shell prompt is detected (SSH/login workflows without agent-supplied regex)

- `get_screen(session_id)`: rendered screen snapshot (includes cursor position and vt100 health)
- `get_scrollback(session_id, lines=200)`: best-effort rendered scrollback
- `clear_scrollback(session_id)`: clears renderer scrollback history without sending input and without changing the current visible screen

- `get_metadata(session_id)`: cwd, foreground pid, dimensions, timestamps, tag
- `configure_session(session_id, tag=None, prompt_regex=None)`: set a tag and optional prompt regex (escape hatch)
- `list_sessions()`: list active and terminated session ids (with metadata)
- `transcript(session_id)`: transcript path (also returns the on-disk path if a session was evicted/restarted)
- `terminate(session_id)`: terminate a session (final)

### `status` and `prompt`

PiloTY returns a single processed `status` plus a separate `prompt` classification, derived from the rendered screen.

- `status`: `running`, `ready`, `repl`, `password`, `confirm`, `editor`, `pager`, `unknown`, `eof`, `terminated`
- `prompt`: `shell`, `python`, `pdb`, `none`, `unknown`

`status` is an agent-facing summary of "what input is likely needed next". It is not a transport state, and it is best-effort.

## Common workflows

### Long-running command + output monitoring

- Start the job (foreground or via `&`)
- Use `poll_output(timeout=...)` to pick up output that arrives later
- Use `get_screen()` when the incremental output is hard to interpret (pagers, full-screen TUIs)
- Stop follow/streaming with Ctrl+C (`send_control(key="c")`)

### Interactive debugging (pdb)

- `run(session_id, "python -m pdb path/to/script.py", timeout=5)`
- Drive the debugger with `send_input()` and inspect state with `get_screen()`

### SSH without regex

For slow banners and delayed prompt printing:

- `run(session_id, "ssh host", timeout=2)` (do not expect the banner to be fully captured)
- `expect_prompt(session_id, timeout=30)` (waits for a READY prompt)

### Pagers and TUIs (less, man, vim)

`send_input(strip_ansi=true)` returns a normalized text stream, which can still be ambiguous for cursor-motion heavy TUIs. Prefer `get_screen()` as the "what the user would see" view.

## Logs

Each session writes logs under `~/.piloty/`:

- `~/.piloty/sessions/<session-id>/transcript.log`: raw PTY bytes (combined stdout and stderr)
- `~/.piloty/sessions/<session-id>/interaction.log`: best-effort structured interactions
- `~/.piloty/sessions/<session-id>/session.json`: metadata

Server logs go to `/tmp/piloty.log`.

## Development

Repository layout:

```
piloty/
  core.py        # PTY + VT100 renderer + session logs
  mcp_server.py  # MCP tools + state inference
tests/
tools/
  pty_playground.py
  session_viewer.py
```

Local development:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m pytest -q
```

Developer tools:

```bash
python tools/pty_playground.py
python tools/session_viewer.py list
python tools/session_viewer.py info <session-id>
python tools/session_viewer.py tail -f <session-id>
```

License: Apache License 2.0, see `LICENSE`.
