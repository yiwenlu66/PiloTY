"""MCP server interface for PiloTY.

Quiescence-based PTY with LLM sampling for state interpretation.
"""

import signal
import sys
import logging
import os
import asyncio
import re
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import SamplingMessage, TextContent

from .core import PTY

logger = logging.getLogger(__name__)


def _configure_logging():
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    log_path = os.getenv("PILOTY_LOG_PATH", "/tmp/piloty.log")
    try:
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        return
    except Exception:
        pass

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


TERMINAL_STATE_PROMPT = """Analyze this terminal screen and determine its state.

Screen content:
```
{screen}
```

What is the terminal state? Answer with exactly one of:
- READY: Shell prompt visible, waiting for command (e.g., $, #, >, PS1)
- PASSWORD: Asking for password (e.g., "Password:", "Enter passphrase")
- CONFIRM: Asking for confirmation (e.g., "[Y/n]", "Continue?", "Are you sure?")
- REPL: Interactive interpreter prompt (e.g., ">>>", "In [1]:", "irb>", "mysql>")
- EDITOR: Text editor active (e.g., vim, nano, emacs)
- PAGER: Pager active (e.g., less, more, man page)
- RUNNING: Command still executing, no prompt visible
- ERROR: Error message visible
- UNKNOWN: Cannot determine state

Respond with just the state name and a brief reason, e.g.:
READY: bash prompt visible
PASSWORD: SSH asking for password
CONFIRM: apt asking to continue"""


class SessionManager:
    """Manages multiple PTY instances."""

    def __init__(self):
        self.sessions: dict[str, PTY] = {}
        self._passwords: dict[str, str] = {}  # session_id -> password (not logged)
        self._last_used: dict[str, float] = {}
        self._max_sessions: int = int(os.getenv("PILOTY_MAX_SESSIONS", "32"))

    def get_session(self, session_id: str) -> PTY:
        """Get or create PTY session."""
        existing = self.sessions.get(session_id)
        if existing is not None and not existing.alive:
            try:
                existing.terminate()
            except Exception:
                pass
            self.sessions.pop(session_id, None)
            self._last_used.pop(session_id, None)

        if session_id not in self.sessions:
            if self._max_sessions > 0 and len(self.sessions) >= self._max_sessions:
                oldest_id = min(self._last_used, key=self._last_used.get, default=None)
                if oldest_id is not None:
                    try:
                        self.sessions[oldest_id].terminate()
                    except Exception:
                        pass
                    self.sessions.pop(oldest_id, None)
                    self._last_used.pop(oldest_id, None)
            self.sessions[session_id] = PTY(session_id=session_id)
        self._last_used[session_id] = time.monotonic()
        return self.sessions[session_id]

    def set_password(self, session_id: str, password: str):
        """Store password for session (not logged)."""
        self._passwords[session_id] = password

    def get_password(self, session_id: str) -> Optional[str]:
        """Get stored password for session."""
        return self._passwords.get(session_id)

    def clear_password(self, session_id: str):
        """Clear stored password."""
        self._passwords.pop(session_id, None)

    def terminate_all(self):
        """Terminate all sessions."""
        for session in self.sessions.values():
            session.terminate()
        self.sessions.clear()
        self._passwords.clear()


# Initialize MCP server
mcp = FastMCP("PiloTY", dependencies=["pexpect", "pyte"])
session_manager = SessionManager()


async def interpret_terminal_state(
    ctx: Context,
    screen: str,
) -> tuple[str, str]:
    """Use LLM sampling to interpret terminal state.

    Returns:
        (state, reason) tuple
    """
    try:
        result = await ctx.session.create_message(
            messages=[
                SamplingMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=TERMINAL_STATE_PROMPT.format(screen=screen),
                    ),
                )
            ],
            max_tokens=50,
        )

        if result.content.type == "text":
            response = result.content.text.strip()
            if ":" in response:
                state, reason = response.split(":", 1)
                return state.strip().upper(), reason.strip()
            m = re.search(r"\b(READY|PASSWORD|CONFIRM|REPL|EDITOR|PAGER|RUNNING|ERROR|UNKNOWN)\b", response.upper())
            if m:
                state = m.group(1)
                reason = response[m.end() :].strip(" \t\r\n:-")
                return state, reason
            return "UNKNOWN", response[:100]
        return "UNKNOWN", "sampling failed"
    except Exception as e:
        logger.warning(f"Sampling failed: {e}")
        return "UNKNOWN", str(e)


