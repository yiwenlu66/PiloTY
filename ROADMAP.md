# PTY-MCP Development Roadmap

## Overview
This document outlines the technical development plan for improving the PTY-MCP server with a focus on practical priorities: first making bash commands work reliably, then supporting line-based interactive programs, and finally full-screen interactive applications.

## Priority Levels

### Priority 1: Reliable Bash Command Execution
Make standard bash commands work with accurate stdout/stderr capture, including:
- Simple commands: `ls`, `pwd`, `echo`, `cat`
- Piped commands: `ls | grep pattern`
- Background processes: `sleep 10 &`
- SSH sessions: `ssh user@host command`
- Multi-line commands and scripts
- Proper exit code capture

### Priority 2: Line-Based Interactive Programs
Support programs that operate on a line-by-line basis:
- Python REPL, IPython
- Database clients: `mysql`, `psql`
- Simple prompts: `read -p "prompt"`, confirmation dialogs
- Git interactive commands

### Priority 3: Full Interactive Programs
Support full-screen terminal applications:
- Editors: `vim`, `nano`
- Pagers: `less`, `more`
- System monitors: `top`, `htop`
- Terminal multiplexers: `screen`, `tmux`

## Phase 1: Foundation - Reliable Bash Execution

### 1.1 Fix Current Issues

#### Problem: Prompt Detection Reliability
Current implementation uses custom prompts but doesn't handle all cases well.

**Solution**: Enhanced prompt management with command markers
```python
class BashSession:
    def __init__(self):
        self.prompt = "PTY_MCP_PROMPT> "
        self.marker_prefix = "PTY_MCP_MARKER_"
        self.command_counter = 0
        
    def execute_command(self, cmd: str) -> dict:
        """Execute with precise output capture."""
        # Generate unique markers
        self.command_counter += 1
        start_marker = f"{self.marker_prefix}START_{self.command_counter}"
        end_marker = f"{self.marker_prefix}END_{self.command_counter}"
        
        # Wrap command with markers and exit code capture
        wrapped_cmd = f"""
echo "{start_marker}"
{cmd}
__exit_code__=$?
echo "{end_marker}"
echo "EXIT_CODE:$__exit_code__"
"""
        
        # Send and collect output between markers
        self.process.sendline(wrapped_cmd)
        self.process.expect(start_marker)
        self.process.expect(end_marker)
        
        output = self.process.before
        
        # Get exit code
        self.process.expect("EXIT_CODE:(\d+)")
        exit_code = int(self.process.match.group(1))
        
        return {
            "output": output.strip(),
            "exit_code": exit_code,
            "command": cmd
        }
```

#### Problem: SSH Command Handling
SSH commands often fail due to terminal allocation issues.

**Solution**: Proper SSH flags and environment
```python
def handle_ssh_command(self, cmd: str) -> dict:
    """Special handling for SSH commands."""
    # Detect SSH command
    if cmd.strip().startswith('ssh '):
        # Force pseudo-terminal allocation for interactive SSH
        if '-t' not in cmd and '-T' not in cmd:
            # Check if command is provided (non-interactive)
            ssh_parts = shlex.split(cmd)
            if len(ssh_parts) > 2:  # Has command
                # Non-interactive, disable pseudo-terminal
                cmd = cmd.replace('ssh ', 'ssh -T ', 1)
            else:
                # Interactive SSH, force pseudo-terminal
                cmd = cmd.replace('ssh ', 'ssh -t ', 1)
    
    return self.execute_command(cmd)
```

### 1.2 Stdout/Stderr Separation

Implement proper stdout/stderr capture:

