"""MCP server interface for PiloTY."""

import signal
import sys
import logging
from mcp.server.fastmcp import FastMCP

from .core import ShellSession
from .handlers import ssh

# Configure file logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler = logging.FileHandler("/tmp/piloty.log")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class SessionManager:
    """Manages multiple ShellSession instances identified by session_id."""

    def __init__(self):
        self.sessions: dict[str, ShellSession] = {}

    def get_session(self, session_id: str) -> ShellSession:
        """Retrieve an existing ShellSession by ID, or create a new one if not present."""
        if session_id not in self.sessions:
            self.sessions[session_id] = ShellSession()
        return self.sessions[session_id]

    def terminate_all_sessions(self):
        """Terminate all active shell sessions."""
        for session_id, session in self.sessions.items():
            session.terminate()
        self.sessions.clear()


# Initialize the MCP server (no authentication required)
mcp = FastMCP("PiloTY", dependencies=["pexpect"])

# Instantiate a single SessionManager to manage shell sessions
session_manager = SessionManager()


@mcp.tool()
def run(session_id: str, command: str) -> str:
    """
    Execute a shell command in an interactive session and return its output.

    Args:
        session_id: The ID of the shell session to execute the command in.
        command: The command to execute in the shell session.

    Returns:
        The output of the command.

    Example:
        >>> run("session1", "pwd")
        '/home/user'
        >>> run("session1", "cd /tmp")
        ''
        >>> run("session1", "pwd")
        '/tmp'

    Tip: if you're getting repeated "Error: Command timed out" errors, try using a different session_id.
    """
    # Get or create the shell session for the given session_id
    session = session_manager.get_session(session_id)
    
    # Check for SSH command
    if ssh.detect_ssh_command(command):
        output, state_updates = ssh.handle_ssh_connection(session, command)
        session.update_state(state_updates)
        return output
    
    # Check for SSH exit
    if session.is_ssh_session and command.strip() == 'exit':
        output, state_updates = ssh.handle_ssh_exit(session, command)
        session.update_state(state_updates)
        return output
    
    # Default execution
    return session.run(command)


@mcp.tool()
def monitor_output(session_id: str, duration: float = 1.0, flush: bool = True) -> str:
    """
    Poll PTY output for a specified duration without running any commands.
    
    Background process output is buffered by the kernel's TTY subsystem. The flush
    parameter triggers a minimal PTY interaction (space+backspace) to make buffered
    data available for reading.
    
    Args:
        session_id: The ID of the shell session to monitor.
        duration: How long to poll for output (in seconds, max 10).
        flush: If True, trigger kernel buffer flush to get background output.
    
    Returns:
        Any output available from the PTY.
    
    Example:
        >>> run("session1", "for i in {1..5}; do echo $i; sleep 1; done &")
        '[1] 12345'
        >>> monitor_output("session1", flush=True)  # Gets background output
        '1\n2\n3\n4\n5\n[1]+  Done  for i in {1..5}...'
    """
    # Limit duration to reasonable values
    duration = min(duration, 10.0)
    session = session_manager.get_session(session_id)
    return session.poll_output(timeout=duration, flush=flush)


@mcp.tool()
def get_session_info(session_id: str) -> dict:
    """
    Get information about the current session state.
    
    This is useful for checking if you're in an SSH session or local shell.
    
    Args:
        session_id: The ID of the shell session to check.
    
    Returns:
        Dictionary with session information:
        - is_ssh: Whether currently in an SSH session
        - ssh_host: The remote host if in SSH, None otherwise
        - prompt: The current prompt being used
    
    Example:
        >>> run("session1", "ssh user@server")
        'Connected to user@server'
        >>> get_session_info("session1")
        {'is_ssh': True, 'ssh_host': 'user@server', 'prompt': 'REMOTE_MCP> '}
    """
    session = session_manager.get_session(session_id)
    return session.get_session_info()


@mcp.tool()
def check_jobs(session_id: str) -> list[dict]:
    """
    Get status of all background jobs in the session.
    
    Args:
        session_id: The ID of the shell session to check.
        
    Returns:
        List of job dictionaries with keys:
        - job_id: Job number
        - pid: Process ID
        - status: Job status (Running, Done, etc.)
        - command: Command being executed
        
    Example:
        >>> run("session1", "sleep 10 &")
        '[1] 12345'
        >>> check_jobs("session1")
        [{'job_id': 1, 'pid': 12345, 'status': 'Running', 'command': 'sleep 10 &'}]
    """
    session = session_manager.get_session(session_id)
    return session.check_jobs()


def signal_handler(sig, frame):
    """Handle signals like SIGINT and SIGTERM."""
    session_manager.terminate_all_sessions()
    sys.exit(0)


def main():
    """Main entry point for the MCP server."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Handle kill/system shutdown

    # Start the MCP server (synchronous startup)
    mcp.run()


if __name__ == "__main__":
    main()