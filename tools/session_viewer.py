#!/usr/bin/env python3
"""
Session Viewer - Inspect PiloTY session logs and state.

This tool allows you to view and monitor PTY sessions that have been
logged to ~/.piloty/
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


def list_sessions(show_all=False):
    """List active or all sessions."""
    piloty_dir = get_piloty_dir()
    
    if show_all:
        sessions_dir = piloty_dir / "sessions"
        if not sessions_dir.exists():
            print("No sessions found.")
            return
            
        sessions = list(sessions_dir.iterdir())
        print(f"\nAll sessions ({len(sessions)} total):")
    else:
        active_dir = piloty_dir / "active"
        if not active_dir.exists():
            print("No active sessions found.")
            return
            
        sessions = list(active_dir.iterdir())
        print(f"\nActive sessions ({len(sessions)} total):")
    
    if not sessions:
        print("  (none)")
        return
        
    # Sort by name (which includes timestamp)
    sessions.sort()
    
    for session_path in sessions:
        # For active sessions, resolve symlink to get actual path
        if session_path.is_symlink():
            actual_path = session_path.resolve()
        else:
            actual_path = session_path
            
        # Read session metadata
        session_file = actual_path / "session.json"
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
                
            print(f"  {session_path.name} - Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')} - PID: {pid} - Status: {status}")
        else:
            print(f"  {session_path.name} - (no metadata)")


def show_session_info(session_id):
    """Show detailed information about a session."""
    piloty_dir = get_piloty_dir()
    
    # Try active first, then all sessions
    session_path = piloty_dir / "active" / session_id
    if session_path.exists() and session_path.is_symlink():
        session_path = session_path.resolve()
    else:
        session_path = piloty_dir / "sessions" / session_id
        
    if not session_path.exists():
        print(f"Session '{session_id}' not found.")
        return
        
    print(f"\nSession: {session_id}")
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
        print(f"  Directory: {state.get('current_directory', 'unknown')}")
        print(f"  Active handler: {state.get('active_handler', 'none')}")
        if state.get('handler_context'):
            print(f"  Handler context: {json.dumps(state['handler_context'], indent=4)}")
        if state.get('background_jobs'):
            print(f"  Background jobs: {len(state['background_jobs'])}")
            
    # Show files
    print("\nLog Files:")
    for log_file in ['commands.log', 'transcript.log']:
        file_path = session_path / log_file
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"  {log_file}: {size:,} bytes")


def show_commands(session_id, last_n=None):
    """Show commands from a session."""
    piloty_dir = get_piloty_dir()
    
    # Find session
    session_path = piloty_dir / "active" / session_id
    if session_path.exists() and session_path.is_symlink():
        session_path = session_path.resolve()
    else:
        session_path = piloty_dir / "sessions" / session_id
        
    if not session_path.exists():
        print(f"Session '{session_id}' not found.")
        return
        
    commands_file = session_path / "commands.log"
    if not commands_file.exists():
        print("No commands log found.")
        return
        
    with open(commands_file) as f:
        lines = f.readlines()
        
    if last_n:
        lines = lines[-last_n:]
        
    print(f"\nCommands from session {session_id}:")
    print("-" * 50)
    for line in lines:
        print(line.rstrip())


def tail_transcript(session_id, follow=False):
    """Tail the transcript log."""
    piloty_dir = get_piloty_dir()
    
    # Find session
    session_path = piloty_dir / "active" / session_id
    if session_path.exists() and session_path.is_symlink():
        session_path = session_path.resolve()
    else:
        session_path = piloty_dir / "sessions" / session_id
        
    if not session_path.exists():
        print(f"Session '{session_id}' not found.")
        return
        
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
    for symlink in active_dir.iterdir():
        if symlink.is_symlink():
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
                    print(f"Removing stale session: {symlink.name} (PID {pid} not found)")
                    symlink.unlink()
                    removed += 1
            else:
                # No metadata, remove symlink
                print(f"Removing invalid session: {symlink.name} (no metadata)")
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
    elif args.command == 'tail':
        tail_transcript(args.session_id, follow=args.follow)
    elif args.command == 'cleanup':
        cleanup_stale_sessions()


if __name__ == "__main__":
    main()