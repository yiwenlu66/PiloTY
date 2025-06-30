# PiloTY Development Roadmap

## Overview

PiloTY's development follows a progressive enhancement approach: establish reliable fundamentals first, then build sophisticated interactive capabilities. This ensures that basic terminal operations work consistently before tackling the complexity of advanced interactive applications.

## Current Status ✅

PiloTY has achieved solid foundational capabilities:

- **Stateful terminal sessions** - Commands maintain context and working directory across interactions
- **SSH with public key authentication** - Seamless remote server access and command execution
- **Background process management** - Start, monitor, and control long-running tasks
- **Handler architecture** - Extensible system for adding support for new interactive programs
- **Comprehensive session logging** - Full session history with inspection tools for debugging
- **MCP integration** - Ready for use with AI agents through Claude Code, Claude Desktop, and other MCP clients

## Development Priorities

### Priority 1: Core Reliability 📋

Enhance the robustness and capabilities of existing terminal operations:

- **Password authentication** - Support for SSH password login, sudo commands, and other password-requiring tools
- **Interactive prompt handling** - Support for programs that request user input during operation (e.g., oh-my-zsh update prompts during SSH connection, apt asking for confirmation, etc.)
- **Enhanced error handling** - Better recovery from failed commands and connection issues
- **Multi-line command improvements** - Robust handling of complex scripts and here-documents
- **Output separation** - Clean stdout/stderr separation for better command result parsing
- **Playground UX improvements** - Add fzf-style hints for slash commands and arrow key navigation for command history

### Priority 2: REPL Support 🎯

Enable interactive data analysis and debugging workflows through REPL integration:

- **Python/IPython sessions** - Full support for interactive Python development and data analysis
- **Database clients** - Interactive sessions with mysql, psql, and other database command-line tools
- **Node.js REPL** - JavaScript development and debugging support
- **Interactive debugging tools** - Integration with pdb, ipdb, and similar debugging environments
- **REPL lifecycle management** - Seamless entry, interaction, and exit from various REPL environments

*This priority addresses the "vibe debugging" and interactive data analysis use cases that are central to modern development workflows.*

### Priority 3: Advanced Interactive Tools 📋

Support for complex full-screen terminal applications:

- **Text editors** - Basic vim and nano support for quick file editing
- **Terminal multiplexers** - Integration with tmux and screen for session management
- **System monitors** - Support for top, htop, and similar system monitoring tools
- **Pagers and viewers** - Handling of less, more, and other content viewing applications

## Success Metrics

### Core Reliability
- Commands execute consistently with proper exit codes and output capture
- SSH sessions establish reliably and handle both interactive and non-interactive use cases
- Background processes are managed cleanly without hanging or resource leaks

### REPL Integration  
- AI agents can naturally start, use, and exit Python/IPython sessions for data analysis
- Database queries can be executed interactively through command-line clients
- Multi-line code blocks and complex debugging scenarios work seamlessly

### Advanced Tools
- Basic text editing workflows function within AI agent conversations
- System monitoring and log viewing integrate naturally with diagnostic workflows
- Complex terminal applications degrade gracefully when full functionality isn't available

## Development Philosophy

**Start Simple, Build Smart**: Rather than attempting to solve all terminal interaction challenges at once, PiloTY focuses on incremental capability building. Each priority level builds upon the previous one:

1. **Reliable basics** ensure that standard command-line operations work consistently
2. **REPL support** enables the interactive development and analysis workflows that are increasingly central to modern software development
3. **Advanced tools** provide the final layer of sophisticated terminal application support

This approach ensures that users get immediate value from solid fundamentals while providing a clear path toward comprehensive terminal AI integration.

The emphasis on REPL support reflects the reality that interactive data analysis, debugging, and exploratory programming are among the most valuable AI-assisted workflows for developers and data scientists.