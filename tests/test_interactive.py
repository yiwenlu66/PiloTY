#!/usr/bin/env python3
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from piloty.piloty import ShellSession

def show_help():
    """Show available slash commands."""
    print("\nAvailable slash commands:")
    print("  /help                    - Show this help message")
    print("  /exit, /quit             - Exit the test environment")
    print("  /poll_output [timeout] [flush] - Poll for output (timeout: 0.1s, flush: true)")
    print("  /check_jobs              - Check status of background jobs")
    print("  /session_info            - Get current session information")
    print("\nRegular commands (not starting with /) are sent to the PTY.")
    print("Type 'exit' without slash to send it to PTY (e.g., to exit SSH).\n")

def format_result(result):
    """Format API result for display."""
    if isinstance(result, (dict, list)):
        return json.dumps(result, indent=2)
    return str(result)

def handle_slash_command(session, command):
    """Handle slash commands that call API methods."""
    parts = command.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    
    try:
        if cmd in ['/exit', '/quit']:
            return None  # Signal to exit
            
        elif cmd == '/help':
            show_help()
            return True
            
        elif cmd == '/poll_output':
            # Parse arguments: timeout and flush
            parts = args.split() if args else []
            timeout = float(parts[0]) if len(parts) > 0 else 0.1
            flush = parts[1].lower() != 'false' if len(parts) > 1 else True
            
            result = session.poll_output(timeout=timeout, flush=flush)
            print(f"\nAPI Result (poll_output, timeout={timeout}, flush={flush}):")
            if result:
                print(result)
            else:
                print("(no output)")
            return True
            
        elif cmd == '/check_jobs':
            result = session.check_jobs()
            print(f"\nAPI Result (check_jobs):")
            if result:
                print(format_result(result))
            else:
                print("No background jobs")
            return True
            
        elif cmd == '/session_info':
            result = session.get_session_info()
            print(f"\nAPI Result (session_info):")
            print(format_result(result))
            return True
            
        else:
            print(f"Unknown slash command: {cmd}")
            print("Type /help for available commands")
            return True
            
    except Exception as e:
        print(f"Error executing {cmd}: {e}")
        return True

def main():
    # Create a shell session
    session = ShellSession()
    
    print("PTY Test Environment")
    print("Type /help for available commands or /exit to quit")
    print("-" * 40)
    
    try:
        while True:
            # Get command from user
            command = input("\n> ")
            
            if not command:
                continue
            
            # Check if it's a slash command
            if command.startswith('/'):
                result = handle_slash_command(session, command)
                if result is None:  # Exit signal
                    break
                continue
            
            # Regular command - send to PTY
            print(f"\nRunning: {command}")
            result = session.run(command)
            print(f"Output:\n{result}")
            
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except EOFError:
        print("\n\nEOF received")
    finally:
        session.terminate()
        print("\nSession terminated")

if __name__ == "__main__":
    main()