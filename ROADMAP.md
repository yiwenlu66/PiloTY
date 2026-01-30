# PiloTY Roadmap

## Architecture

PTY has two states: **busy** (producing output) or **quiescent** (silent for N ms).

State interpretation via:
1. **Heuristic detection** - Fast pattern matching for common states (prompts, passwords, REPLs, editors)
2. **LLM sampling** - MCP `sampling/createMessage` for complex cases (when heuristic returns UNKNOWN)

No per-program handlers. TUI programs rendered via VT100 emulator (pyte) before interpretation.

## API

```python
# Execute command
run(session_id, command, timeout=30) -> {status, output, screen, state_reason}

# Send raw input (no newline)
send_input(session_id, text, timeout=30) -> {status, output, screen, state_reason}

# Send password securely (not logged)
send_password(session_id, password, timeout=30) -> {status, output, screen, state_reason}

# Send control character
send_control(session_id, key, timeout=5) -> {status, output, screen, state_reason}

# Poll for pending output without input
poll_output(session_id, timeout=0.1) -> {status, output, screen, state_reason}

# Get current screen
read(session_id) -> str

# Get transcript path
transcript(session_id) -> str

# Terminate session
terminate(session_id) -> str
```

Status values: `ready`, `password`, `confirm`, `repl`, `editor`, `pager`, `error`, `running`, `timeout`

`session_id` identifies a stateful PTY. If you start `ssh`, a REPL, or a TUI app in that session, the PTY stays inside it until exit/disconnect; the client agent must decide the next action based on `screen` and `status`.

## Done

- **P0-1**: Quiescence detection (output silence timer)
- **P0-2**: MCP sampling integration + heuristic fallback
- **P0-3**: Simplified API (`run`, `send_input`, `send_password`, `send_control`, `read`, `transcript`)
- **P0-4**: VT100 emulation via pyte
- **P1-1**: Password input (secure, not logged)
- **P1-2**: Interactive confirmations (detected via heuristic/sampling)
- **P1-3**: Output truncation (head+tail with transcript file)
- **P2-1**: REPL sessions (Python, IPython, Ruby, MySQL, etc.)
- **P2-2**: Error recovery (error state detection, Ctrl+C support)
- **P3-1**: Text editors (vim, nano via VT100 + state detection)
- **P3-2**: Multiplexers (tmux, screen - works via screen rendering)
- **P3-3**: Viewers (less, top, htop via pager detection)

## Open Questions

- Sampling latency/cost in production?
- Need dynamic screen size detection?

## Notes

**Playground without LLM**: Heuristic detection handles common cases. Playground shows state detection results; human interprets visually for edge cases.

**State detection priority**: Password > Confirm > Error > REPL > Editor > Pager > Shell prompt > Running
