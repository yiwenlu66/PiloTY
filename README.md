# PiloTY

**AI Pilot for PTY Operations** - An MCP server that enables AI agents to control interactive terminals like a human.

> **⚠️ Work in Progress**: This project is under active development and not ready for production use yet.

PiloTY (Pilot + PTY) bridges AI agents and terminal interfaces through the Model Context Protocol, providing stateful terminal sessions with support for interactive applications, SSH connections, and background processes.

📖 **[Read the technical design document](TECHNICAL.md)** for detailed architecture and use cases.

## Acknowledgments

PiloTY is built upon the foundational work of [pty-mcp](https://github.com/qodo-ai/pty-mcp) by [Qodo](https://github.com/qodo-ai). We extend our gratitude to the original authors for creating the initial MCP terminal server implementation that made this project possible.

## Installation

### Option 1: Install with pipx (Recommended)

This is the recommended way to install PiloTY as it creates an isolated environment:

1. Install pipx if you haven't already:
   ```bash
   python -m pip install --user pipx
   pipx ensurepath
   ```

2. Install PiloTY:
   ```bash
   pipx install git+https://github.com/yiwenlu66/PiloTY.git
   ```

The server will be available as `piloty` in your path.

### Option 2: Install from source

For development or testing:

```bash
git clone https://github.com/yiwenlu66/PiloTY.git
cd PiloTY
pip install -e .
```

## Usage with Claude Desktop

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
- **Interactive Program Support**: SSH, vim, less, and more coming soon
- **Background Process Management**: Run and monitor long-running processes
- **Handler Architecture**: Extensible system for adding new interactive programs
- **PTY Control**: True terminal emulation for authentic interactions

## Developer Resources

- **[Development Guide](DEVELOPMENT.md)**: Architecture details and how to extend PiloTY
- **[Developer Tools](tools/README.md)**: Interactive PTY playground for testing
- **[Technical Design](TECHNICAL.md)**: Detailed architecture and philosophy

## Quick Examples

### Basic Commands
```python
# Execute commands with persistent state
run("cd /tmp")
run("pwd")  # Returns: /tmp

# Background processes
run("sleep 10 &")
check_jobs()  # Shows running background job
monitor_output()  # Polls for background output
```

### SSH Sessions
```python
# Interactive SSH (requires key-based auth)
run("ssh user@host")
run("ls -la")  # Runs on remote host
run("exit")   # Returns to local shell
```

## Testing

Run the test suite:

```bash
python tests/test_background_processes.py
python tests/test_poll_output.py
python tests/test_ssh.py
```

For interactive testing, use the PTY playground:

```bash
python tools/pty_playground.py
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.