"""PiloTY: AI Pilot for PTY Operations.

Quiescence-based PTY with LLM sampling for state interpretation.
"""

from .core import PTY
from .mcp_server import (
    session_manager,
    run,
    send_input,
    send_password,
    send_control,
    poll_output,
    read,
    transcript,
    terminate,
    detect_state_heuristic,
)

__version__ = "0.3.0"
__all__ = [
    "PTY",
    "session_manager",
    "run",
    "send_input",
    "send_password",
    "send_control",
    "poll_output",
    "read",
    "transcript",
    "terminate",
    "detect_state_heuristic",
]
