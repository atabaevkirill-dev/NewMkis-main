#!/usr/bin/env python
"""
OnCam - Camera Monitoring and PTZ Control Application
Standalone Executable Entry Point

This script is designed to work with PyInstaller for creating standalone executables.
"""

import sys
import os
import importlib
import logging

def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_modules = {
        'cv2': 'opencv-python',
        'numpy': 'numpy',
        'PyQt6': 'PyQt6',
        'onvif': 'onvif_zeep',
        'zeep': 'zeep',
        'lxml': 'lxml',
        'requests': 'requests',
        'serial': 'pyserial'  # Добавляем pyserial
    }
    
    missing_modules = []
    
    for module_name, package_name in required_modules.items():
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            print(f"Failed to import {module_name}: {e}")
            missing_modules.append((module_name, package_name))
    
    if missing_modules:
        print("Missing required modules:")
        for module_name, package_name in missing_modules:
            print(f"  - {module_name} (install with: pip install {package_name})")
        
        print("\nPlease install required packages using: pip install -r requirements.txt")
        return False
    
    return True

def setup_logging():
    """Setup logging for the application"""
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.expanduser("~"), "OnCamLogs")
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Setup logging
    log_file = os.path.join(logs_dir, "oncam_standalone.log")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also log to console for debugging
        ]
    )

def main():
    """Main function to run the application as standalone executable"""
    print("Starting OnCam standalone application...")
    
    # Change to the directory containing the executable
    if getattr(sys, 'frozen', False):
        # If running as a PyInstaller bundle
        os.chdir(os.path.dirname(sys.executable))
    
    # Add the project root to the Python path
    project_root = os.path.dirname(os.path.abspath(__file__))  # core directory
    parent_dir = os.path.dirname(project_root)  # project root
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Setup logging
    setup_logging()
    
    try:
        # Import and run the main application
        from core.main import main as app_main
        app_main()
    except ImportError as e:
        print(f"Error importing main application: {e}")
        print("Make sure all required modules are installed.")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"Error running application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()