import subprocess
import sys
import os

def install_requirements():
    """Install all required packages from requirements.txt"""
    print("Installing required packages for OnCam application...")
    
    # Path to requirements.txt
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    
    try:
        # Run pip install command
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', requirements_path
        ], check=True, capture_output=True, text=True)
        
        print("Successfully installed required packages!")
        print(result.stdout)
        
    except subprocess.CalledProcessError as e:
        print(f"Error installing packages: {e}")
        print(f"Error output: {e.stderr}")
        
        # Try installing packages individually if the bulk install fails
        install_packages_individually()
        
    except FileNotFoundError:
        print("requirements.txt file not found. Attempting to install packages individually...")
        install_packages_individually()

def install_packages_individually():
    """Install packages one by one if requirements.txt fails"""
    packages = [
        'opencv-python>=4.5.0',
        'numpy>=1.19.0',
        'PyQt6>=6.2.0',
        'onvif_zeep>=0.2.12',
        'pyserial>=3.5'
    ]
    
    print("Installing packages individually...")
    
    for package in packages:
        try:
            print(f"Installing {package}...")
            result = subprocess.run([
                sys.executable, '-m', 'pip', 'install', package
            ], check=True, capture_output=True, text=True)
            
            print(f"Successfully installed {package}")
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to install {package}: {e}")
            print(f"Error output: {e.stderr}")

def check_installation():
    """Check if packages were installed correctly"""
    print("\nChecking installation...")
    
    required_modules = {
        'cv2': 'opencv-python',
        'numpy': 'numpy',
        'PyQt6': 'PyQt6',
        'onvif': 'onvif_zeep',
        'serial': 'pyserial'
    }
    
    missing_modules = []
    
    for module_name, package_name in required_modules.items():
        try:
            __import__(module_name)
            print(f"✓ {module_name} ({package_name}) - OK")
        except ImportError:
            print(f"✗ {module_name} ({package_name}) - MISSING")
            missing_modules.append((module_name, package_name))
    
    if missing_modules:
        print(f"\nMissing modules: {[m[1] for m in missing_modules]}")
        print("Please run the installation again or install manually:")
        for _, package in missing_modules:
            print(f"  pip install {package}")
        return False
    else:
        print("\nAll required modules are installed correctly!")
        return True

if __name__ == "__main__":
    install_requirements()
    check_installation()