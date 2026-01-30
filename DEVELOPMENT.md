# PiloTY Development Guide

This guide covers development practices, architecture details, and how to extend PiloTY.

## Project Structure

```
piloty/
├── core.py              # Quiescence-based PTY + VT100 rendering + session logs
├── mcp_server.py        # MCP interface (tools + state detection)
├── handler_manager.py   # Deprecated (legacy docs/import compatibility)
├── handlers/            # Deprecated (legacy docs/import compatibility)
├── session_logger.py    # Deprecated (legacy docs/import compatibility)
└── utils.py             # Deprecated (legacy docs/import compatibility)

tests/                   # Automated tests
tools/                   # Developer utilities
└── pty_playground.py   # Interactive testing tool
```

## Development Setup

1. **Clone and install in development mode:**
   ```bash
   git clone https://github.com/yiwenlu66/PiloTY.git
   cd PiloTY
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

2. **Run tests:**
   ```bash
   python -m pytest
   ```

## Developer Tools

### PTY Playground

The PTY Playground is an interactive REPL for testing PiloTY functionality without the MCP layer:

```bash
python tools/pty_playground.py
```

### Session Viewer

Inspect session logs under `~/.piloty/`:

```bash
python tools/session_viewer.py list
python tools/session_viewer.py info <session-id>
python tools/session_viewer.py tail -f <session-id>
```

## Session Logging

PiloTY automatically logs all sessions to `~/.piloty/`:

- **Active sessions**: Symlinked in `~/.piloty/active/`
- **All sessions**: Stored in `~/.piloty/sessions/`
- **Log files**: commands.log, transcript.log, state.json
- **Disable logging**: Pass `enable_logging=False` to ShellSession

This makes debugging much easier as you can inspect exactly what happened in any session.

## Architecture Overview

### Core Components

1. **ShellSession** (`core.py`)
   - Manages PTY (pseudo-terminal) using pexpect
   - Provides command execution and output polling
   - Integrates with HandlerManager for extensibility

2. **HandlerManager** (`handler_manager.py`)
   - Maintains registry of available handlers
   - Routes commands to appropriate handlers
   - Manages handler lifecycle (activation/deactivation)

3. **InteractiveHandler** (`handlers/base.py`)
   - Abstract base class for all handlers
   - Defines handler interface and lifecycle methods
   - Handlers encapsulate their own state via context objects

4. **MCP Server** (`mcp_server.py`)
   - Exposes PiloTY functionality via Model Context Protocol
   - Manages multiple sessions
   - Provides tools: `run`, `monitor_output`, `get_session_info`, `check_jobs`

### Handler System

Handlers manage interactive programs within the PTY session. Each handler:
- Detects when it should activate (`can_handle`)
- Processes initial connection/startup (`activate`)
- Manages its own prompts and state (`context`)
- Cleans up on exit (`deactivate`)

## Adding a New Handler

To add support for a new interactive program (e.g., vim, ipdb, tmux):

### 1. Create the handler file

Create `piloty/handlers/your_handler.py`:

```python
from dataclasses import dataclass
from typing import Optional
from .base import InteractiveHandler, HandlerContext

@dataclass
class YourContext(HandlerContext):
    """Handler-specific state."""
    # Add your state fields here
    custom_field: str = ""

class YourHandler(InteractiveHandler):
    """Handler for your interactive program."""
    
    def _create_context(self) -> YourContext:
        """Create handler-specific context."""
        return YourContext()
    
    def can_handle(self, command: str) -> bool:
        """Check if this handler should process the command."""
        # Return True if command starts your program
        return command.strip().startswith('your-command')
    
    def activate(self, session, command: str) -> str:
        """Activate handler and process initial command."""
        # Send command to PTY
        session.process.sendline(command)
        
        # Wait for program startup
        # Handle any initial prompts
        # Set up custom prompts if needed
        
        self.context.active = True
        return "Connected to your program"
    
    def deactivate(self, session) -> str:
        """Clean up when exiting."""
        # Send exit command
        # Wait for normal prompt
        self.context.active = False
        return "Exited your program"
```

### 2. Register the handler

In `piloty/core.py`, add to `_register_handlers`:

```python
from .handlers import YourHandler

def _register_handlers(self):
    """Register available handlers."""
    self.handler_manager.register_handler(SSHHandler)
    self.handler_manager.register_handler(YourHandler)  # Add this
```

### 3. Export from handlers module

In `piloty/handlers/__init__.py`:

```python
from .your_handler import YourHandler

__all__ = [..., 'YourHandler']
```

### 4. Test your handler

Create a test file or use the PTY playground:

```python
# In tools/pty_playground.py
> your-command
# Should activate your handler

> /session_info
# Should show your handler as active
```

## Handler Best Practices

1. **State Encapsulation**: Keep all handler state in the context object
2. **Prompt Management**: Handle various shell prompts (bash, zsh, fish, etc.)
3. **Error Handling**: Gracefully handle connection failures and timeouts
4. **Clean Exit**: Always restore the session to a clean state

## Testing

### Unit Tests

Place handler-specific tests in `tests/test_your_handler.py`:

```python
def test_your_handler_detection():
    """Test command detection logic."""
    handler = YourHandler()
    assert handler.can_handle("your-command")
    assert not handler.can_handle("other-command")

def test_your_handler_integration():
    """Test handler with ShellSession."""
    session = ShellSession()
    result = session.run("your-command")
    # Verify handler behavior
```

### Manual Testing

Use the PTY playground for interactive testing:
- Test handler activation/deactivation
- Verify prompt handling
- Check error scenarios
- Test command sequences

## Debugging Tips

1. **Enable logging**: Check `/tmp/piloty.log` for detailed logs
2. **Use PTY playground**: Interactive testing without MCP complexity
3. **Add debug output**: Use `logging.debug()` in handlers
4. **Test prompt patterns**: Use regex testers for prompt matching
5. **Check pexpect state**: `session.process.before` shows buffered output

## Common Issues

### Handler not activating
- Verify `can_handle` logic
- Check command parsing (use shlex for complex commands)
- Ensure handler is registered

### Prompt matching failures
- Test with different shells (bash, zsh, fish)
- Handle ANSI escape sequences
- Consider bracketed paste mode

### Timeout errors
- Increase timeout for slow operations
- Handle network latency for remote connections
- Add intermediate expect patterns

## Contributing

1. **Code style**: Follow PEP 8
2. **Type hints**: Add type annotations where helpful
3. **Documentation**: Update docstrings and README
4. **Tests**: Add tests for new functionality
5. **Commits**: Use conventional commit messages

## Resources

- [pexpect documentation](https://pexpect.readthedocs.io/)
- [MCP specification](https://modelcontextprotocol.io/)
- [PTY/Terminal concepts](https://en.wikipedia.org/wiki/Pseudoterminal)
