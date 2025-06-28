# PiloTY Developer Tools

This directory contains utilities for developing and testing PiloTY.

## Session Viewer

The Session Viewer (`session_viewer.py`) allows you to inspect PTY session logs stored in `~/.piloty/`.

### Usage

```bash
# List active sessions
python tools/session_viewer.py list

# List all sessions (including ended ones)
python tools/session_viewer.py list --all

# Show detailed session information
python tools/session_viewer.py info <session-id>

# Show command history
python tools/session_viewer.py commands <session-id>
python tools/session_viewer.py commands <session-id> -n 10  # Last 10 commands

# Show formatted command/output interactions
python tools/session_viewer.py interactions <session-id>
python tools/session_viewer.py interactions <session-id> -n 5  # Last 5 interactions

# Tail session transcript (raw PTY output)
python tools/session_viewer.py tail <session-id>
python tools/session_viewer.py tail -f <session-id>  # Follow in real-time

# Clean up stale session symlinks
python tools/session_viewer.py cleanup
```

### Session Files

Each session creates these files in `~/.piloty/sessions/<session-id>/`:
- `session.json` - Metadata (start/end time, PID, initial directory)
- `commands.log` - Timestamped list of executed commands
- `transcript.log` - Raw PTY output (includes prompts, ANSI codes)
- `interaction.log` - Formatted command/output pairs for easy reading
- `state.json` - Current state (directory, active handler, background jobs)

Active sessions have symlinks in `~/.piloty/active/`.

## PTY Playground

The PTY Playground (`pty_playground.py`) is an interactive tool that allows developers to test and explore PiloTY's functionality without going through the MCP interface.

### Usage

Run the playground from the project root:

```bash
python tools/pty_playground.py
```

Or make it executable:

```bash
chmod +x tools/pty_playground.py
./tools/pty_playground.py
```

### Features

The playground provides a REPL-like interface where you can:

1. **Execute shell commands** - Type any command to run it in the PTY session
2. **Use slash commands** - Special commands for interacting with PiloTY's API

### Available Slash Commands

- `/help` - Show available commands
- `/exit`, `/quit` - Exit the playground
- `/poll_output [timeout] [flush]` - Poll for background process output
  - `timeout`: How long to wait (default: 0.1 seconds)
  - `flush`: Whether to flush kernel buffers (default: true)
- `/check_jobs` - Check status of background jobs
- `/session_info` - Get current session information (handler state, etc.)

### Example Session

```
🎮 PTY Playground - Interactive Terminal Control
==================================================
This tool lets you interact with PiloTY directly.
Type /help for available commands or /exit to quit
--------------------------------------------------

> echo "Hello from PTY Playground"

Running: echo "Hello from PTY Playground"
Output:
Hello from PTY Playground

> sleep 5 &

Running: sleep 5 &
Output:
[1] 12345

> /check_jobs

API Result (check_jobs):
[
  {
    "job_id": 1,
    "pid": 12345,
    "status": "Running",
    "command": "sleep 5 &"
  }
]

> ssh user@example.com

Running: ssh user@example.com
Output:
Error: SSH connection failed: Could not resolve hostname example.com

> /session_info

API Result (session_info):
{
  "prompt": "MCP> ",
  "has_active_handler": false,
  "active": false,
  "handler_type": null,
  "context": null
}

> /exit

Session terminated
```

### Use Cases

1. **Testing new handlers** - Verify handler activation and behavior
2. **Debugging PTY issues** - See exactly what's happening in the terminal
3. **Testing edge cases** - Try complex command sequences interactively
4. **Understanding PiloTY's API** - Explore what each method returns

### Tips

- Use `/poll_output` after starting background processes to see their output
- The playground shows raw API responses, making it easy to understand what MCP clients will receive
- Regular commands (not starting with `/`) are sent directly to the PTY
- To send "exit" to an SSH session (not exit the playground), type `exit` without the slash

## Adding New Tools

When adding new developer tools:

1. Place them in this directory
2. Add documentation to this README
3. Ensure they use relative imports to access PiloTY modules
4. Consider adding them to pyproject.toml if they should be installed as scripts