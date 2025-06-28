"""SSH connection handling for interactive SSH sessions."""

import logging
import re
import shlex
from typing import Optional, Tuple, Dict, Any
import pexpect

from ..utils import clean_output


def detect_ssh_command(command: str) -> bool:
    """
    Detect if command is an interactive SSH connection.
    
    Args:
        command: Command string to check
        
    Returns:
        True if command is interactive SSH, False otherwise
    """
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


def extract_ssh_host(ssh_command: str) -> str:
    """
    Extract hostname from SSH command.
    
    Args:
        ssh_command: SSH command string
        
    Returns:
        Hostname or "unknown" if cannot parse
    """
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


def handle_ssh_connection(session, command: str, timeout: int = 30) -> Tuple[str, Dict[str, Any]]:
    """
    Handle interactive SSH connection.
    
    Args:
        session: ShellSession instance
        command: SSH command to execute
        timeout: Connection timeout in seconds
        
    Returns:
        Tuple of (output_message, state_updates)
        state_updates is a dict with keys: is_ssh, ssh_host, remote_ps1, remote_ps2
    """
    # Default state updates
    state = {
        'is_ssh': False,
        'ssh_host': None,
        'remote_ps1': "REMOTE_MCP> ",
        'remote_ps2': "REMOTE_CONT> "
    }
    
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
        return "Error: Password authentication not supported. Please use SSH keys.", state
    elif idx in [7, 8, 9]:  # Connection failures
        error_msg = session.process.before or "Connection failed"
        session.process.expect(session.ps1, timeout=5)
        return f"Error: SSH connection failed: {error_msg.strip()}", state
    elif idx == 10:  # Timeout
        return "Error: SSH connection timed out", state
    
    # Connected! Now set remote prompts adaptively
    # Try different methods to set prompt based on shell type
    prompt_commands = [
        (f"PS1='{state['remote_ps1']}'", f"PS2='{state['remote_ps2']}'"),  # sh/bash without export
        (f"export PS1='{state['remote_ps1']}'", f"export PS2='{state['remote_ps2']}'"),  # bash/zsh with export
        (f"set prompt='{state['remote_ps1']}'", None),  # csh/tcsh style (no PS2)
        (f"set PS1 '{state['remote_ps1']}'", None),  # fish style
    ]
    
    prompt_set = False
    for ps1_cmd, ps2_cmd in prompt_commands:
        session.process.sendline(ps1_cmd)
        try:
            # Try to match our custom prompt
            session.process.expect(state['remote_ps1'], timeout=1)
            prompt_set = True
            # If PS1 worked and we have PS2 command, set it too
            if ps2_cmd:
                session.process.sendline(ps2_cmd)
                try:
                    session.process.expect(state['remote_ps1'], timeout=1)
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
            session.process.sendline("echo SYNC_MARKER")
            # Wait for the marker
            session.process.expect("SYNC_MARKER", timeout=2)
            # Now wait for the prompt after the marker
            session.process.expect(state['remote_ps1'], timeout=2)
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
    
    # Update state
    state['is_ssh'] = True
    state['ssh_host'] = extract_ssh_host(command)
    
    return f"Connected to {state['ssh_host']}", state


def handle_ssh_exit(session, command: str) -> Tuple[str, Dict[str, Any]]:
    """
    Handle exit from SSH session.
    
    Args:
        session: ShellSession instance  
        command: Exit command
        
    Returns:
        Tuple of (output_message, state_updates)
    """
    session.process.sendline(command)
    # Wait for local prompt to return
    try:
        session.process.expect(session.ps1, timeout=5)
        host = session.ssh_host if hasattr(session, 'ssh_host') else 'remote'
        return f"Disconnected from {host}", {
            'is_ssh': False,
            'ssh_host': None
        }
    except pexpect.TIMEOUT:
        # Maybe connection was already closed
        return "SSH session ended", {
            'is_ssh': False, 
            'ssh_host': None
        }


def get_ssh_prompt_patterns(remote_ps1: str, remote_ps2: str) -> list:
    """
    Get regex patterns for matching SSH prompts.
    
    Args:
        remote_ps1: Primary remote prompt
        remote_ps2: Secondary remote prompt
        
    Returns:
        List of compiled regex patterns
    """
    # Match prompts including zsh's % formatting and bracketed paste mode
    # The pattern needs to match: \r\n%[spaces]\r \r\rPROMPT[optional bracketed paste]
    return [
        r'(?:\r\n%\s+\r\s+\r)?' + re.escape(remote_ps1) + r'(?:\s*\x1b\[\?2004h)?',  # PS1 with zsh formatting
        r'(?:\r\n%\s+\r\s+\r)?' + re.escape(remote_ps2) + r'(?:\s*\x1b\[\?2004h)?'   # PS2 with zsh formatting
    ]