# PiloTY: Stateful PTY Control for AI Agents

## Philosophy

### Unix Design Principles

PiloTY embodies the Unix philosophy:

- **Do one thing well**: Terminal control only, no bundled features
- **Everything is a file**: PTY devices expose standard file descriptors
- **Text streams**: Standard I/O enables pipeline composition
- **Small and focused**: Single-purpose tool that composes with others

### CLI-First Architecture

- Built for headless server environments
- No GUI dependencies or desktop integration  
- Designed for automation and scripting
- Minimal resource footprint for container deployment

### Comparison with Bundled Approaches

This philosophy contrasts with all-in-one solutions like DesktopCommander:

| Aspect | DesktopCommander | PiloTY |
|--------|------------------|--------|
| Scope | Desktop automation suite | Terminal control only |
| Features | Screen capture, mouse control, file browser | PTY sessions |
| Target | Desktop GUI environments | Headless servers, CLI workflows |
| Dependencies | Heavy (GUI libraries) | Minimal (pexpect) |
| Resource usage | High | Low |

**Why this matters**: Developers working on remote servers need lightweight tools that integrate with existing workflows. PiloTY provides focused terminal control without the overhead of desktop automation features, making it ideal for SSH sessions, containers, and CI/CD pipelines.

## Problem: Stateless Command Execution

Current AI coding assistants execute commands in isolated contexts. Each command runs in a fresh shell environment, losing:

- Environment variables and working directory state
- Active SSH connections and authentication
- Running processes and job control
- Interactive program sessions

This stateless approach prevents AI agents from performing multi-step operations that developers routinely execute.

## Solution: PTY-Based Stateful Sessions

PiloTY provides persistent PTY (pseudo-terminal) sessions accessible via MCP. Key technical characteristics:

- **Bidirectional communication**: Master/slave PTY pair enables full duplex I/O
- **Terminal emulation**: Complete support for terminal control sequences, signals (SIGINT, SIGWINCH), and line discipline
- **Session persistence**: Process state, environment, and terminal context maintained across commands
- **Universal compatibility**: Works with any terminal-based application without modification

## Target Scenarios

### 1. Password and Confirmation Prompts

Programs using `getpass()` or readline-based prompts expect terminal input. PTY provides proper `/dev/tty` handling and echo control required for secure password entry.

### 2. SSH Session Management

Multi-command server operations require persistent SSH connections. PTY maintains the SSH process and its encrypted channel, preserving authentication state and remote environment.

### 3. Interactive Debugging (ipdb/pdb)

Python debuggers maintain execution context, breakpoints, and variable state. PTY enables stepping through code, inspecting frames, and modifying program state interactively.

### 4. Terminal Multiplexing (tmux)

Background process management and session persistence require PTY job control. PiloTY supports tmux's terminal multiplexing, enabling detached sessions and multi-pane workflows.

### 5. Pager Navigation (less/more)

Pagers require terminal size awareness, cursor positioning, and keyboard input handling. PTY provides `ioctl()` support for terminal dimensions and full control sequence compatibility.

### 6. Text Editing (vim)

Full-screen terminal applications need cursor addressing, alternate screen buffers, and raw input mode. PTY implements complete termios interface required for editor functionality.

## Technical Design

### Cross-Platform PTY Implementation

- Linux: Native PTY via `openpty()`/`forkpty()`
- macOS: BSD PTY compatibility layer
- Standard POSIX terminal interface for consistent behavior

## Implementation Approach

PiloTY uses `pexpect` for PTY management, providing:

- Robust process spawning with proper signal handling
- Pattern-based output synchronization
- Timeout and error handling for network operations
- Cross-platform PTY abstraction

The MCP interface exposes:

- `run()`: Execute commands in persistent session
- `poll_output()`: Read background process output with kernel buffer flushing
- `check_jobs()`: Monitor background process status
- Session lifecycle management

This architecture enables AI agents to operate terminals with the same capabilities as human developers, removing the artificial limitations of stateless command execution.
