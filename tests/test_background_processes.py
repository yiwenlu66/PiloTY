#!/usr/bin/env python3
"""Test background process handling."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pty_mcp.pty_mcp import ShellSession

def test_background_processes():
    session = ShellSession()
    
    try:
        print("Testing background process support...\n")
        
        # Test 1: Basic background job
        print("1. Basic background job")
        job = session.run_background("sleep 2")
        print(f"   Started: {job}")
        
        jobs = session.check_jobs()
        assert len(jobs) == 1
        assert jobs[0]['status'] == 'Running'
        print("   ✓ Job tracking works")
        
        # Test 2: Background with output
        print("\n2. Background job with output")
        job = session.run_background("echo 'Background output'")
        print(f"   Started: {job}")
        
        # Background output appears with next command
        result = session.run("echo 'Next command'")
        assert 'Background output' in result
        assert 'Next command' in result
        print(f"   ✓ Output captured: '{result}'")
        
        # Test 3: Multiple jobs
        print("\n3. Multiple background jobs")
        job1 = session.run_background("sleep 1")
        job2 = session.run_background("sleep 1")
        
        jobs = session.check_jobs()
        running_jobs = [j for j in jobs if j['status'] == 'Running']
        print(f"   Running jobs: {len(running_jobs)}")
        assert len(running_jobs) >= 2
        print("   ✓ Multiple jobs tracked")
        
        # Test 4: Job completion
        print("\n4. Job completion notices")
        session.run("sleep 0.1 &")  # Quick job
        import time
        time.sleep(0.5)
        
        # Completion notice appears with next command
        result = session.run("echo 'Done'")
        assert 'Done' in result and 'sleep 0.1' in result
        print(f"   ✓ Completion notice captured")
        
        print("\nAll tests passed!")
        
    finally:
        session.terminate()

if __name__ == "__main__":
    test_background_processes()