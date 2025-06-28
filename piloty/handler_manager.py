"""Handler manager for coordinating interactive program handlers."""

import logging
from typing import List, Optional, Tuple, Type

from .handlers.base import InteractiveHandler


class HandlerManager:
    """Manages handlers for a shell session.
    
    The HandlerManager maintains a registry of available handlers and
    coordinates their activation/deactivation based on commands.
    """
    
    def __init__(self):
        """Initialize the handler manager."""
        self.handlers: List[InteractiveHandler] = []
        self.active_handler: Optional[InteractiveHandler] = None
        
    def register_handler(self, handler_class: Type[InteractiveHandler]) -> None:
        """Register a handler class.
        
        Args:
            handler_class: The handler class to register
        """
        handler = handler_class()
        self.handlers.append(handler)
        logging.info(f"Registered handler: {handler_class.__name__}")
        
    def process_command(self, session, command: str) -> Tuple[str, bool]:
        """Process a command through the handler system.
        
        Args:
            session: The shell session
            command: The command to process
            
        Returns:
            Tuple of (output, handled) where handled indicates if a handler processed it
        """
        # First check if active handler wants to exit
        if self.active_handler and self.active_handler.should_exit(command):
            output = self.active_handler.deactivate(session)
            self.active_handler = None
            return output, True
            
        # Let active handler pre-process
        if self.active_handler:
            pre_result = self.active_handler.pre_command(command)
            if pre_result is not None:
                return pre_result, True
                
        # Check if any handler wants to activate
        if not self.active_handler:
            for handler in self.handlers:
                if handler.can_handle(command):
                    output = handler.activate(session, command)
                    self.active_handler = handler
                    return output, True
                    
        # No handler claimed the command
        return "", False
        
    def get_prompt_patterns(self) -> Optional[list]:
        """Get prompt patterns from active handler.
        
        Returns:
            Prompt patterns if active handler provides them, None otherwise
        """
        if self.active_handler:
            return self.active_handler.get_prompt_patterns()
        return None
        
    def post_process_output(self, output: str, command: str) -> str:
        """Post-process output through active handler.
        
        Args:
            output: Raw command output
            command: The command that was executed
            
        Returns:
            Processed output
        """
        if self.active_handler:
            return self.active_handler.post_output(output, command)
        return output
        
    @property
    def has_active_handler(self) -> bool:
        """Check if there's an active handler."""
        return self.active_handler is not None
        
    def get_active_handler_info(self) -> dict:
        """Get information about the active handler.
        
        Returns:
            Dictionary with handler information
        """
        if self.active_handler:
            return {
                'active': True,
                'handler_type': type(self.active_handler).__name__,
                'context': vars(self.active_handler.context)
            }
        return {
            'active': False,
            'handler_type': None,
            'context': None
        }