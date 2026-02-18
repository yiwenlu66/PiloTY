#!/usr/bin/env python3
"""
Session Viewer - Inspect PiloTY session logs and state.

This tool allows you to view and monitor PTY sessions that have been
logged under ~/.piloty/
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
import os


def get_piloty_dir():
    """Get the PiloTY directory path."""
    return Path.home() / ".piloty"


def _active_sessions():
    piloty_dir = get_piloty_dir()
    active_dir = piloty_dir / "active"
    if not active_dir.exists():
        return []

    out = []
    for server_dir in sorted(active_dir.iterdir()):
        if not server_dir.is_dir():
            continue
        for link in sorted(server_dir.iterdir()):
            if not link.is_symlink():
                continue
            out.append((server_dir.name, link.name, link, link.resolve()))
    return out


def _all_sessions():
    piloty_dir = get_piloty_dir()
    servers_dir = piloty_dir / "servers"
    if not servers_dir.exists():
        return []

    out = []
    for server_dir in sorted(servers_dir.iterdir()):
        sessions_dir = server_dir / "sessions"
        if not sessions_dir.exists():
            continue
        for session_dir in sorted(sessions_dir.iterdir()):
            if not session_dir.is_dir():
                continue
            out.append((server_dir.name, session_dir.name, session_dir))
    return out


def _resolve_session_ref(session_ref: str) -> tuple[str, Path] | None:
    piloty_dir = get_piloty_dir()

    if "/" in session_ref:
        server_id, session_id = session_ref.split("/", 1)
        active_link = piloty_dir / "active" / server_id / session_id
        if active_link.exists() and active_link.is_symlink():
            return (f"{server_id}/{session_id}", active_link.resolve())

        session_dir = piloty_dir / "servers" / server_id / "sessions" / session_id
        if session_dir.exists() and session_dir.is_dir():
            return (f"{server_id}/{session_id}", session_dir)

        print(f"Session '{server_id}/{session_id}' not found.")
        return None

    active_matches = [
        (server_id, sid, path)
        for (server_id, sid, _link, path) in _active_sessions()
        if sid == session_ref
    ]
    if len(active_matches) == 1:
        server_id, sid, path = active_matches[0]
        return (f"{server_id}/{sid}", path)
    if len(active_matches) > 1:
        matches = ", ".join(f"{server_id}/{sid}" for (server_id, sid, _p) in active_matches)
        print(f"Ambiguous session id '{session_ref}'. Matches: {matches}")
        return None

    all_matches = [
        (server_id, sid, path) for (server_id, sid, path) in _all_sessions() if sid == session_ref
    ]
    if len(all_matches) == 1:
        server_id, sid, path = all_matches[0]
        return (f"{server_id}/{sid}", path)
    if len(all_matches) > 1:
        matches = ", ".join(f"{server_id}/{sid}" for (server_id, sid, _p) in all_matches)
        print(f"Ambiguous session id '{session_ref}'. Matches: {matches}")
        return None

    print(f"Session '{session_ref}' not found.")
    return None


def list_sessions(show_all=False):
    """List active or all sessions."""
    if show_all:
        sessions = _all_sessions()
        if not sessions:
            print("No sessions found.")
            return
        print(f"\nAll sessions ({len(sessions)} total):")
    else:
        sessions = _active_sessions()
        if not sessions:
            print("No active sessions found.")
            return
        print(f"\nActive sessions ({len(sessions)} total):")

    if show_all:
        for server_id, session_id, actual_path in sessions:
            display = f"{server_id}/{session_id}"
            session_path = actual_path
            _print_session_summary(display, session_path, show_all=True)
    else:
        for server_id, session_id, _link, actual_path in sessions:
            display = f"{server_id}/{session_id}"
            session_path = actual_path
            _print_session_summary(display, session_path, show_all=False)


def _print_session_summary(display: str, session_path: Path, show_all: bool):
        # Read session metadata
        session_file = session_path / "session.json"
        if session_file.exists():
            with open(session_file) as f:
                metadata = json.load(f)
                
            start_time = datetime.fromisoformat(metadata['start_time'])
            pid = metadata['pid']
            
            # Check if process is still running
            if not show_all:
                try:
                    os.kill(pid, 0)  # Check if process exists
                    status = "running"
                except ProcessLookupError:
                    status = "dead"
            else:
                status = "ended" if metadata.get('end_time') else "unknown"
                
            print(
                f"  {display} - Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')} - PID: {pid} - Status: {status}"
            )
        else:
            print(f"  {display} - (no metadata)")


def show_session_info(session_id):
    """Show detailed information about a session."""
    resolved = _resolve_session_ref(session_id)
    if resolved is None:
        return
    display, session_path = resolved

    print(f"\nSession: {display}")
    print("=" * 50)
    
    # Show metadata
    session_file = session_path / "session.json"
    if session_file.exists():
        with open(session_file) as f:
            metadata = json.load(f)
        
        print("\nMetadata:")
        print(f"  Start time: {metadata['start_time']}")
        print(f"  End time: {metadata.get('end_time', 'Still active')}")
        print(f"  PID: {metadata['pid']}")
        print(f"  Initial CWD: {metadata['initial_cwd']}")
    
    # Show current state
    state_file = session_path / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            
        print("\nCurrent State:")
        print(f"  VT100 OK: {state.get('vt100_ok', 'unknown')}")
        if state.get("vt100_error"):
            print(f"  VT100 error: {state['vt100_error']}")
        print(f"  Transcript: {state.get('transcript', 'unknown')}")
            
    # Show files
    print("\nLog Files:")
    for log_file in ['commands.log', 'transcript.log', 'interaction.log']:
        file_path = session_path / log_file
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"  {log_file}: {size:,} bytes")


def show_commands(session_id, last_n=None):
    """Show commands from a session."""
    resolved = _resolve_session_ref(session_id)
    if resolved is None:
        return
    display, session_path = resolved

    commands_file = session_path / "commands.log"
    if not commands_file.exists():
        print("No commands log found.")
        return
        
    with open(commands_file) as f:
        lines = f.readlines()
        
    if last_n:
        lines = lines[-last_n:]
        
    print(f"\nCommands from session {display}:")
    print("-" * 50)
    for line in lines:
        print(line.rstrip())


def show_interactions(session_id, last_n=None):
    """Show formatted interactions from a session."""
    resolved = _resolve_session_ref(session_id)
    if resolved is None:
        return
    display, session_path = resolved

    interaction_file = session_path / "interaction.log"
    if not interaction_file.exists():
        print("No interaction log found.")
        return
        
    with open(interaction_file) as f:
        content = f.read()
        
    if last_n:
        # Split by timestamp sections and get last N
        sections = content.split('\n[')[1:]  # Skip first empty split
        if sections:
            sections = sections[-last_n:]
            content = '\n[' + '\n['.join(sections)
        
    print(f"\nInteractions from session {display}:")
    print("-" * 50)
    print(content)


def tail_transcript(session_id, follow=False):
    """Tail the transcript log."""
    resolved = _resolve_session_ref(session_id)
    if resolved is None:
        return
    _display, session_path = resolved

    transcript_file = session_path / "transcript.log"
    if not transcript_file.exists():
        print("No transcript log found.")
        return
        
    # Use system tail command for simplicity
    import subprocess
    cmd = ["tail"]
    if follow:
        cmd.append("-f")
    else:
        cmd.extend(["-n", "50"])
    cmd.append(str(transcript_file))
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


def cleanup_stale_sessions():
    """Remove symlinks for dead sessions."""
    piloty_dir = get_piloty_dir()
    active_dir = piloty_dir / "active"
    
    if not active_dir.exists():
        print("No active directory found.")
        return
        
    removed = 0
    for server_dir in active_dir.iterdir():
        if not server_dir.is_dir():
            continue
        for symlink in server_dir.iterdir():
            if not symlink.is_symlink():
                continue
            target = symlink.resolve()
            
            # Check if session metadata exists
            session_file = target / "session.json"
            if session_file.exists():
                with open(session_file) as f:
                    metadata = json.load(f)
                    
                pid = metadata['pid']
                
                # Check if process is running
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    # Process is dead, remove symlink
                    print(f"Removing stale session: {server_dir.name}/{symlink.name} (PID {pid} not found)")
                    symlink.unlink()
                    removed += 1
            else:
                # No metadata, remove symlink
                print(f"Removing invalid session: {server_dir.name}/{symlink.name} (no metadata)")
                symlink.unlink()
                removed += 1
                
    print(f"\nRemoved {removed} stale session(s).")


def main():
    parser = argparse.ArgumentParser(description="Inspect PiloTY session logs")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List sessions')
    list_parser.add_argument('-a', '--all', action='store_true', help='Show all sessions, not just active')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show session information')
    info_parser.add_argument('session_id', help='Session ID')
    
    # Commands command
    commands_parser = subparsers.add_parser('commands', help='Show commands from session')
    commands_parser.add_argument('session_id', help='Session ID')
    commands_parser.add_argument('-n', '--last', type=int, help='Show only last N commands')
    
    # Interactions command
    interactions_parser = subparsers.add_parser('interactions', help='Show formatted command/output interactions')
    interactions_parser.add_argument('session_id', help='Session ID')
    interactions_parser.add_argument('-n', '--last', type=int, help='Show only last N interactions')
    
    # Tail command
    tail_parser = subparsers.add_parser('tail', help='Tail transcript log')
    tail_parser.add_argument('session_id', help='Session ID')
    tail_parser.add_argument('-f', '--follow', action='store_true', help='Follow log in real-time')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Remove stale session symlinks')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
        
    if args.command == 'list':
        list_sessions(show_all=args.all)
    elif args.command == 'info':
        show_session_info(args.session_id)
    elif args.command == 'commands':
        show_commands(args.session_id, last_n=args.last)
    elif args.command == 'interactions':
        show_interactions(args.session_id, last_n=args.last)
    elif args.command == 'tail':
        tail_transcript(args.session_id, follow=args.follow)
    elif args.command == 'cleanup':
        cleanup_stale_sessions()


if __name__ == "__main__":
    main()
