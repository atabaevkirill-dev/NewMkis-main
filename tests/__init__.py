"""
Pytest configuration and test runner for OnCam project
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_tests():
    """Run all tests in the tests directory"""
    
    # Configuration
    config = [
        '-v',  # Verbose output
        '--tb=short',  # Short traceback format
        '-s',  # Print print statements
    ]
    
    # Run tests
    exit_code = pytest.main(config)
    
    return exit_code == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
