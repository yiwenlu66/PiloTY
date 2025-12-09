# PiloTY Roadmap

## Architecture

PTY has two states: **busy** (producing output) or **quiescent** (silent for N ms).

State interpretation delegated to MCP client LLM via sampling. No per-program handlers or prompt patterns. TUI programs rendered via VT100 emulator before LLM interpretation.

## Done

- Stateful terminal sessions
- SSH with public key authentication
- Background process management
- Session logging
- MCP integration

## Phase 0: Architecture Rewrite

**P0-1: Quiescence detection** - Replace `pexpect.expect()` prompt matching with output silence timer. Return "busy" or "quiescent".

**P0-2: MCP sampling integration** - Use `sampling/createMessage` to ask client LLM "is terminal waiting for input?" Short context, separate from main agent conversation.

**P0-3: Simplified API** - `type(text, timeout)`, `read()`, `transcript()`. Remove `run()` abstraction.

**P0-4: VT100 emulation** - Integrate `pyte` for escape sequence parsing. Send rendered screen to sampling, not raw bytes.

## Phase 1: Core Capabilities

**P1-1: Password input** - LLM recognizes prompts. Secure injection without logging.

**P1-2: Interactive confirmations** - LLM recognizes [Y/n] prompts. Agent decides response.

**P1-3: Output management** - Head+tail truncation. Transcript file for grep.

## Phase 2: Enhanced Interaction

**P2-1: REPL sessions** - Python, IPython, Node, database clients work automatically via LLM recognition.

**P2-2: Error recovery** - LLM detects errors, stack traces. Timeout recovery for hung programs.

## Phase 3: TUI Programs

**P3-1: Text editors** - vim, nano via VT100 rendering. LLM interprets mode.

**P3-2: Multiplexers** - tmux, screen with pane detection.

**P3-3: Viewers** - less, top, htop navigation.

## Open Questions

- Sampling latency/cost acceptable?
- Fixed 80x24 or detect screen size?

## Notes

**Playground without LLM**: Quiescence detection works without sampling. Playground returns output after silence timeout; human interprets state visually. Human acts as the "sampling LLM" during manual testing.