```python
class OutputCapture:
    def __init__(self):
        self.stdout_file = tempfile.NamedTemporaryFile(delete=False)
        self.stderr_file = tempfile.NamedTemporaryFile(delete=False)
    
    def execute_with_separation(self, cmd: str) -> dict:
        """Execute command with separated stdout/stderr."""
        # Use bash process substitution for capture
        wrapped_cmd = f"""
{cmd} > >({self.tee_to_file(self.stdout_file.name)}) \
      2> >({self.tee_to_file(self.stderr_file.name)})
"""
        
        result = self.execute_command(wrapped_cmd)
        
        # Read captured outputs
        stdout = self.read_and_cleanup(self.stdout_file)
        stderr = self.read_and_cleanup(self.stderr_file)
        
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result["exit_code"],
            "combined": result["output"]
        }
    
    def tee_to_file(self, filename: str) -> str:
        """Tee output to both file and terminal."""
        return f"tee {filename}"
```

### 1.3 Multi-line Command Support

Handle multi-line commands and here-documents properly:

```python
class MultiLineHandler:
    def detect_incomplete_command(self, cmd: str) -> bool:
        """Detect if command needs continuation."""
        # Count quotes and brackets
        counts = {
            '"': cmd.count('"') % 2,
            "'": cmd.count("'") % 2,
            '(': cmd.count('(') - cmd.count(')'),
            '[': cmd.count('[') - cmd.count(']'),
            '{': cmd.count('{') - cmd.count('}')
        }
        
        # Check for line continuations
        if cmd.rstrip().endswith('\\'):
            return True
        
        # Check for here-document
        if '<<' in cmd and not self.here_doc_complete(cmd):
            return True
        
        return any(counts.values())
    
    def handle_multiline(self, initial_cmd: str) -> str:
        """Collect full multi-line command."""
        lines = [initial_cmd]
        
        while self.detect_incomplete_command('\n'.join(lines)):
            # Wait for continuation prompt
            self.process.expect(self.cont_prompt)
            # Get next line from caller
            next_line = yield  # Coroutine pattern
            lines.append(next_line)
        
        return '\n'.join(lines)
```

### 1.4 Background Process Management

```python
class BackgroundProcessManager:
    def __init__(self):
        self.background_jobs = {}
    
    def execute_command(self, cmd: str) -> dict:
        """Handle commands with background processes."""
        is_background = cmd.rstrip().endswith('&')
        
        if is_background:
            # Execute in background
            job_id = self.start_background_job(cmd)
            return {
                "output": f"[{job_id}] Started",
                "job_id": job_id,
                "background": True
            }
        else:
            # Normal execution
            return super().execute_command(cmd)
    
    def check_background_jobs(self) -> list:
        """Check status of background jobs."""
        self.process.sendline("jobs -l")
        self.process.expect(self.prompt)
        return self.parse_jobs_output(self.process.before)
```

## Phase 2: Line-Based Interactive Programs

### 2.1 REPL Detection and Management

```python
class REPLManager:
    """Handle line-based interactive programs."""
    
    REPL_PATTERNS = {
        'python': {
            'command': ['python', 'python3'],
            'prompt': '>>> ',
            'continuation': '... ',
            'exit': 'exit()\n'
        },
        'ipython': {
            'command': ['ipython'],
            'prompt': 'In \[\d+\]: ',
            'continuation': '   ...: ',
            'exit': 'exit\n'
        },
        'node': {
            'command': ['node'],
            'prompt': '> ',
            'continuation': '... ',
            'exit': '.exit\n'
        },
        'mysql': {
            'command': ['mysql'],
            'prompt': 'mysql> ',
            'continuation': '    -> ',
            'exit': 'quit\n'
        }
    }
    
    def detect_repl_start(self, cmd: str) -> str | None:
        """Detect if command starts a REPL."""
        cmd_parts = cmd.strip().split()
        if not cmd_parts:
            return None
            
        base_cmd = cmd_parts[0]
        for repl_name, config in self.REPL_PATTERNS.items():
            if base_cmd in config['command']:
                return repl_name
        return None
```

### 2.2 Line-Based Interaction