def detect_state_heuristic(screen: str) -> tuple[str, str]:
    """Fast heuristic state detection (no LLM).

    Used as fallback when sampling unavailable.
    """
    lines = screen.strip().split("\n")
    if not lines:
        return "UNKNOWN", "empty screen"

    last_line = lines[-1] if lines else ""
    last_line_lower = last_line.lower()
    last_line_stripped = last_line.rstrip()  # Keep leading spaces, strip trailing
    screen_lower = screen.lower()

    # Password prompts (check early - high priority)
    # Match various password prompt formats
    password_patterns = [
        "password:",
        "password for",
        "passphrase:",
        "passphrase for",
        "enter password",
        "enter passphrase",
        "secret:",
        "[sudo]",  # sudo password prompt often contains this
    ]
    for pattern in password_patterns:
        if pattern in screen_lower and ("password" in screen_lower or "passphrase" in screen_lower):
            return "PASSWORD", f"password prompt detected"
    # Direct password keyword check
    if screen_lower.rstrip().endswith(("password:", "passphrase:", "password: ", "passphrase: ")):
        return "PASSWORD", "ends with password prompt"

    # Confirmation prompts
    confirm_indicators = ["[y/n]", "[yes/no]", "continue?", "are you sure", "proceed?"]
    for indicator in confirm_indicators:
        if indicator in screen_lower:
            return "CONFIRM", f"found '{indicator}'"

    # Error detection (check before REPL since traceback contains "...")
    error_indicators = ["error:", "failed:", "fatal:", "exception:", "traceback"]
    for indicator in error_indicators:
        if indicator in screen_lower:
            return "ERROR", f"found '{indicator}'"

    # REPL prompts - check exact patterns
    # Use original last_line to preserve case and spacing
    repl_patterns = [
        (">>> ", "python"),
        (">>>", "python"),  # Also match without trailing space
        ("... ", "python continuation"),
        ("...", "python continuation"),  # Match without trailing space
        ("in [", "ipython"),
        ("out[", "ipython output"),
        ("irb(", "ruby"),
        ("pry(", "pry"),
        ("mysql>", "mysql"),
        ("postgres", "postgres"),
        ("sqlite>", "sqlite"),
    ]
    for prompt, name in repl_patterns:
        if prompt in last_line or prompt in last_line_lower:
            return "REPL", f"{name} prompt"

    # Editor detection (vim, nano)
    if "-- insert --" in screen_lower or "-- normal --" in screen_lower:
        return "EDITOR", "vim mode indicator"
    if "gnu nano" in screen_lower or "^g get help" in screen_lower:
        return "EDITOR", "nano indicators"

    # Pager detection
    if last_line_stripped == ":" or "(end)" in last_line_lower or "manual page" in screen_lower:
        return "PAGER", "pager indicators"

    # Shell prompts - must look like actual prompts, not progress bars
    # Require typical prompt structure: ends with $ # or > but not inside brackets
    shell_ends = ["$", "#"]
    for end in shell_ends:
        if last_line_stripped.endswith(end):
            # Exclude if it looks like a progress bar or percentage
            if "%" in last_line_stripped or "[" in last_line_stripped and "]" in last_line_stripped:
                continue
            # Likely a shell prompt
            return "READY", f"shell prompt '{end}'"
        # Also check with trailing space
        if last_line.rstrip().endswith(end + " ") or last_line.endswith(end + " "):
            return "READY", f"shell prompt '{end}'"

    # Check for common prompt formats: user@host:path$ or bash-5.3$
    if "@" in last_line_stripped and ("$" in last_line_stripped or "#" in last_line_stripped):
        return "READY", "user@host prompt"
    if last_line_stripped.startswith("bash") and "$" in last_line_stripped:
        return "READY", "bash prompt"

    # Special case: bare > prompt (but not inside progress bars or with percentages)
    if last_line_stripped.endswith(">"):
        # Exclude progress bars and percentages
        if "%" not in last_line_stripped and "[" not in last_line_stripped:
            if len(last_line_stripped) < 50:  # Prompts are usually short
                return "READY", "generic prompt"

    # zsh prompt: ends with %
    if last_line_stripped.endswith("%") or last_line.rstrip().endswith("% "):
        # Exclude percentages in progress bars (e.g., "50%")
        if not last_line_stripped[-2:-1].isdigit():
            return "READY", "zsh prompt"

    return "RUNNING", "no prompt detected"


