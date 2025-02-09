# pty-mcp

An MCP tool server that provides a stateful terminal.

## Installation

### Option 1: Install with pipx (Recommended)

This is the recommended way to install pty-mcp as it creates an isolated environment:

1. Install pipx if you haven't already:
   ```bash
   python -m pip install --user pipx
   pipx ensurepath
   ```

2. Install pty-mcp:
   ```bash
   pipx install git+https://github.com/qodo-ai/pty-mcp.git
   ```

The server will be available as `pty-mcp` in your path.