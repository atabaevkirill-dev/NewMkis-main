#!/usr/bin/env python3
"""
Utility script to install AI integration requirements
"""

import subprocess
import sys


def install_requirements():
    """Install required packages for AI integration"""
    print("Installing AI integration requirements...")
    
    # Install requests library if not already installed
    try:
        import requests
        print("✓ Requests library already installed")
    except ImportError:
        print("Installing requests library...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
        print("✓ Requests library installed")
    
    print("AI integration requirements installation complete!")


if __name__ == "__main__":
    install_requirements()