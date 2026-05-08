#!/usr/bin/env python3
"""
Quick start test - starts the service and tests endpoints.
"""

import subprocess
import time
import sys
import signal
import requests
from pathlib import Path

def run_test():
    """Run quick start test."""
    print("Starting ASAN Chrome Mirror service...")
    print("=" * 60)
    
    # Start the service
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for server to start
    print("Waiting for server to start...")
    time.sleep(3)
    
    try:
        # Test health endpoint
        print("Testing health endpoint...")
        resp = requests.get("http://localhost:8000/health", timeout=5)
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {resp.json()}")
        
        # Test root endpoint
        print("\nTesting root endpoint...")
        resp = requests.get("http://localhost:8000/", timeout=5)
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {resp.json()}")
        
        # Test metrics endpoint
        print("\nTesting metrics endpoint...")
        resp = requests.get("http://localhost:8000/metrics", timeout=5)
        print(f"  Status: {resp.status_code}")
        data = resp.json()
        print(f"  Downloads: {data['downloads']}")
        
        print("\n" + "=" * 60)
        print("✓ Quick start test passed!")
        print("=" * 60)
        return 0
        
    except requests.ConnectionError:
        print("✗ Failed to connect to server")
        return 1
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return 1
    finally:
        # Stop the service
        print("\nStopping service...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

if __name__ == "__main__":
    sys.exit(run_test())
