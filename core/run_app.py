#!/usr/bin/env python
"""
OnCam - Camera Monitoring and PTZ Control Application

This script runs the main application after checking dependencies.
"""

import sys
import os
import importlib

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_modules = {
        'cv2': 'opencv-python',
        'numpy': 'numpy',
        'PyQt6': 'PyQt6',
        'onvif': 'onvif_zeep',
        'serial': 'pyserial'  # Добавляем pyserial к проверке зависимостей
    }
    
    missing_modules = []
    
    for module_name, package_name in required_modules.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing_modules.append((module_name, package_name))
    
    if missing_modules:
        print("Missing required modules:")
        for module_name, package_name in missing_modules:
            print(f"  - {module_name} (install with: pip install {package_name})")
        
        print("\nPlease install required packages using: python install_requirements.py")
        sys.exit(1)
    
    return True

def main():
    """Main function to run the application"""
    print("Checking dependencies...")
    
    if not check_dependencies():
        sys.exit(1)
    
    print("All dependencies satisfied. Starting OnCam application...")
    
    # Добавляем корень проекта в путь поиска модулей
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    try:
        # Import and run the main application from the core module
        from core.main import main as app_main
        app_main()
    except ImportError as e:
        print(f"Error importing main application: {e}")
        print("Make sure you're running this script from the project root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"Error running application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()