"""Base classes for interactive program handlers."""

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..core import ShellSession


@dataclass
class HandlerContext:
    """Base class for handler-specific context/state."""
    active: bool = False


class InteractiveHandler(ABC):
    """Abstract base class for interactive program handlers.
    
    Handlers encapsulate the logic for managing specific interactive programs
    (SSH, REPL, vim, etc.) within a PTY session. Each handler manages its own
    state and provides hooks for command processing.
    """
    
    def __init__(self):
        """Initialize handler with its context."""
        self.context = self._create_context()
    
    @abstractmethod
    def _create_context(self) -> HandlerContext:
        """Create handler-specific context object.
        
        Returns:
            HandlerContext subclass with handler-specific state
        """
        pass
    
    @abstractmethod
    def can_handle(self, command: str) -> bool:
        """Check if this handler should process the command.
        
        This is called for each command to determine if the handler
        should become active.
        
        Args:
            command: The command to check
            
        Returns:
            True if this handler should handle the command
        """
        pass
    
    @abstractmethod
    def activate(self, session: 'ShellSession', command: str) -> str:
        """Activate handler and process initial command.
        
        This is called when can_handle returns True and the handler
        becomes active. The handler should process the command and
        update its context.
        
        Args:
            session: The shell session
            command: The command that triggered activation
            
        Returns:
            Output from processing the command
        """
        pass
    
    @abstractmethod
    def deactivate(self, session: 'ShellSession') -> str:
        """Deactivate handler and clean up.
        
        This is called when the handler should stop being active
        (e.g., when exiting SSH or vim).
        
        Args:
            session: The shell session
            
        Returns:
            Output message from deactivation
        """
        pass
    
    def pre_command(self, command: str) -> Optional[str]:
        """Pre-process command if handler is active.
        
        This is called for each command when the handler is active.
        Return None to let the command execute normally, or return
        a string to override the command execution.
        
        Args:
            command: The command to pre-process
            
        Returns:
            None to use default execution, or string result to override
        """
        return None
    
    def post_output(self, output: str, command: str) -> str:
        """Post-process output if handler is active.
        
        This is called after command execution to allow the handler
        to transform the output.
        
        Args:
            output: The raw output from command execution
            command: The command that was executed
            
        Returns:
            Processed output
        """
        return output
    
    def get_prompt_patterns(self) -> Optional[list]:
        """Get custom prompt patterns when handler is active.
        
        Returns:
            List of regex patterns for prompts, or None to use defaults
        """
        return None
    
    @property
    def is_active(self) -> bool:
        """Check if handler is currently active."""
        return self.context.active
    
    def should_exit(self, command: str) -> bool:
        """Check if command should trigger handler exit.
        
        Args:
            command: The command to check
            
        Returns:
            True if handler should deactivate
        """
        return False