```python
class LineBasedInteraction:
    def __init__(self, repl_type: str):
        self.repl_config = REPLManager.REPL_PATTERNS[repl_type]
        self.in_repl = False
        self.prompt_pattern = self.repl_config['prompt']
        self.continuation_pattern = self.repl_config['continuation']
    
    def send_line(self, line: str) -> dict:
        """Send a line to the REPL and get response."""
        self.process.sendline(line)
        
        # Wait for prompt (main or continuation)
        patterns = [
            self.prompt_pattern,
            self.continuation_pattern,
            pexpect.TIMEOUT
        ]
        
        index = self.process.expect(patterns, timeout=5)
        
        if index == 0:  # Main prompt
            output = self.process.before
            return {
                "output": output,
                "expecting_more": False,
                "prompt": "main"
            }
        elif index == 1:  # Continuation prompt
            output = self.process.before
            return {
                "output": output,
                "expecting_more": True,
                "prompt": "continuation"
            }
        else:  # Timeout
            # Might be computing or waiting for input
            return {
                "output": self.process.before,
                "timeout": True,
                "buffer": self.process.buffer
            }
    
    def exit_repl(self) -> dict:
        """Exit the REPL cleanly."""
        exit_cmd = self.repl_config['exit']
        self.process.send(exit_cmd)
        self.process.expect(self.original_prompt, timeout=5)
        return {"exited": True}
```

### 2.3 Smart Line Buffering

```python
class SmartLineBuffer:
    """Intelligent line buffering for REPLs."""
    
    def __init__(self, max_lines: int = 1000):
        self.lines = deque(maxlen=max_lines)
        self.incomplete_line = ""
    
    def add_output(self, data: str):
        """Add output data with smart line handling."""
        data = self.incomplete_line + data
        lines = data.split('\n')
        
        # Last piece might be incomplete
        if not data.endswith('\n'):
            self.incomplete_line = lines.pop()
        else:
            self.incomplete_line = ""
        
        self.lines.extend(lines)
    
    def get_recent_lines(self, n: int = 50) -> list[str]:
        """Get recent n lines."""
        return list(self.lines)[-n:]
    
    def clear_after_prompt(self, prompt_pattern: str):
        """Clear buffer after detecting prompt."""
        # Find last prompt in buffer
        for i in range(len(self.lines) - 1, -1, -1):
            if re.match(prompt_pattern, self.lines[i]):
                # Keep only lines after prompt
                self.lines = deque(list(self.lines)[i+1:], maxlen=self.lines.maxlen)
                break
```

## Phase 3: Testing Framework (Priority 1 & 2 Focus)

### 3.1 Bash Command Tests

```python
class TestBashCommands:
    """Test standard bash command execution."""
    
    def test_simple_commands(self, session):
        """Test basic commands."""
        test_cases = [
            ("echo 'Hello World'", "Hello World", 0),
            ("pwd", os.getcwd(), 0),
            ("false", "", 1),
            ("true", "", 0),
            ("exit 42", "", 42)
        ]
        
        for cmd, expected_output, expected_exit in test_cases:
            result = session.execute_command(cmd)
            assert expected_output in result['output']
            assert result['exit_code'] == expected_exit
    
    def test_piped_commands(self, session):
        """Test command pipelines."""
        result = session.execute_command("echo -e 'line1\\nline2\\nline3' | grep line2")
        assert result['output'] == "line2"
        assert result['exit_code'] == 0
    
    def test_stderr_capture(self, session):
        """Test stderr separation."""
        result = session.execute_with_separation("echo stdout; echo stderr >&2")
        assert result['stdout'].strip() == "stdout"
        assert result['stderr'].strip() == "stderr"
    
    def test_multiline_command(self, session):
        """Test multi-line command execution."""
        cmd = """
        for i in {1..3}; do
            echo "Line $i"
        done
        """
        result = session.execute_command(cmd)
        assert "Line 1" in result['output']
        assert "Line 2" in result['output']
        assert "Line 3" in result['output']
    
    def test_background_job(self, session):
        """Test background process handling."""
        result = session.execute_command("sleep 5 &")
        assert result['background'] == True
        assert 'job_id' in result
        
        # Check job status
        jobs = session.check_background_jobs()
        assert len(jobs) > 0
```

### 3.2 SSH Command Tests

