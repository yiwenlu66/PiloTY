#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pty_mcp.pty_mcp import ShellSession

def main():
    # Create a shell session
    session = ShellSession()
    
    print("PTY Test Environment")
    print("Type 'exit' to quit")
    print("-" * 40)
    
    try:
        while True:
            # Get command from user
            command = input("\n> ")
            
            if command.lower() in ['exit', 'quit']:
                break
            
            # Run command and show result
            print(f"\nRunning: {command}")
            result = session.run(command)
            print(f"Output:\n{result}")
            
    finally:
        session.terminate()
        print("\nSession terminated")

if __name__ == "__main__":
    main()