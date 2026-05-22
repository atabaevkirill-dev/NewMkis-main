#!/usr/bin/env python3
"""
Test script to verify the device information functionality
"""

import sys
from PyQt6.QtWidgets import QApplication
from ui.device_info_dialog import DeviceInfoDialog
from camera.config_manager import config_manager

def test_device_info_dialog():
    app = QApplication(sys.argv)
    
    print("Testing DeviceInfoDialog...")
    print("Current device info from config:")
    current_info = config_manager.get_device_info()
    for key, value in current_info.items():
        print(f"  {key}: {value}")
    
    dialog = DeviceInfoDialog()
    result = dialog.exec()
    
    if result:
        print("\nSaving device info...")
        dialog.save_device_info()
        print("Device info saved successfully!")
        
        # Verify the save worked
        updated_info = config_manager.get_device_info()
        print("\nUpdated device info from config:")
        for key, value in updated_info.items():
            print(f"  {key}: {value}")
    
    return True

if __name__ == "__main__":
    test_device_info_dialog()