@mcp.tool()
async def run(
    session_id: str,
    command: str,
    timeout: float = 30.0,
    ctx: Context | None = None,
) -> dict:
    """Execute a command in a stateful PTY session.

    This is a stateful terminal: the PTY persists across calls per `session_id`.
    If you start an interactive program (ssh, python, pdb, vim, tmux), the PTY
    stays inside it until you exit or the program ends.

    Return timing: waits until output has been silent for ~500ms (quiescence) or
    until `timeout` seconds elapse. Quiescence is not equivalent to "process
    completed" for programs that are silent while still running or waiting.

    Args:
        session_id: Session identifier. Reuse the same ID to keep context.
        command: Command to execute (newline added automatically).
        timeout: Maximum wait time in seconds

    Returns:
        {
            "status": "ready" | "password" | "confirm" | "repl" | "editor" | "pager" | "error" | "timeout",
            "output": str,
            "screen": str,
            "state_reason": str
        }
    """
    session = session_manager.get_session(session_id)

    # Send command with newline
    result = await asyncio.to_thread(session.type, command + "\n", timeout=timeout, quiescence_ms=500)

    # Get rendered screen
    screen = await asyncio.to_thread(session.read)

    # Interpret state
    if ctx and ctx.session:
        state, reason = await interpret_terminal_state(ctx, screen)
    else:
        state, reason = detect_state_heuristic(screen)

    # Map state to status
    status_map = {
        "READY": "ready",
        "PASSWORD": "password",
        "CONFIRM": "confirm",
        "REPL": "repl",
        "EDITOR": "editor",
        "PAGER": "pager",
        "ERROR": "error",
        "RUNNING": "running",
        "UNKNOWN": "running",
    }
    status = status_map.get(state, "running")

    # Handle timeout
    if result["status"] == "timeout":
        status = "timeout"
    if result["status"] == "eof":
        status = "error"
        reason = (reason + " " if reason else "") + "pty eof"
    if result["status"] == "error":
        status = "error"
        reason = (reason + " " if reason else "") + str(result.get("error", "pty error"))

    return {
        "status": status,
        "output": result["output"],
        "screen": screen,
        "state_reason": reason,
    }


@mcp.tool()
async def send_input(
    session_id: str,
    text: str,
    timeout: float = 30.0,
    ctx: Context | None = None,
) -> dict:
    """Send raw input to a stateful terminal session (no newline added).

    Use for:
    - Answering confirmation prompts (y/n)
    - Sending text to REPL
    - Navigating TUI programs
    - Any input that doesn't need a newline automatically added

    Args:
        session_id: Session identifier. Reuse the same ID to keep context.
        text: Text to send (exactly as provided, no newline added)
        timeout: Maximum wait time

    Returns:
        Same as run() - status, output, screen, state_reason
    """
    session = session_manager.get_session(session_id)

    result = await asyncio.to_thread(session.type, text, timeout=timeout, quiescence_ms=500)
    screen = await asyncio.to_thread(session.read)

    if ctx and ctx.session:
        state, reason = await interpret_terminal_state(ctx, screen)
    else:
        state, reason = detect_state_heuristic(screen)

    status_map = {
        "READY": "ready",
        "PASSWORD": "password",
        "CONFIRM": "confirm",
        "REPL": "repl",
        "EDITOR": "editor",
        "PAGER": "pager",
        "ERROR": "error",
        "RUNNING": "running",
        "UNKNOWN": "running",
    }
    status = status_map.get(state, "running")

    if result["status"] == "timeout":
        status = "timeout"
    if result["status"] == "eof":
        status = "error"
        reason = (reason + " " if reason else "") + "pty eof"
    if result["status"] == "error":
        status = "error"
        reason = (reason + " " if reason else "") + str(result.get("error", "pty error"))

    return {
        "status": status,
        "output": result["output"],
        "screen": screen,
        "state_reason": reason,
    }


