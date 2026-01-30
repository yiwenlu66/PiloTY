"""Deprecated handler-manager API.

The current PiloTY implementation does not use per-program handlers. This module
exists to keep imports in older docs/tools from breaking.
"""


class HandlerManager:
    def __init__(self):
        self._handlers = []

    def register_handler(self, _handler):
        self._handlers.append(_handler)

