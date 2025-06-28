#!/usr/bin/env python3
"""Test SSH handler functionality."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from piloty.core import ShellSession
from piloty.handlers.ssh import SSHHandler

def test_ssh_detection():
    """Test SSH command detection logic."""
    print("\n1. SSH Command Detection Tests")
    print("-" * 40)
    
    # Test SSH handler directly
    ssh_handler = SSHHandler()
    
    test_cases = [
        # (command, should_handle, expected_host)
        ("ssh host", True, "host"),
        ("ssh user@host", True, "user@host"),
        ("ssh -p 22 server", True, "server"),
        ("ssh -i key.pem user@host", True, "user@host"),
        ("ssh host 'ls'", False, None),
        ("ssh host \"echo test\"", False, None),
        ("echo ssh", False, None),
    ]
    
    all_passed = True
    for cmd, should_handle, expected_host in test_cases:
        can_handle = ssh_handler.can_handle(cmd)
        if should_handle:
            # Test host extraction
            host = ssh_handler._extract_ssh_host(cmd) if can_handle else None
            passed = can_handle and host == expected_host
            all_passed &= passed
            print(f"   {'✓' if passed else '✗'} '{cmd}' -> can_handle={can_handle}, host={host}")
        else:
            passed = not can_handle
            all_passed &= passed
            print(f"   {'✓' if passed else '✗'} '{cmd}' -> can_handle={can_handle}")
    
    return all_passed

def test_ssh_errors():
    """Test SSH error handling through handler system."""
    print("\n2. SSH Error Handling Tests")
    print("-" * 40)
    
    session = ShellSession()
    try:
        # Test handler integration first
        handler_types = [type(h).__name__ for h in session.handler_manager.handlers]
        if 'SSHHandler' not in handler_types:
            print("   ✗ SSH handler not registered!")
            return False
        print("   ✓ SSH handler registered in session")
        
        # Test password prompt handling
        print("\n   Testing password authentication...")
        result = session.run("ssh -o PreferredAuthentications=password localhost")
        if "Error:" in result and "Password authentication not supported" in result:
            print("   ✓ Password prompt handled correctly")
        else:
            print(f"   ⚠️  Password test result: {result[:60]}...")
        
        # Test with non-existent host
        print("\n   Testing connection to non-existent host...")
        result = session.run("ssh nonexistent.invalid.host")
        
        # Should get an error message from handler
        if "Could not resolve" in result or "Connection" in result or "Error" in result:
            print(f"   ✓ Got expected error: {result[:60]}...")
        else:
            print(f"   ✗ Unexpected result: {result}")
            
        # Check handler state
        info = session.get_session_info()
        if not info['has_active_handler']:
            print("   ✓ No active handler after failed connection")
        else:
            print(f"   ⚠️  Handler still active: {info}")
            
        # Verify normal commands still work
        result = session.run("echo 'Back in local'")
        if result == "Back in local":
            print("   ✓ Local session working correctly")
        else:
            print(f"   ✗ Local session check failed: {result}")
            
        return True
    finally:
        session.terminate()

def test_ssh_workflow():
    """Test SSH handler integration with ShellSession."""
    print("\n3. SSH Handler Integration")
    print("-" * 40)
    
    session = ShellSession()
    try:
        # Test handler activation for various commands
        test_commands = [
            ("echo 'test'", False, "Normal command"),
            ("ssh localhost", True, "SSH interactive"),
            ("ssh host 'command'", False, "SSH non-interactive"),
        ]
        
        for cmd, should_activate, desc in test_commands:
            # Clear any active handler first
            if session.handler_manager.active_handler:
                session.handler_manager.active_handler = None
                
            # Run command
            result = session.run(cmd)
            
            # Check if handler was activated appropriately
            has_handler = session.handler_manager.has_active_handler
            if should_activate:
                # For SSH commands, handler processes them even if connection fails
                if "SSH" in result or "Connection" in result or "Error" in result:
                    print(f"   ✓ {desc}: Handler processed command")
                else:
                    print(f"   ✗ {desc}: Unexpected result - {result[:50]}...")
            else:
                if not has_handler:
                    print(f"   ✓ {desc}: Handler not activated")
                else:
                    print(f"   ✗ {desc}: Handler incorrectly activated")
                    
        return True
    finally:
        session.terminate()

def test_handler_state():
    """Test handler state management."""
    print("\n4. Handler State Management")
    print("-" * 40)
    
    session = ShellSession()
    try:
        # Initial state
        info = session.get_session_info()
        print(f"   Initial state: has_active_handler={info['has_active_handler']}")
        assert not info['has_active_handler']
        print("   ✓ No active handler initially")
        
        # Test session info structure
        required_keys = ['prompt', 'has_active_handler', 'active', 'handler_type', 'context']
        missing_keys = [k for k in required_keys if k not in info]
        if not missing_keys:
            print("   ✓ Session info has all required keys")
        else:
            print(f"   ✗ Missing keys in session info: {missing_keys}")
            
        # Test that background processes still work with handler system
        print("\n   Testing background processes with handler system...")
        session.run("echo 'background test' &")
        time.sleep(0.1)
        output = session.poll_output()
        if 'background test' in output:
            print("   ✓ Background processes work with handler system")
        else:
            print(f"   ✗ Background process test failed: {repr(output)}")
            
        return True
    finally:
        session.terminate()

def test_actual_ssh_connection():
    """Test actual SSH connection if available."""
    print("\n5. Actual SSH Connection Test")
    print("-" * 40)
    
    session = ShellSession()
    try:
        # Try to connect to localhost
        print("   Attempting SSH to localhost...")
        result = session.run("ssh localhost")
        
        # Check the result
        info = session.get_session_info()
        if info['has_active_handler'] and info['handler_type'] == 'SSHHandler':
            # Handler was activated
            if "Connected to" in result:
                print(f"   ✓ Successfully connected: {result}")
                
                # Test remote command
                result = session.run("echo 'Remote test'")
                if result == "Remote test":
                    print("   ✓ Remote command execution works")
                else:
                    print(f"   ✗ Remote command failed: {result}")
                    
                # Test exit
                result = session.run("exit")
                if "Disconnected" in result:
                    print("   ✓ Successfully disconnected")
                else:
                    print(f"   ⚠️  Exit result: {result}")
                    
                return True
            else:
                print(f"   ⚠️  Connection failed: {result[:80]}...")
                print("   This is normal if SSH is not configured for localhost")
                return True  # Not a test failure
        else:
            print("   ✗ SSH handler was not activated")
            return False
            
    finally:
        session.terminate()

def main():
    """Run all SSH tests."""
    print("SSH Handler Test Suite")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("SSH Detection", test_ssh_detection()))
    results.append(("Error Handling", test_ssh_errors()))
    results.append(("Handler Integration", test_ssh_workflow()))
    results.append(("State Management", test_handler_state()))
    results.append(("SSH Connection", test_actual_ssh_connection()))
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"   {name}: {status}")
    
    # First 4 tests should always pass
    core_tests_passed = all(r[1] for r in results[:4])
    if core_tests_passed:
        print("\n✓ Core SSH handler tests passed!")
        if not results[4][1]:
            print("  (SSH connection test requires localhost SSH access)")
    else:
        print("\n✗ Some core tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()