@mcp.tool()
async def send_password(
    session_id: str,
    password: str,
    timeout: float = 30.0,
    ctx: Context | None = None,
) -> dict:
    """Send a password to the terminal (best-effort redaction).

    The password is sent with a newline. Transcript logging is disabled for the
    duration of this call, but screen rendering may still show echoed text if
    the remote program echoes input.

    Args:
        session_id: Session identifier. Reuse the same ID to keep context.
        password: Password to send (will add newline)
        timeout: Maximum wait time

    Returns:
        Same as run() - status, output, screen, state_reason
    """
    session = session_manager.get_session(session_id)

    try:
        result = await asyncio.to_thread(
            session.type,
            password + "\n",
            timeout=timeout,
            quiescence_ms=500,
            log=False,
        )
    except TypeError:
        # Back-compat if PTY.type() does not accept log= yet.
        result = await asyncio.to_thread(session.type, password + "\n", timeout=timeout, quiescence_ms=500)

    try:
        screen = await asyncio.to_thread(session.read, log=False)
    except TypeError:
        screen = await asyncio.to_thread(session.read)

    if ctx and ctx.session:
        state, reason = await interpret_terminal_state(ctx, screen)
    else:
        state, reason = detect_state_heuristic(screen)

    status_map = {
        "READY": "ready",
        "PASSWORD": "password",
        "CONFIRM": "confirm",
        "REPL": "repl",
        "EDITOR": "editor",
        "PAGER": "pager",
        "ERROR": "error",
        "RUNNING": "running",
        "UNKNOWN": "running",
    }
    status = status_map.get(state, "running")

    if result["status"] == "timeout":
        status = "timeout"
    if result["status"] == "eof":
        status = "error"
        reason = (reason + " " if reason else "") + "pty eof"
    if result["status"] == "error":
        status = "error"
        reason = (reason + " " if reason else "") + str(result.get("error", "pty error"))

    return {
        "status": status,
        "output": "[password sent]",  # Don't return actual output which might echo
        "screen": screen,
        "state_reason": reason,
    }


@mcp.tool()
async def send_control(
    session_id: str,
    key: str,
    timeout: float = 5.0,
    ctx: Context | None = None,
) -> dict:
    """Send a control character to the terminal (Ctrl+key).

    Args:
        session_id: Session identifier. Reuse the same ID to keep context.
        key: Control key - one of: c (^C), d (^D), z (^Z), l (^L clear),
             [ (escape), or any letter for Ctrl+letter
        timeout: Maximum wait time

    Returns:
        Same as run() - status, output, screen, state_reason
    """
    session = session_manager.get_session(session_id)

    # Map key to control character
    key = key.lower()
    if key == "[" or key == "escape" or key == "esc":
        char = "\x1b"  # Escape
    elif len(key) == 1 and key.isalpha():
        char = chr(ord(key) - ord("a") + 1)  # Ctrl+letter
    else:
        return {"status": "error", "output": f"Unknown control key: {key}", "screen": "", "state_reason": ""}

    result = await asyncio.to_thread(session.type, char, timeout=timeout, quiescence_ms=300)
    screen = await asyncio.to_thread(session.read)

    if ctx and ctx.session:
        state, reason = await interpret_terminal_state(ctx, screen)
    else:
        state, reason = detect_state_heuristic(screen)

    status_map = {
        "READY": "ready",
        "PASSWORD": "password",
        "CONFIRM": "confirm",
        "REPL": "repl",
        "EDITOR": "editor",
        "PAGER": "pager",
        "ERROR": "error",
        "RUNNING": "running",
        "UNKNOWN": "running",
    }
    status = status_map.get(state, "running")
    if result["status"] == "timeout":
        status = "timeout"
    if result["status"] == "eof":
        status = "error"
        reason = (reason + " " if reason else "") + "pty eof"
    if result["status"] == "error":
        status = "error"
        reason = (reason + " " if reason else "") + str(result.get("error", "pty error"))

    return {
        "status": status,
        "output": result["output"],
        "screen": screen,
        "state_reason": reason,
    }


