# PiloTY Development SOP for AI Assistants

## Project-Specific Context

PiloTY is a Model Context Protocol (MCP) server that provides terminal capabilities to AI agents. The codebase uses Python with async patterns and a handler-based architecture for managing different interactive terminal programs.

## Development Workflow SOP

### Task Selection and Execution Process

When working on PiloTY development tasks, follow this systematic approach:

#### 1. Task Selection
- Review @todo/ROADMAP.md to understand current priorities
- Select an appropriate task based on:
  - Priority level (P1 > P2 > P3)
  - Dependencies (some tasks may require others to be completed first)
  - Current project needs discussed with the user

#### 2. PRD Review and Context Gathering
- Read the corresponding PRD in `todo/` (e.g., `P1-01-password-auth.md`)
- Gather relevant context by:
  - Searching the codebase for related implementations
  - Understanding existing patterns and abstractions
  - Reviewing handler architecture in `src/handlers/`
  - Checking test coverage in `tests/`

#### 3. Deep Thinking and Planning
- Use the sequential thinking tool or similar to:
  - Break down the implementation into steps
  - Identify potential challenges and edge cases
  - Consider integration with existing components
  - Plan testing approach

#### 4. Discussion and PRD Refinement
- Present your understanding and implementation plan to the user
- Discuss any ambiguities or alternative approaches
- Update the PRD if new requirements or constraints are identified
- Get user confirmation before proceeding with implementation

#### 5. Implementation
- Follow the fail-fast philosophy
- Use existing abstractions and patterns
- Implement in small, testable increments
- Maintain clean separation of concerns
- Add appropriate error handling for external failures only

#### 6. Testing and Validation
- Write tests for new functionality
- Ensure existing tests still pass
- Test edge cases and error conditions
- Validate with manual testing in the playground

#### 7. Documentation and Cleanup
- Update relevant documentation
- Add docstrings to new functions/classes
- Clean up any debug code or TODOs
- Ensure code follows project style

#### 8. Roadmap Update
- Mark the PRD as completed in todo/ROADMAP.md
- Add completion date and any relevant notes
- Update status indicators (✅ for completed)
- Note any follow-up tasks identified during implementation

#### 9. Commit Changes
- Create a clear, descriptive commit message
- Include reference to the PRD (e.g., "Implement P1-01: Password authentication")
- Ensure all changes are staged
- Commit with appropriate scope


### Important Files and Directories

- `src/piloty/` - Main source code
- `src/handlers/` - Interactive program handlers
- `tests/` - Test suite
- `todo/` - Roadmap and PRDs
- `playground.py` - Interactive testing environment
- `pyproject.toml` - Project configuration

### Notes for AI Assistants

1. **Always consult existing code** before implementing new features
2. **Follow established patterns** rather than creating new ones
3. **Test incrementally** to catch issues early
4. **Communicate uncertainties** to the user before proceeding
5. **Update documentation** as part of the implementation
6. **Use the playground** for manual validation
7. **Consider edge cases** and error scenarios
8. **Maintain backwards compatibility** when possible