```python
class TestSSHCommands:
    """Test SSH command handling."""
    
    def test_ssh_command_execution(self, session, ssh_test_host):
        """Test SSH remote command execution."""
        result = session.execute_command(f"ssh {ssh_test_host} 'echo Remote Output'")
        assert "Remote Output" in result['output']
        assert result['exit_code'] == 0
    
    def test_ssh_error_handling(self, session):
        """Test SSH error cases."""
        result = session.execute_command("ssh nonexistent.host 'echo test'")
        assert result['exit_code'] != 0
        assert "could not resolve" in result['output'].lower() or \
               "name or service not known" in result['output'].lower()
```

### 3.3 REPL Tests

```python
class TestREPLs:
    """Test line-based interactive programs."""
    
    def test_python_repl(self, session):
        """Test Python REPL interaction."""
        # Start Python
        result = session.execute_command("python3")
        assert session.detect_repl_start("python3") == "python"
        
        # Send commands
        result = session.send_repl_line("2 + 2")
        assert "4" in result['output']
        
        result = session.send_repl_line("print('Hello')")
        assert "Hello" in result['output']
        
        # Multi-line input
        result = session.send_repl_line("def foo():")
        assert result['expecting_more'] == True
        
        result = session.send_repl_line("    return 42")
        assert result['expecting_more'] == True
        
        result = session.send_repl_line("")  # Empty line to end
        assert result['expecting_more'] == False
        
        # Exit REPL
        result = session.exit_repl()
        assert result['exited'] == True
    
    def test_ipython_repl(self, session):
        """Test IPython REPL if available."""
        # Check if ipython is available
        check = session.execute_command("which ipython")
        if check['exit_code'] != 0:
            pytest.skip("IPython not available")
        
        result = session.execute_command("ipython")
        
        # Test magic commands
        result = session.send_repl_line("%timeit 2+2")
        assert "nsec" in result['output'] or "usec" in result['output']
```

## Phase 4: Implementation Plan

### Week 1: Foundation (Priority 1)
- Fix prompt detection with marker system
- Implement reliable command execution
- Add exit code capture
- Basic test suite for simple commands

### Week 2: Bash Enhancements (Priority 1)
- Multi-line command support
- Background process handling
- Stdout/stderr separation
- SSH command improvements

### Week 3: Testing & Hardening (Priority 1)
- Comprehensive bash command tests
- Error handling improvements
- Session recovery mechanisms
- Performance optimization

### Week 4: REPL Foundation (Priority 2)
- REPL detection system
- Line-based interaction protocol
- Python REPL support
- Basic REPL tests

### Week 5: REPL Polish (Priority 2)
- Support for IPython, Node, MySQL
- Multi-line REPL input handling
- REPL state management
- Comprehensive REPL tests

### Week 6: Integration & Documentation
- MCP tool updates
- API documentation
- Usage examples
- Performance benchmarks

## Success Metrics

### Priority 1 (Must Have)
- 100% success rate for basic bash commands
- Proper exit code capture
- Reliable SSH command execution
- Clean stdout/stderr separation
- No hanging on multi-line commands

### Priority 2 (Should Have)
- Python/IPython REPL fully functional
- Clean entry/exit from REPLs
- Multi-line REPL input support
- At least 3 REPLs supported

### Priority 3 (Nice to Have)
- Basic vim/nano detection
- Graceful handling of full-screen apps
- Warning when entering unsupported mode

## Technical Decisions

### Why Markers Instead of Prompts
Using unique markers around command output provides:
- Exact output boundaries
- No confusion with command output containing prompt-like strings
- Works regardless of PS1 customization
- Allows accurate exit code capture

### Why Line-Based for REPLs
REPLs are inherently line-oriented:
- Input is processed line by line
- Output comes after each line
- Prompts indicate readiness for next line
- No need for full terminal emulation

### Deferred: Full Terminal Emulation
Full-screen apps require:
- ANSI escape sequence parsing
- Screen buffer management  
- Cursor tracking
- Much more complexity

This is deferred to Priority 3 as it provides less value for most use cases.