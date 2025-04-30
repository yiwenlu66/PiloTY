import os
import signal
import sys
import pexpect
import logging
from mcp.server.fastmcp import FastMCP

# Configure file logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler('/tmp/pty_mcp.log')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class ShellSession:
    """Manages an interactive Bash shell session using pexpect."""

    def __init__(self):
        # Define a unique prompt to detect when a command finishes
        self.prompt = "MCP> "
        # Spawn an interactive Bash shell with minimal configuration
        # Add GIT_PAGER=cat and PAGER=cat to disable paging for git and other tools
        session_env = {**os.environ, "TERM": "dumb", "GIT_PAGER": "cat", "PAGER": "cat"}
        self.process = pexpect.spawn(
            "bash",
            ["--norc", "--noprofile"],
            encoding="utf-8",
            echo=False,
            env=session_env,
        )
        # Initialize the shell prompt to our custom prompt
        try:
            # Wait for the default bash prompt (user or root) to appear
            self.process.expect([r"\$ ", r"# "], timeout=5)
        except pexpect.TIMEOUT:
            # If no prompt seen (should not usually happen), continue anyway
            pass
        # Set the shell prompt to the custom marker
        self.process.sendline(f"PS1='{self.prompt}'")
        self.process.expect(self.prompt)  # wait until the new prompt is ready

    def terminate(self):
        """Terminate the shell process."""
        if self.process.isalive():
            self.process.terminate(force=True)  # Send SIGKILL

    def run(self, command: str) -> str:
        """Execute a command in this shell session and return its output or error."""
        logging.info(f"Running command: {command}")  # Log command start
        try:
            # Send the command to the shell
            self.process.sendline(command)
            # Wait for the prompt to appear again, indicating the command is done
            self.process.expect(self.prompt, timeout=30)
            # Everything before the prompt is the command output
            output = self.process.before  # captured output (excluding the prompt)
            if output is None:
                return ""  # No output
            # Strip trailing newline (and carriage return if any)
            return output.rstrip("\r\n")
        except pexpect.TIMEOUT:
            # Log detailed information on timeout
            logging.error(f"Command timed out: {command}")
            logging.error(f"pexpect 'before' buffer: {repr(self.process.before)}")
            logging.error(f"pexpect 'buffer' content: {repr(self.process.buffer)}")
            return "Error: Command timed out"
        except pexpect.EOF:
            logging.error("Session terminated unexpectedly")
            return "Error: Session terminated unexpectedly"
        except Exception as e:
            return f"Error: {str(e)}"


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
mcp = FastMCP("ShellToolServer", dependencies=["pexpect"])

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
    """
    # Get or create the shell session for the given session_id
    session = session_manager.get_session(session_id)
    # Run the command in the session and return the result
    return session.run(command)


def signal_handler(sig, frame):
    """Handle signals like SIGINT and SIGTERM."""
    session_manager.terminate_all_sessions()
    sys.exit(0)


def main():
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Handle kill/system shutdown

    # Start the MCP server (synchronous startup)
    mcp.run()


if __name__ == "__main__":
    main()
