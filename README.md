# PiloTY

**AI Pilot for PTY Operations** - An MCP server that enables AI agents to control interactive terminals like a human.

PiloTY (Pilot + PTY) bridges AI agents and terminal interfaces through the Model Context Protocol, providing stateful terminal sessions with support for interactive applications, SSH connections, and background processes.

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