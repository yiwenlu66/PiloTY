"""Shared utilities for output processing and text manipulation."""

import re


def clean_output(text: str, command: str = None, is_ssh: bool = False, remote_ps1: str = None, remote_ps2: str = None) -> str:
    """
    Remove common terminal escape sequences and clean output.
    
    Args:
        text: Raw output text to clean
        command: Original command that produced the output (for echo removal)
        is_ssh: Whether this is SSH session output
        remote_ps1: Remote PS1 prompt (for SSH sessions)
        remote_ps2: Remote PS2 prompt (for SSH sessions)
    
    Returns:
        Cleaned output text
    """
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
    
    # Remove lines that are just prompts or empty (SSH-specific)
    if is_ssh and remote_ps1:
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip lines that look like standalone prompts
            stripped = line.strip()
            if stripped and not re.match(r'^[%$#>]\s*$', stripped):
                # Also skip lines that are just the prompt itself
                if stripped not in [remote_ps1.strip(), remote_ps2.strip() if remote_ps2 else '']:
                    # Skip the command echo if it appears at the start
                    if command and stripped == command.strip():
                        continue
                    cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
    
    return text


# Common terminal prompt patterns
PROMPT_PATTERNS = {
    'bash': r'\$ ',
    'zsh': r'% ',
    'fish': r'> ',
    'root': r'# ',
    'generic': r'[$#>%] ',
    'user_host': r'.*@.*[:#~].*[$#%>] '
}

# ANSI escape sequence patterns
ANSI_PATTERNS = {
    'color': r'\x1b\[[0-9;]*[mGKHF]',
    'bracketed_paste': r'\x1b\[\?2004[hl]',
    'cursor': r'\x1b\[[\d;]*[A-Za-z]',
    'other': r'\x1b[>=\[\]()][\d;]*[A-Za-z]?'
}