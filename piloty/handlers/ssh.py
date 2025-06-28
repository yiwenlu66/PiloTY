"""SSH connection handler for interactive SSH sessions."""

import logging
import re
import shlex
from typing import Optional
from dataclasses import dataclass
import pexpect

from .base import InteractiveHandler, HandlerContext
from ..utils import clean_output


@dataclass
class SSHContext(HandlerContext):
    """SSH-specific context."""
    host: Optional[str] = None
    remote_ps1: str = "REMOTE_MCP> "
    remote_ps2: str = "REMOTE_CONT> "
    prompt_set: bool = False


class SSHHandler(InteractiveHandler):
    """Handler for SSH connections.
    
    Manages interactive SSH sessions including connection setup,
    prompt management, and session cleanup.
    """
    
    def _create_context(self) -> SSHContext:
        """Create SSH-specific context."""
        return SSHContext()
    
    @property
    def ssh_context(self) -> SSHContext:
        """Type-safe access to SSH context."""
        return self.context  # type: ignore
    
    def can_handle(self, command: str) -> bool:
        """Detect interactive SSH commands."""
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
    
    def activate(self, session, command: str) -> str:
        """Handle SSH connection."""
        # Extract hostname first
        self.ssh_context.host = self._extract_ssh_host(command)
        
        # Send SSH command
        session.process.sendline(command)
        
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
        
        idx = session.process.expect(patterns, timeout=10)
        
        if idx == 0:  # Password
            session.process.sendcontrol("c")  # Cancel
            session.process.expect(session.ps1, timeout=5)
            return "Error: Password authentication not supported. Please use SSH keys."
        elif idx in [7, 8, 9]:  # Connection failures
            error_msg = session.process.before or "Connection failed"
            session.process.expect(session.ps1, timeout=5)
            return f"Error: SSH connection failed: {error_msg.strip()}"
        elif idx == 10:  # Timeout
            return "Error: SSH connection timed out"
        
        # Connected! Now set remote prompts adaptively
        self._setup_remote_prompts(session)
        
        # Activate handler
        self.context.active = True
        
        return f"Connected to {self.ssh_context.host}"
    
    def deactivate(self, session) -> str:
        """Handle SSH exit."""
        session.process.sendline("exit")
        # Wait for local prompt to return
        try:
            session.process.expect(session.ps1, timeout=5)
            host = self.ssh_context.host
            self.context.active = False
            self.ssh_context.host = None
            self.ssh_context.prompt_set = False
            return f"Disconnected from {host}"
        except pexpect.TIMEOUT:
            # Maybe connection was already closed
            self.context.active = False
            self.ssh_context.host = None
            self.ssh_context.prompt_set = False
            return "SSH session ended"
    
    def pre_command(self, command: str) -> Optional[str]:
        """Check for exit command."""
        if command.strip() == 'exit':
            # Handle exit through deactivate
            return None  # Let it execute normally, we'll catch it in should_exit
        return None
    
    def post_output(self, output: str, command: str) -> str:
        """Clean SSH output."""
        return clean_output(
            output, 
            command, 
            is_ssh=True,
            remote_ps1=self.ssh_context.remote_ps1,
            remote_ps2=self.ssh_context.remote_ps2
        )
    
    def get_prompt_patterns(self) -> Optional[list]:
        """Get SSH prompt patterns."""
        if not self.context.active:
            return None
            
        # Match prompts including zsh's % formatting and bracketed paste mode
        return [
            r'(?:\r\n%\s+\r\s+\r)?' + re.escape(self.ssh_context.remote_ps1) + r'(?:\s*\x1b\[\?2004h)?',
            r'(?:\r\n%\s+\r\s+\r)?' + re.escape(self.ssh_context.remote_ps2) + r'(?:\s*\x1b\[\?2004h)?'
        ]
    
    def should_exit(self, command: str) -> bool:
        """Check if command should exit SSH."""
        return self.is_active and command.strip() == 'exit'
    
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
    
    def _setup_remote_prompts(self, session) -> None:
        """Set up custom prompts on remote shell."""
        # Try different methods to set prompt based on shell type
        prompt_commands = [
            (f"PS1='{self.ssh_context.remote_ps1}'", f"PS2='{self.ssh_context.remote_ps2}'"),  # sh/bash without export
            (f"export PS1='{self.ssh_context.remote_ps1}'", f"export PS2='{self.ssh_context.remote_ps2}'"),  # bash/zsh with export
            (f"set prompt='{self.ssh_context.remote_ps1}'", None),  # csh/tcsh style (no PS2)
            (f"set PS1 '{self.ssh_context.remote_ps1}'", None),  # fish style
        ]
        
        for ps1_cmd, ps2_cmd in prompt_commands:
            session.process.sendline(ps1_cmd)
            try:
                # Try to match our custom prompt
                session.process.expect(self.ssh_context.remote_ps1, timeout=1)
                self.ssh_context.prompt_set = True
                # If PS1 worked and we have PS2 command, set it too
                if ps2_cmd:
                    session.process.sendline(ps2_cmd)
                    try:
                        session.process.expect(self.ssh_context.remote_ps1, timeout=1)
                    except:
                        pass  # PS2 is less critical
                break
            except pexpect.TIMEOUT:
                # This method didn't work, try next
                continue
        
        if not self.ssh_context.prompt_set:
            # Couldn't set custom prompt, we'll work with whatever the shell has
            logging.warning("Could not set custom prompt on remote shell")
        
        # Clear any remaining output in buffer and sync
        self._sync_session(session)
    
    def _sync_session(self, session) -> None:
        """Sync session after prompt setup."""
        if self.ssh_context.prompt_set:
            try:
                # Send a sync command and wait for it to complete
                session.process.sendline("echo SYNC_MARKER")
                # Wait for the marker
                session.process.expect("SYNC_MARKER", timeout=2)
                # Now wait for the prompt after the marker
                session.process.expect(self.ssh_context.remote_ps1, timeout=2)
                # Clear the buffer to ensure clean state
                session.process.buffer = ''
            except pexpect.TIMEOUT:
                logging.warning("Could not sync after prompt setup")
                # Try to clear buffer anyway
                try:
                    session.process.read_nonblocking(size=2000, timeout=0.2)
                    session.process.buffer = ''
                except:
                    pass
        else:
            # Try to sync with generic prompt
            try:
                session.process.sendline("echo ready")
                session.process.expect(r'ready', timeout=2)
                session.process.expect(r'[$#>%] ', timeout=2)
            except:
                pass