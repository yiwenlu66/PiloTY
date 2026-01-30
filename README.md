# PiloTY

**AI Pilot for PTY Operations** - An MCP server that enables AI agents to control interactive terminals like a human.

> **⚠️ Work in Progress**: This project is under active development and not ready for production use yet.

> **🔴 Security Warning**: PiloTY provides unrestricted terminal access that can "jailbreak" permission controls. For example, while Claude Code requires approval for each bash command, PiloTY's `run` tool can execute ANY command without additional checks. Only use with trusted AI systems and understand the security implications.

PiloTY (Pilot + PTY) bridges AI agents and terminal interfaces through the Model Context Protocol, providing stateful terminal sessions with support for interactive applications, SSH connections, and background processes.

📖 **[Read the technical design document](TECHNICAL.md)** for detailed architecture and use cases.

## Session Model (Agent Responsibilities)

PiloTY exposes a stateful PTY per `session_id`. Agents must treat `session_id` as a persistent handle:

- Reuse the same `session_id` for a multi-step workflow. Do not generate a new ID per command.
- The PTY keeps process state between calls: working directory, environment variables, running programs.
- If an agent runs `ssh user@host`, the PTY stays inside that SSH session until the agent exits (`exit`, Ctrl+D) or the connection drops.
- If an agent starts a REPL or debugger (Python, pdb, ipdb), the PTY stays inside it until exit.
- The server returns a best-effort `status` plus a rendered `screen`. The agent is responsible for deciding the next action (send input, send control keys, terminate, etc).

## What You Can Do

**Transform natural language into powerful terminal workflows.** With PiloTY, AI agents can control terminals just like experienced developers - maintaining state, managing SSH sessions, and handling complex multi-step operations through simple conversation.

### Stateful Development Workflows

> "Change to my project directory, activate the virtual environment, and run the tests"

> "Install the dependencies, build the project, and run the linter"

### Remote Server Management  

> "SSH into my production server, check the logs in /var/log/, and restart the nginx service"

> "Connect to my database server and show me the current connections"

### Background Process Monitoring

> "Start a long-running data processing script in the background and check on its progress every few minutes"

> "Download a large file using wget in the background and let me know when it's done"

### Interactive Debugging

> "Run my Python script with ipdb and set a breakpoint at line 42 (vibe debugging)"

> "Start a tmux session on my remote server and attach to an existing session"

## Installation

### Option 0: Run with uvx (single command, no install)

If you have `uvx` available, you can run the MCP server directly from the Git repo:

```bash
uvx --from git+https://github.com/yiwenlu66/PiloTY.git piloty
```

### Option 1: Install with uv (Recommended)

The fastest and most reliable way to install PiloTY:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install PiloTY globally
uv tool install git+https://github.com/yiwenlu66/PiloTY.git

# Update shell PATH if needed
uv tool update-shell
```

### Option 2: Install with pipx

Alternative installation using pipx:

```bash
# Install pipx if you haven't already
python -m pip install --user pipx
pipx ensurepath

# Install PiloTY
pipx install git+https://github.com/yiwenlu66/PiloTY.git
```

### Option 3: Install from source

For development or testing:

```bash
git clone https://github.com/yiwenlu66/PiloTY.git
cd PiloTY

# Using uv (recommended)
uv tool install .

# Or using pip in development mode
pip install -e .
```

After installation, verify the `piloty` command is available:

```bash
which piloty  # Should show the installed location
```

## Setup with AI Agents

### Claude Code

Add PiloTY to your Claude Code configuration in `~/.claude.json`:

#### Option A: Installed `piloty`

```json
{
  "mcpServers": {
    "piloty": {
      "command": "piloty"
    }
  }
}
```

#### Option B: `uvx` single-command runner

```json
{
  "mcpServers": {
    "piloty": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/yiwenlu66/PiloTY.git", "piloty"]
    }
  }
}
```

**Important**: Restart Claude Code completely after adding the configuration.

### Claude Desktop

Add the following to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "piloty": {
      "command": "piloty"
    }
  }
}
```

## Features

- **Stateful Terminal Sessions**: Maintains context across commands
- **Interactive Programs via PTY**: SSH, REPLs, debuggers, pagers, and TUIs (best-effort state detection)
- **Background Sessions**: Long-running commands can be monitored by polling output and reading screen state
- **Session Logging**: Logs to `~/.piloty/` for inspection and debugging
- **PTY Control**: Terminal emulation with control keys for interrupts and navigation

## Roadmap

### ✅ Currently Supported
- **Stateful shell sessions** - Commands maintain context and working directory
- **SSH sessions** - PTY remains in SSH until `exit`/disconnect
- **Background processes** - Use shell job control (`&`, `jobs -l`) plus output polling
- **REPL/debugger loops** - Python REPL and breakpoint-driven debugging inside a persistent PTY
- **Best-effort TUI handling** - vim/tmux/pagers do not crash the server; agent drives via screen+keys

### 🚧 Coming Soon
- **More reliable state detection** - Reduce false READY/RUNNING classifications
- **Stronger background job introspection** - Job tracking beyond `jobs -l`
- **Safer credential workflows** - Reduce accidental screen/echo exposure risks
- **Multi-session management** - Coordinate multiple terminal sessions simultaneously

## Session Logging

PiloTY automatically logs all terminal sessions to `~/.piloty/` for debugging and inspection:

- **Active sessions**: `~/.piloty/active/` (symlinks to active sessions)
- **Session history**: `~/.piloty/sessions/` (persistent logs for all sessions)
- **Command history**: Timestamped commands and outputs
- **Session state**: Best-effort state snapshot (e.g., screen render health)

Use the [session viewer tool](tools/README.md) to inspect session logs, or browse the files directly with standard UNIX tools like `tail`, `grep`, and `cat`.

## Testing Integration

After configuration, test PiloTY in Claude Code by asking it to perform terminal tasks:

> "Please run 'echo Hello from PiloTY' in a terminal session"

> "Change to the /tmp directory and show me the current working directory"

> "SSH into my server and check the disk usage with df -h"

> "Start a background process to download a file and monitor its progress"

> "Check what background jobs are running in my session"

The AI will automatically use PiloTY's MCP tools to execute these requests while maintaining session state across commands.

## Developer Resources

- **[Development Guide](DEVELOPMENT.md)**: Architecture details and how to extend PiloTY
- **[Developer Tools](tools/README.md)**: Interactive PTY playground for testing
- **[Technical Design](TECHNICAL.md)**: Detailed architecture and philosophy

## Testing and Development

### Manual Testing

For hands-on testing and development:

```bash
python tools/pty_playground.py
```

### Integration Testing

Use PiloTY through AI agents (Claude Code, Claude Desktop, etc.) by asking them to perform terminal tasks in natural language.

### Automated Tests

Run the test suite:

```bash
python -m pytest
```

## Acknowledgments

PiloTY is built upon the foundational work of [pty-mcp](https://github.com/qodo-ai/pty-mcp) by [Qodo](https://github.com/qodo-ai). We extend our gratitude to the original authors for creating the initial MCP terminal server implementation that made this project possible.

## License

This project is licensed under the Apache License 2.0 - see `LICENSE`.
