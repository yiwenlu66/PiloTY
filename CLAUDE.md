# PiloTY Development Guide

## Project Context

PiloTY is an MCP server providing terminal capabilities to AI agents. Architecture uses quiescence detection + MCP sampling for program-agnostic terminal interaction. See `ROADMAP.md` for current priorities.

## Key Files

- `src/piloty/` - Main source code
- `tests/` - Test suite
- `playground.py` - Interactive testing
- `ROADMAP.md` - Development priorities

## Development Workflow

1. Review `ROADMAP.md` for current phase and tasks
2. Search codebase for related implementations
3. Discuss approach with user before significant changes
4. Implement incrementally, test as you go
5. Update `ROADMAP.md` when tasks complete
6. Commit with clear message referencing roadmap item

## Principles

- Fail fast, surface errors early
- Consult existing code before writing new patterns
- Test edge cases and error conditions
- Communicate uncertainties before proceeding