@mcp.tool()
async def poll_output(
    session_id: str,
    timeout: float = 0.1,
    ctx: Context | None = None,
) -> dict:
    """Poll for pending output without sending input.

    Intended for long-running commands and background jobs where output arrives
    asynchronously. This does not attempt to force output (no flush keystrokes);
    it only drains whatever the PTY produces.

    Args:
        session_id: Stateful session identifier. Reuse the same ID to keep context.
        timeout: Maximum poll time in seconds.

    Returns:
        Same structure as run(): status, output, screen, state_reason.
    """
    session = session_manager.get_session(session_id)

    result = await asyncio.to_thread(session.poll_output, timeout=timeout, quiescence_ms=100)
    screen = await asyncio.to_thread(session.read)

    if ctx and ctx.session:
        state, reason = await interpret_terminal_state(ctx, screen)
    else:
        state, reason = detect_state_heuristic(screen)

    status_map = {
        "READY": "ready",
        "PASSWORD": "password",
        "CONFIRM": "confirm",
        "REPL": "repl",
        "EDITOR": "editor",
        "PAGER": "pager",
        "ERROR": "error",
        "RUNNING": "running",
        "UNKNOWN": "running",
    }
    status = status_map.get(state, "running")

    if result["status"] == "timeout":
        status = "timeout"
    if result["status"] == "eof":
        status = "error"
        reason = (reason + " " if reason else "") + "pty eof"
    if result["status"] == "error":
        status = "error"
        reason = (reason + " " if reason else "") + str(result.get("error", "pty error"))

    return {
        "status": status,
        "output": result["output"],
        "screen": screen,
        "state_reason": reason,
    }


@mcp.tool()
async def read(session_id: str) -> str:
    """Get current terminal screen content.

    Returns VT100-rendered screen (24x80 by default).
    Escape sequences are processed, giving clean text output.

    Args:
        session_id: Session identifier

    Returns:
        Current screen content as text
    """
    session = session_manager.get_session(session_id)
    return await asyncio.to_thread(session.read)


@mcp.tool()
def transcript(session_id: str) -> str:
    """Get path to transcript file.

    Transcript contains full session output (not truncated).
    Use for searching through history or reviewing full output.

    Args:
        session_id: Session identifier

    Returns:
        Absolute path to transcript file
    """
    session = session_manager.get_session(session_id)
    return session.transcript()


@mcp.tool()
async def terminate(session_id: str) -> str:
    """Terminate a PTY session.

    Args:
        session_id: Session identifier

    Returns:
        Confirmation message
    """
    if session_id in session_manager.sessions:
        await asyncio.to_thread(session_manager.sessions[session_id].terminate)
        del session_manager.sessions[session_id]
        session_manager.clear_password(session_id)
        return f"Session '{session_id}' terminated"
    return f"Session '{session_id}' not found"


def signal_handler(sig, frame):
    """Handle signals for graceful shutdown."""
    session_manager.terminate_all()
    sys.exit(0)


def main():
    """Main entry point for MCP server."""
    _configure_logging()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    mcp.run()


if __name__ == "__main__":
    main()
