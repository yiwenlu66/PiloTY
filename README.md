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