import os

import pexpect
from mcp.server.fastmcp import FastMCP


class ShellSession:
    """Manages an interactive Bash shell session using pexpect."""

    def __init__(self):
        # Define a unique prompt to detect when a command finishes
        self.prompt = "MCP> "
        # Spawn an interactive Bash shell with minimal configuration
        self.process = pexpect.spawn(
            "bash",
            ["--norc", "--noprofile"],
            encoding="utf-8",
            echo=False,
            env={**os.environ, "TERM": "dumb"},
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

    def run(self, command: str) -> str:
        """Execute a command in this shell session and return its output or error."""
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
            return "Error: Command timed out"
        except pexpect.EOF:
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


def main():
    # Start the MCP server (synchronous startup)
    mcp.run()


if __name__ == "__main__":
    main()
