#!/usr/bin/env python3
"""
PTY Playground - Interactive development tool for PiloTY.

Uses quiescence-based PTY with heuristic state detection.
Human acts as the "sampling LLM" for complex state interpretation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from piloty.core import PTY
from piloty.mcp_server import detect_state_heuristic


def show_help():
    """Show available commands."""
    print("""
Commands:
  /help          - Show this help
  /exit, /quit   - Exit playground
	  /get_screen    - Get current screen content
	  /state         - Detect terminal state (heuristic)
	  /transcript    - Show transcript file path
	  /poll_output [timeout] - Wait up to timeout for new output (no input)
	  /check_jobs    - Run 'jobs -l' in session
	  /ctrl <key>    - Send control character (c, d, z, l, [)
	  /status        - Show PTY status

Input:
  Regular text (without /) is sent as a command with newline.
  Use /raw <text> to send without newline.
  Use /ctrl c to send Ctrl+C.
""")


def send_control(pty, key):
    """Send control character."""
    key = key.lower()
    if key == "[" or key == "escape" or key == "esc":
        char = "\x1b"
    elif len(key) == 1 and key.isalpha():
        char = chr(ord(key) - ord("a") + 1)
    else:
        print(f"Unknown control key: {key}")
        return

    result = pty.type(char, timeout=2.0, quiescence_ms=300)
    print(f"Status: {result['status']}")
    snap = pty.screen_snapshot()
    screen = snap["screen"]
    state, reason = detect_state_heuristic(screen, cursor_x=snap.get("cursor_x"))
    print(f"State: {state} ({reason})")
    print(f"Screen:\n{screen}")


def main():
    pty = PTY(session_id="playground")

    print("PTY Playground - Quiescence-based Terminal")
    print("=" * 50)
    print("Type /help for commands or /exit to quit")
    print(f"Transcript: {pty.transcript()}")
    print("-" * 50)

    # Show initial screen
    snap = pty.screen_snapshot()
    screen = snap["screen"]
    state, reason = detect_state_heuristic(screen, cursor_x=snap.get("cursor_x"))
    print(f"\nInitial state: {state} ({reason})")
    print(f"Screen:\n{screen}")

    try:
        while True:
            try:
                command = input("\n> ")
            except EOFError:
                break

            if not command:
                continue

            # Slash commands
            if command.startswith("/"):
                parts = command.split(maxsplit=1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd in ["/exit", "/quit"]:
                    break

                elif cmd == "/help":
                    show_help()

                elif cmd == "/get_screen":
                    snap = pty.screen_snapshot()
                    print(f"\nScreen:\n{snap['screen']}")

                elif cmd == "/state":
                    snap = pty.screen_snapshot()
                    screen = snap["screen"]
                    state, reason = detect_state_heuristic(screen, cursor_x=snap.get("cursor_x"))
                    print(f"\nState: {state}")
                    print(f"Reason: {reason}")

                elif cmd == "/transcript":
                    print(f"\nTranscript: {pty.transcript()}")

                elif cmd == "/poll_output":
                    t = 0.1
                    if args:
                        try:
                            t = float(args.strip())
                        except ValueError:
                            print("Usage: /poll_output [timeout]")
                            continue
                    result = pty.poll_output(timeout=t, quiescence_ms=100)
                    print(f"\nStatus: {result['status']}")
                    print(f"Output:\n{result['output']}")

                elif cmd == "/check_jobs":
                    result = pty.type("jobs -l\n", timeout=2.0, quiescence_ms=300)
                    print(f"\nStatus: {result['status']}")
                    print(f"Output:\n{result['output']}")

                elif cmd == "/ctrl":
                    if args:
                        send_control(pty, args)
                    else:
                        print("Usage: /ctrl <key>")

                elif cmd == "/status":
                    print(f"\nAlive: {pty.alive}")
                    print(f"Transcript: {pty.transcript()}")
                    snap = pty.screen_snapshot()
                    screen = snap["screen"]
                    state, reason = detect_state_heuristic(screen, cursor_x=snap.get("cursor_x"))
                    print(f"State: {state} ({reason})")

                elif cmd == "/raw":
                    if args:
                        result = pty.type(args, timeout=30.0, quiescence_ms=500)
                        print(f"Status: {result['status']}")
                        snap = pty.screen_snapshot()
                        screen = snap["screen"]
                        state, reason = detect_state_heuristic(screen, cursor_x=snap.get("cursor_x"))
                        print(f"State: {state} ({reason})")
                        print(f"Output:\n{result['output']}")
                    else:
                        print("Usage: /raw <text>")

                else:
                    print(f"Unknown command: {cmd}")
                    print("Type /help for available commands")

                continue

            # Regular command - send with newline
            print(f"\nSending: {repr(command)}")
            result = pty.type(command + "\n", timeout=30.0, quiescence_ms=500)
            print(f"Status: {result['status']}")

            snap = pty.screen_snapshot()
            screen = snap["screen"]
            state, reason = detect_state_heuristic(screen, cursor_x=snap.get("cursor_x"))
            print(f"State: {state} ({reason})")
            print(f"Output:\n{result['output']}")

    except KeyboardInterrupt:
        print("\n\nInterrupted")
    finally:
        pty.terminate()
        print("\nSession terminated")


if __name__ == "__main__":
    main()
