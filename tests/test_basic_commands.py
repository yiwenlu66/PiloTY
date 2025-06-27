#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pty_mcp.pty_mcp import ShellSession

# Test basic commands
test_commands = [
    "echo 'Hello World'",
    "pwd",
    "ls -la",
    "echo $?",  # Check exit code
    "false",    # Command that fails
    "echo $?",  # Should show 1
    "true",     # Command that succeeds
    "echo $?",  # Should show 0
    "echo 'Line 1'; echo 'Line 2'",  # Multiple commands
    "for i in {1..3}; do echo \"Number $i\"; done",  # Loop
]

session = ShellSession()
try:
    for cmd in test_commands:
        print(f"\n{'='*50}")
        print(f"Command: {cmd}")
        result = session.run(cmd)
        print(f"Result: {result}")
finally:
    session.terminate()