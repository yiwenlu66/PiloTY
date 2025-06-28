#!/usr/bin/env python3
"""Test the new poll_output functionality."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from piloty.core import ShellSession

def test_poll_output():
    session = ShellSession()
    
    try:
        print("Test 1: Background counter with poll_output")
        result = session.run("for i in {1..5}; do echo \"Count: $i\"; sleep 0.2; done &")
        print(f"Background job started: {result}")
        
        # Poll multiple times
        for i in range(3):
            time.sleep(0.5)
            output = session.poll_output(timeout=0.1, flush=True)
            print(f"\nPoll {i+1} result:")
            if output:
                print(output)
            else:
                print("(no output)")
                
        print("\nTest 2: Testing without flush")
        result = session.run("echo 'Test without flush' &")
        time.sleep(0.1)
        
        output = session.poll_output(timeout=0.1, flush=False)
        print(f"Without flush: {repr(output)}")
        
        output = session.poll_output(timeout=0.1, flush=True)
        print(f"With flush: {repr(output)}")
        
        print("\nTest 3: Check final state")
        result = session.run("echo 'Done'")
        print(f"Final command: {repr(result)}")
        
    finally:
        session.terminate()

if __name__ == "__main__":
    test_poll_output()