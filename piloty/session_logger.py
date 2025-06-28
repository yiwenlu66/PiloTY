"""File-based session logging for PTY sessions."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import random
import string


class SessionLogger:
    """Logs PTY session data to files for inspection and debugging."""
    
    def __init__(self, session_id: Optional[str] = None):
        """Initialize session logger.
        
        Args:
            session_id: Optional session ID. If not provided, generates one.
        """
        self.session_id = session_id or self._generate_session_id()
        self.base_dir = Path.home() / ".piloty"
        self.session_dir = self.base_dir / "sessions" / self.session_id
        self.active_dir = self.base_dir / "active"
        
        # File handles
        self._commands_file = None
        self._transcript_file = None
        
        # Buffering for transcript
        self._transcript_buffer = []
        self._last_flush = datetime.now()
        
        # Setup directories and files
        self._setup_directories()
        self._create_session_metadata()
        self._create_symlink()
        
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"{timestamp}-{suffix}"
        
    def _setup_directories(self):
        """Create necessary directories."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.active_dir.mkdir(parents=True, exist_ok=True)
        
    def _create_session_metadata(self):
        """Create initial session.json file."""
        metadata = {
            "session_id": self.session_id,
            "start_time": datetime.now().isoformat(),
            "pid": os.getpid(),
            "initial_cwd": os.getcwd(),
            "end_time": None
        }
        
        session_file = self.session_dir / "session.json"
        with open(session_file, 'w') as f:
            json.dump(metadata, f, indent=2)
            
    def _create_symlink(self):
        """Create symlink in active directory."""
        symlink_path = self.active_dir / self.session_id
        target = Path("..") / "sessions" / self.session_id
        
        # Remove if exists (shouldn't happen but be safe)
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
            
        symlink_path.symlink_to(target)
        
    def log_command(self, command: str):
        """Log a command to commands.log.
        
        Args:
            command: The command that was executed
        """
        timestamp = datetime.now().isoformat()
        commands_file = self.session_dir / "commands.log"
        
        # Append to commands log
        with open(commands_file, 'a') as f:
            f.write(f"{timestamp} $ {command}\n")
            
    def log_output(self, data: str):
        """Log output to transcript.log.
        
        Args:
            data: Raw output data from PTY
        """
        # Add to buffer
        self._transcript_buffer.append(data)
        
        # Flush if buffer is large or time has passed
        if (len(self._transcript_buffer) > 100 or 
            (datetime.now() - self._last_flush).seconds > 1):
            self._flush_transcript()
            
    def _flush_transcript(self):
        """Flush transcript buffer to file."""
        if not self._transcript_buffer:
            return
            
        transcript_file = self.session_dir / "transcript.log"
        with open(transcript_file, 'a') as f:
            f.write(''.join(self._transcript_buffer))
            
        self._transcript_buffer.clear()
        self._last_flush = datetime.now()
        
    def update_state(self, state: Dict[str, Any]):
        """Update state.json with current session state.
        
        Args:
            state: Dictionary containing current state
        """
        state_file = self.session_dir / "state.json"
        state['last_updated'] = datetime.now().isoformat()
        
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
            
    def close(self):
        """Clean up on session termination."""
        # Flush any remaining transcript
        self._flush_transcript()
        
        # Update session.json with end time
        session_file = self.session_dir / "session.json"
        with open(session_file, 'r') as f:
            metadata = json.load(f)
            
        metadata['end_time'] = datetime.now().isoformat()
        
        with open(session_file, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        # Remove symlink
        symlink_path = self.active_dir / self.session_id
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()