"""Core PTY session management functionality."""

import os
import logging
import re
import time
import pexpect

from .utils import clean_output
from .handler_manager import HandlerManager
from .handlers import SSHHandler


class ShellSession:
    """Manages an interactive Bash shell session using pexpect."""

    def __init__(self):
        self.ps1 = "MCP> "
        self.ps2 = "MCP_CONT> "  # unique PS2
        
        # Initialize handler manager
        self.handler_manager = HandlerManager()
        self._register_handlers()
        
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
    
    def _register_handlers(self):
        """Register available handlers."""
        self.handler_manager.register_handler(SSHHandler)

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
        
        # First check if handler wants to process this command
        output, handled = self.handler_manager.process_command(self, command)
        if handled:
            return output
        
        # Get prompts from handler or use defaults
        handler_prompts = self.handler_manager.get_prompt_patterns()
        if handler_prompts:
            prompt_patterns = handler_prompts
        else:
            prompts = [self.ps1, self.ps2]
            prompt_patterns = [
                r'\r?\n?' + re.escape(prompts[0]),  # PS1 at start of line
                r'\r?\n?' + re.escape(prompts[1])   # PS2 at start of line
            ]
        
        try:
            self.process.sendline(command)
            idx = self.process.expect(prompt_patterns, timeout=timeout)

            # idx == 1 -> we matched PS2 -> syntax error / unbalanced quotes
            if idx == 1:
                self.process.sendcontrol("c")  # abort current line
                self.process.expect(prompt_patterns[0], timeout=5)
                return "Error: command appears incomplete (unbalanced quotes or parentheses)"

            output = self.process.before or ""
            
            # Post-process output through handler
            output = self.handler_manager.post_process_output(output, command)
            
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
        handler_info = self.handler_manager.get_active_handler_info()
        base_info = {
            'prompt': self.ps1,
            'has_active_handler': self.handler_manager.has_active_handler
        }
        # Merge handler info
        return {**base_info, **handler_info}
    
