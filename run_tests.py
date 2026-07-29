"""
Comprehensive Test Suite for OnCam Project

This module provides a unified interface to run all tests
with detailed reporting and coverage analysis.
"""

import pytest
import sys
import os
from datetime import datetime


def run_all_tests(verbose=True, coverage=False):
    """
    Run all tests in the project with optional coverage
    
    Args:
        verbose: Show detailed output
        coverage: Generate coverage report (requires pytest-cov)
    
    Returns:
        bool: True if all tests passed, False otherwise
    """
    
    # Build pytest arguments
    args = []
    
    if verbose:
        args.append('-v')
    
    args.append('--tb=short')
    
    if coverage:
        try:
            import pytest_cov
            args.extend([
                '--cov=.',
                '--cov-report=term-missing',
                '--cov-report=html:htmlcov'
            ])
        except ImportError:
            print("Warning: pytest-cov not installed. Install with: pip install pytest-cov")
    
    # Add test paths
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    if os.path.exists(test_dir):
        args.append(test_dir)
    else:
        # Fallback to current directory
        args.append('.')
    
    # Print header
    print("=" * 70)
    print("OnCam Test Suite")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Run tests
    exit_code = pytest.main(args)
    
    # Print summary
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    return exit_code == 0


def run_test_file(test_file_path, verbose=True):
    """
    Run a specific test file
    
    Args:
        test_file_path: Path to the test file
        verbose: Show detailed output
    
    Returns:
        bool: True if all tests passed, False otherwise
    """
    args = ['-v' if verbose else '-q', '--tb=short', test_file_path]
    exit_code = pytest.main(args)
    return exit_code == 0


if __name__ == '__main__':
    # Parse command line arguments
    verbose = '-v' in sys.argv or '--verbose' in sys.argv
    coverage = '-c' in sys.argv or '--coverage' in sys.argv
    
    success = run_all_tests(verbose=verbose, coverage=coverage)
    sys.exit(0 if success else 1)
