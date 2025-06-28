import os
import signal
import sys
import pexpect
import logging
import re
import shlex
import time
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
        self.remote_ps1 = "REMOTE_MCP> "
        self.remote_ps2 = "REMOTE_CONT> "
        self.is_ssh_session = False
        self.ssh_host = None
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
    
    def _clean_output(self, text: str, command: str = None) -> str:
        """Remove common terminal escape sequences and clean output."""
        # Remove ANSI color codes
        text = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', text)
        # Remove bracketed paste mode
        text = re.sub(r'\x1b\[\?2004[hl]', '', text)
        # Remove cursor movement and other sequences
        text = re.sub(r'\x1b\[[\d;]*[A-Za-z]', '', text)
        # Remove other escape sequences
        text = re.sub(r'\x1b[>=\[\]()][\d;]*[A-Za-z]?', '', text)
        # Clean up carriage returns
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove lines that are just prompts or empty
        if self.is_ssh_session:
            lines = text.split('\n')
            cleaned_lines = []
            for line in lines:
                # Skip lines that look like standalone prompts
                stripped = line.strip()
                if stripped and not re.match(r'^[%$#>]\s*$', stripped):
                    # Also skip lines that are just the prompt itself
                    if stripped not in [self.remote_ps1.strip(), self.remote_ps2.strip()]:
                        # Skip the command echo if it appears at the start
                        if command and stripped == command.strip():
                            continue
                        cleaned_lines.append(line)
            text = '\n'.join(cleaned_lines)
        
        return text
    
    def _is_interactive_ssh(self, command: str) -> bool:
        """Detect ssh command without remote command."""
        if not command.strip().startswith('ssh '):
            return False
        
        # Parse SSH command
        try:
            parts = shlex.split(command)
            # Look for patterns like: ssh host, ssh user@host, ssh -p 2222 host
            # But not: ssh host "command"
            ssh_idx = parts.index('ssh')
            # Skip flags
            i = ssh_idx + 1
            while i < len(parts) and parts[i].startswith('-'):
                # Handle flags that take arguments
                if parts[i] in ['-p', '-l', '-o', '-i', '-F']:
                    i += 2
                else:
                    i += 1
            # If we reach end or next part doesn't look like command, it's interactive
            return i < len(parts) and i + 1 >= len(parts)
        except:
            return False
    
    def _extract_ssh_host(self, ssh_command: str) -> str:
        """Extract hostname from SSH command."""
        try:
            parts = shlex.split(ssh_command)
            ssh_idx = parts.index('ssh')
            # Skip flags
            i = ssh_idx + 1
            while i < len(parts) and parts[i].startswith('-'):
                if parts[i] in ['-p', '-l', '-o', '-i', '-F']:
                    i += 2
                else:
                    i += 1
            # Next non-flag argument should be the host
            if i < len(parts):
                return parts[i]
        except:
            pass
        return "unknown"
    
    def _handle_ssh_connection(self, ssh_command: str, timeout: int) -> str:
        """Handle interactive SSH connection."""
        # Send SSH command
        self.process.sendline(ssh_command)
        
        # Wait for connection (various possible prompts)
        patterns = [
            r'[Pp]assword:',  # Password prompt
            r'[$#>%] ',  # Common shell ending characters
            r'\$ ',  # Bash/sh style
            r'% ',   # Zsh/csh style  
            r'> ',   # Fish or custom
            r'# ',   # Root prompt
            r'.*@.*[:#~].*[$#%>] ',  # user@host variants
            r'Permission denied',  # Auth failure
            r'Could not resolve',  # DNS failure
            r'Connection refused',  # Connection failure
            pexpect.TIMEOUT
        ]
        
        idx = self.process.expect(patterns, timeout=10)
        
        if idx == 0:  # Password
            self.process.sendcontrol("c")  # Cancel
            self.process.expect(self.ps1, timeout=5)
            return "Error: Password authentication not supported. Please use SSH keys."
        elif idx in [7, 8, 9]:  # Connection failures
            error_msg = self.process.before or "Connection failed"
            self.process.expect(self.ps1, timeout=5)
            return f"Error: SSH connection failed: {error_msg.strip()}"
        elif idx == 10:  # Timeout
            return "Error: SSH connection timed out"
        
        # Connected! Now set remote prompts adaptively
        # Try different methods to set prompt based on shell type
        prompt_commands = [
            (f"PS1='{self.remote_ps1}'", f"PS2='{self.remote_ps2}'"),  # sh/bash without export
            (f"export PS1='{self.remote_ps1}'", f"export PS2='{self.remote_ps2}'"),  # bash/zsh with export
            (f"set prompt='{self.remote_ps1}'", None),  # csh/tcsh style (no PS2)
            (f"set PS1 '{self.remote_ps1}'", None),  # fish style
        ]
        
        prompt_set = False
        for ps1_cmd, ps2_cmd in prompt_commands:
            self.process.sendline(ps1_cmd)
            try:
                # Try to match our custom prompt
                self.process.expect(self.remote_ps1, timeout=1)
                prompt_set = True
                # If PS1 worked and we have PS2 command, set it too
                if ps2_cmd:
                    self.process.sendline(ps2_cmd)
                    try:
                        self.process.expect(self.remote_ps1, timeout=1)
                    except:
                        pass  # PS2 is less critical
                break
            except pexpect.TIMEOUT:
                # This method didn't work, try next
                continue
        
        if not prompt_set:
            # Couldn't set custom prompt, we'll work with whatever the shell has
            logging.warning("Could not set custom prompt on remote shell")
        
        # Clear any remaining output in buffer and sync
        if prompt_set:
            try:
                # Send a sync command and wait for it to complete
                self.process.sendline("echo SYNC_MARKER")
                # Wait for the marker
                self.process.expect("SYNC_MARKER", timeout=2)
                # Now wait for the prompt after the marker
                self.process.expect(self.remote_ps1, timeout=2)
                # Clear the buffer to ensure clean state
                self.process.buffer = ''
            except pexpect.TIMEOUT:
                logging.warning("Could not sync after prompt setup")
                # Try to clear buffer anyway
                try:
                    self.process.read_nonblocking(size=2000, timeout=0.2)
                    self.process.buffer = ''
                except:
                    pass
        else:
            # Try to sync with generic prompt
            try:
                self.process.sendline("echo ready")
                self.process.expect(r'ready', timeout=2)
                self.process.expect(r'[$#>%] ', timeout=2)
            except:
                pass
        
        # Update state
        self.is_ssh_session = True
        self.ssh_host = self._extract_ssh_host(ssh_command)
        
        return f"Connected to {self.ssh_host}"

    def run(self, command: str, timeout: int = 30) -> str:
        """
        Execute *command* and return stdout/stderr.
        Cancels the command if Bash drops to the continuation prompt.
        """
        logging.info(f"Running command: {command}")
        
        # Check for interactive SSH
        if self._is_interactive_ssh(command):
            return self._handle_ssh_connection(command, timeout)
        
        # Handle exit from SSH session
        if self.is_ssh_session and command.strip() == 'exit':
            self.process.sendline(command)
            # Wait for local prompt to return
            try:
                self.process.expect(self.ps1, timeout=5)
                self.is_ssh_session = False
                host = self.ssh_host
                self.ssh_host = None
                return f"Disconnected from {host}"
            except pexpect.TIMEOUT:
                # Maybe connection was already closed
                self.is_ssh_session = False
                self.ssh_host = None
                return "SSH session ended"
        
        # Choose prompts based on current state
        if self.is_ssh_session:
            prompts = [self.remote_ps1, self.remote_ps2]
        else:
            prompts = [self.ps1, self.ps2]
        
        try:
            self.process.sendline(command)
            # Use more specific patterns that match prompts at beginning of line
            # For SSH sessions, we need to be more careful about prompt matching
            if self.is_ssh_session:
                # Match prompts including zsh's % formatting and bracketed paste mode
                # The pattern needs to match: \r\n%[spaces]\r \r\rPROMPT[optional bracketed paste]
                prompt_patterns = [
                    r'(?:\r\n%\s+\r\s+\r)?' + re.escape(prompts[0]) + r'(?:\s*\x1b\[\?2004h)?',  # PS1 with zsh formatting
                    r'(?:\r\n%\s+\r\s+\r)?' + re.escape(prompts[1]) + r'(?:\s*\x1b\[\?2004h)?'   # PS2 with zsh formatting
                ]
            else:
                prompt_patterns = [
                    r'\r?\n?' + re.escape(prompts[0]),  # PS1 at start of line
                    r'\r?\n?' + re.escape(prompts[1])   # PS2 at start of line
                ]
            idx = self.process.expect(prompt_patterns, timeout=timeout)

            # idx == 1 -> we matched PS2 -> syntax error / unbalanced quotes
            if idx == 1:
                self.process.sendcontrol("c")  # abort current line
                self.process.expect(prompt_patterns[0], timeout=5)
                return "Error: command appears incomplete (unbalanced quotes or parentheses)"

            output = self.process.before or ""
            
            # Clean output if in SSH session
            if self.is_ssh_session:
                output = self._clean_output(output, command)
            
            return output.rstrip("\r\n")

        except pexpect.TIMEOUT:
            logging.error(f"Command timed out: {command}")
            logging.error(f"pexpect 'before': {repr(self.process.before)}")
            return "Error: Command timed out"
        except pexpect.EOF:
            logging.error("Session terminated unexpectedly")
            # Reset SSH state if connection dropped
            if self.is_ssh_session:
                self.is_ssh_session = False
                self.ssh_host = None
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
    
    def get_session_info(self) -> dict:
        """Get current session information."""
        return {
            'is_ssh': self.is_ssh_session,
            'ssh_host': self.ssh_host,
            'prompt': self.remote_ps1 if self.is_ssh_session else self.ps1
        }


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
