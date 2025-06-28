"""Core PTY session management functionality."""

import os
import logging
import re
import time
import pexpect

from .utils import clean_output


class ShellSession:
    """Manages an interactive Bash shell session using pexpect."""

    def __init__(self):
        self.ps1 = "MCP> "
        self.ps2 = "MCP_CONT> "  # unique PS2
        
        # Session state (can be updated by handlers)
        self.is_ssh_session = False
        self.ssh_host = None
        self.remote_ps1 = "REMOTE_MCP> "
        self.remote_ps2 = "REMOTE_CONT> "
        
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
        """Terminate the shell session."""
        if self.process.isalive():
            self.process.terminate(force=True)
    
    def poll_output(self, timeout: float = 0.1, flush: bool = True) -> str:
        """
        Poll for any available output from the PTY.
        
        Background process output is buffered by the kernel's TTY subsystem and may not
        be immediately available. The flush parameter triggers a minimal PTY interaction
        to make buffered data available.
        
        Args:
            timeout: Read timeout in seconds
            flush: If True, send space+backspace to trigger kernel buffer flush
            
        Returns:
            Any output available from the PTY
        """
        if flush and self.process.isalive():
            # Send space + backspace to trigger TTY buffer flush
            # This causes minimal side effects while making buffered output available
            self.process.send(' \b')
            time.sleep(0.1)  # Give kernel time to flush buffers
        
        # Now read available output
        try:
            output = ""
            # Read in a loop with short timeout to get all available data
            while True:
                try:
                    chunk = self.process.read_nonblocking(size=2048, timeout=timeout)
                    if chunk:
                        output += chunk
                        # Continue reading with shorter timeout if we got data
                        timeout = 0.05
                    else:
                        break
                except pexpect.TIMEOUT:
                    break
                except pexpect.EOF:
                    break
                    
            # Clean up output - remove any prompts that might have appeared
            if output and self.ps1 in output:
                # Remove prompt if it appears at the end
                output = output.replace(self.ps1, '')
            
            return output.rstrip("\r\n")
        except Exception as e:
            logging.error(f"Error in poll_output: {e}")
            return ""

    def run(self, command: str, timeout: int = 30) -> str:
        """
        Execute command and return stdout/stderr.
        
        Args:
            command: Command to execute
            timeout: Execution timeout in seconds
            
        Returns:
            Command output
        """
        logging.info(f"Running command: {command}")
        
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
                output = clean_output(output, command, is_ssh=True, 
                                    remote_ps1=self.remote_ps1, 
                                    remote_ps2=self.remote_ps2)
            
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
    
    def check_jobs(self) -> list[dict]:
        """Get status of all background jobs."""
        output = self.run("jobs -l")
        jobs = []
        
        # Parse jobs output
        # Format: [1]+ 12345 Running   sleep 10 &
        for line in output.split('\n'):
            if line.strip():
                match = re.match(r'\[(\d+)\][+-]?\s+(\d+)\s+(\w+)\s+(.+)', line)
                if match:
                    jobs.append({
                        'job_id': int(match.group(1)),
                        'pid': int(match.group(2)),
                        'status': match.group(3),
                        'command': match.group(4)
                    })
        return jobs
    
    def get_session_info(self) -> dict:
        """Get current session information."""
        return {
            'is_ssh': self.is_ssh_session,
            'ssh_host': self.ssh_host,
            'prompt': self.remote_ps1 if self.is_ssh_session else self.ps1
        }
    
    def update_state(self, state_updates: dict):
        """
        Update session state from handler results.
        
        Args:
            state_updates: Dictionary with state updates from handlers
        """
        for key, value in state_updates.items():
            if hasattr(self, key):
                setattr(self, key, value)