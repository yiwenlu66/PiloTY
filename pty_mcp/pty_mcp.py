import os
import signal
import sys
import pexpect
import logging
import re
from mcp.server.fastmcp import FastMCP

# Configure file logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler = logging.FileHandler("/tmp/pty_mcp.log")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class ShellSession:
    """Manages an interactive Bash shell session using pexpect."""

    def __init__(self):
        self.ps1 = "MCP> "
        self.ps2 = "MCP_CONT> "  # unique PS2
        session_env = {
            **os.environ,
            "TERM": "dumb",  # disable color
            "GIT_PAGER": "cat",  # disable paging for git commands
            "PAGER": "cat",  # disable paging for other tools
        }

        # Start a bare-bones bash
        self.process = pexpect.spawn(
            "bash",
            ["--norc", "--noprofile"],
            encoding="utf-8",
            echo=False,
            env=session_env,
        )

        # Wait for the initial system prompt and then set ours
        try:
            self.process.expect([r"\$ ", r"# "], timeout=5)
        except pexpect.TIMEOUT:
            pass

        # Custom PS1/PS2 so we always know where we are
        self.process.sendline(f"PS1='{self.ps1}'")
        self.process.expect(self.ps1, timeout=5)
        self.process.sendline(f"PS2='{self.ps2}'")
        self.process.expect(self.ps1, timeout=5)

    def terminate(self):
        if self.process.isalive():
            self.process.terminate(force=True)
    
    def get_output_since(self, timeout: float = 0.1) -> str:
        """
        Get any output that appeared since last command without sending a new command.
        
        Note: In practice, background process output is automatically captured by the
        next run() command, so this method may not capture background output as expected.
        Background output and job completion notices appear mixed with the next command's output.
        """
        try:
            output = ""
            while True:
                chunk = self.process.read_nonblocking(size=1024, timeout=timeout)
                if chunk:
                    output += chunk
                else:
                    break
            return output.rstrip("\r\n")
        except pexpect.TIMEOUT:
            return ""
        except pexpect.EOF:
            return ""

    def run(self, command: str, timeout: int = 30) -> str:
        """
        Execute *command* and return stdout/stderr.
        Cancels the command if Bash drops to the continuation prompt.
        """
        logging.info(f"Running command: {command}")
        try:
            self.process.sendline(command)
            idx = self.process.expect([self.ps1, self.ps2], timeout=timeout)

            # idx == 1 -> we matched PS2 -> syntax error / unbalanced quotes
            if idx == 1:
                self.process.sendcontrol("c")  # abort current line
                self.process.expect(self.ps1, timeout=5)
                return "Error: command appears incomplete (unbalanced quotes or parentheses)"

            output = self.process.before or ""
            return output.rstrip("\r\n")

        except pexpect.TIMEOUT:
            logging.error(f"Command timed out: {command}")
            logging.error(f"pexpect 'before': {repr(self.process.before)}")
            return "Error: Command timed out"
        except pexpect.EOF:
            logging.error("Session terminated unexpectedly")
            return "Error: Session terminated unexpectedly"
        except Exception as e:
            return f"Error: {e}"
    
    def run_background(self, command: str) -> dict:
        """Run a command in background and return job info."""
        if not command.rstrip().endswith('&'):
            command = command + ' &'
        
        result = self.run(command)
        
        # Parse job info from output like "[1] 12345"
        match = re.match(r'\[(\d+)\]\s+(\d+)', result)
        if match:
            return {
                'job_id': int(match.group(1)),
                'pid': int(match.group(2)),
                'output': result
            }
        return {'output': result}
    
    def check_jobs(self) -> list[dict]:
        """Get status of all background jobs."""
        output = self.run("jobs -l")
        jobs = []
        
        # Parse jobs output
        # Format: [1]+ 12345 Running   sleep 10 &
        for line in output.split('\n'):
            if line.strip():
                match = re.match(r'\[(\d+)\]([+-]?)\s+(\d+)\s+(\w+)\s+(.+)', line)
                if match:
                    jobs.append({
                        'job_id': int(match.group(1)),
                        'current': match.group(2) == '+',
                        'previous': match.group(2) == '-',
                        'pid': int(match.group(3)),
                        'status': match.group(4),
                        'command': match.group(5)
                    })
        return jobs


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

    Tip: if you're getting repeated "Error: Command timed out" errors, try using a different session_id.
    """
    # Get or create the shell session for the given session_id
    session = session_manager.get_session(session_id)
    # Run the command in the session and return the result
    return session.run(command)


@mcp.tool()
def monitor_output(session_id: str, duration: float = 1.0) -> str:
    """
    Monitor PTY output for a specified duration without running any commands.
    
    Note: Background process output typically appears mixed with the next run() command.
    This tool may not capture background output as expected. To get background process
    output, simply run another command (even an empty echo) and the background output
    will be included.
    
    Args:
        session_id: The ID of the shell session to monitor.
        duration: How long to monitor for output (in seconds, max 10).
    
    Returns:
        Any output that appeared during the monitoring period.
    
    Example:
        >>> run("session1", "echo 'Background task' &")
        '[1] 12345'
        >>> run("session1", "echo 'Next'")  # Background output appears here
        'Background task\nNext\n[1]+  Done  echo "Background task"'
    """
    # Limit duration to reasonable values
    duration = min(duration, 10.0)
    session = session_manager.get_session(session_id)
    return session.get_output_since(timeout=duration)


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
