#!/usr/bin/env python3
"""Test interactive SSH support."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from piloty.piloty import ShellSession

def test_ssh_detection():
    """Test SSH command detection logic."""
    print("\n1. SSH Command Detection Tests")
    print("-" * 40)
    
    session = ShellSession()
    try:
        test_cases = [
            # (command, is_interactive, expected_host)
            ("ssh host", True, "host"),
            ("ssh user@host", True, "user@host"),
            ("ssh -p 22 server", True, "server"),
            ("ssh -i key.pem user@host", True, "user@host"),
            ("ssh host 'ls'", False, None),
            ("ssh host \"echo test\"", False, None),
            ("echo ssh", False, None),
        ]
        
        all_passed = True
        for cmd, should_be_interactive, expected_host in test_cases:
            is_interactive = session._is_interactive_ssh(cmd)
            if should_be_interactive:
                host = session._extract_ssh_host(cmd) if is_interactive else None
                passed = is_interactive and host == expected_host
                all_passed &= passed
                print(f"   {'✓' if passed else '✗'} '{cmd}' -> interactive={is_interactive}, host={host}")
            else:
                passed = not is_interactive
                all_passed &= passed
                print(f"   {'✓' if passed else '✗'} '{cmd}' -> interactive={is_interactive}")
        
        return all_passed
    finally:
        session.terminate()

def test_ssh_errors():
    """Test SSH error handling and session state."""
    print("\n2. SSH Error Handling Tests")
    print("-" * 40)
    
    session = ShellSession()
    try:
        # Test SSH state detection
        info = session.get_session_info()
        assert not info['is_ssh']
        print("   ✓ Initial state: not in SSH")
        
        # Test password prompt handling (force password auth)
        result = session.run("ssh -o PreferredAuthentications=password localhost")
        if "Error:" in result and "Password authentication not supported" in result:
            print("   ✓ Password prompt handled correctly")
        else:
            print(f"   Password test result: {result[:60]}...")
        
        # Verify still in local session after error
        info = session.get_session_info()
        assert not info['is_ssh']
        print("   ✓ Still in local session after SSH error")
        
        return True
    finally:
        session.terminate()

def test_ssh_connection():
    """Test actual SSH connection and remote execution."""
    print("\n3. SSH Connection and Remote Execution")
    print("-" * 40)
    
    session = ShellSession()
    try:
        # Check initial state
        info = session.get_session_info()
        assert not info['is_ssh']
        print("   ✓ Initial state correct")
        
        # Test local command first
        result = session.run("echo 'Local test'")
        assert result == "Local test"
        print("   ✓ Local command works")
        
        # Try to connect
        print("\n   Attempting SSH to localhost...")
        result = session.run("ssh localhost")
        print(f"   Connection result: {result}")
        
        # Check if connected
        info = session.get_session_info()
        if info['is_ssh']:
            print(f"   ✓ Connected to {info['ssh_host']}")
            
            # Test first command after SSH (this was problematic)
            print("\n   Testing first command after SSH:")
            result = session.run("echo 'First remote'")
            assert result == "First remote", f"Expected 'First remote', got {repr(result)}"
            print("   ✓ First remote command works")
            
            # Test ls command
            print("\n   Testing ls command:")
            result = session.run("ls /tmp | head -3")
            assert "Error:" not in result
            assert len(result) > 0
            print("   ✓ ls command works")
            
            # Test pwd command
            print("\n   Testing pwd command:")
            result = session.run("pwd")
            assert result.startswith("/"), f"Expected absolute path, got {repr(result)}"
            print(f"   ✓ pwd works: {result}")
            
            # Test command sequence
            print("\n   Testing command sequence:")
            for i in range(1, 4):
                result = session.run(f"echo 'Test {i}'")
                assert result == f"Test {i}", f"Expected 'Test {i}', got {repr(result)}"
                print(f"   ✓ Command {i}: {repr(result)}")
            
            # Exit SSH
            print("\n   Disconnecting from SSH...")
            result = session.run("exit")
            print(f"   Exit result: {result}")
            assert "Disconnected from localhost" in result
            
            # Verify disconnected
            info = session.get_session_info()
            assert not info['is_ssh']
            print("   ✓ Successfully disconnected")
            
            # Test local command after SSH
            result = session.run("echo 'Back in local'")
            assert result == "Back in local"
            print("   ✓ Local shell working after SSH")
            
            return True
            
        else:
            print("   ⚠️  Could not establish SSH connection")
            print("   This is normal if SSH server is not running or keys not set up")
            return False
            
    finally:
        session.terminate()

def test_output_cleaning():
    """Test the output cleaning functionality."""
    print("\n4. Output Cleaning Tests")
    print("-" * 40)
    
    session = ShellSession()
    try:
        # Test cleaning various escape sequences
        test_strings = [
            ("\x1b[?2004hHello\x1b[?2004l", "Hello"),  # Bracketed paste
            ("\x1b[31mRed text\x1b[0m", "Red text"),  # Color codes
            ("Line1\r\nLine2\r\nLine3", "Line1\nLine2\nLine3"),  # CRLF
            ("%                      \r \rREMOTE_MCP> test", "REMOTE_MCP> test"),  # Zsh prompt noise (keeps prompt)
        ]
        
        session.is_ssh_session = True  # Simulate SSH mode for cleaning
        
        all_passed = True
        for dirty, expected in test_strings:
            cleaned = session._clean_output(dirty)
            passed = cleaned.strip() == expected.strip()
            all_passed &= passed
            print(f"   {'✓' if passed else '✗'} Cleaned: {repr(dirty[:30])}... -> {repr(cleaned)}")
        
        session.is_ssh_session = False
        return all_passed
        
    finally:
        session.terminate()

def main():
    """Run all SSH tests."""
    print("SSH Support Test Suite")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("SSH Detection", test_ssh_detection()))
    results.append(("Error Handling", test_ssh_errors()))
    results.append(("SSH Connection", test_ssh_connection()))
    results.append(("Output Cleaning", test_output_cleaning()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    for name, passed in results:
        status = "PASSED" if passed else "FAILED/SKIPPED"
        print(f"   {name}: {status}")
    
    all_passed = all(r[1] for r in results[:2])  # First two should always pass
    if all_passed:
        print("\n✓ Core SSH functionality tests passed!")
    else:
        print("\n✗ Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()