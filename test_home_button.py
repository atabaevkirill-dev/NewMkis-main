#!/usr/bin/env python3
"""
Test script to verify the home button implementation using TechLazer service protocol
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from ptz.pelcod_controller import PelcoDController
from PyQt6.QtWidgets import QApplication
import time


def test_home_button():
    """Test the home button functionality with service protocol"""
    app = QApplication(sys.argv)
    
    # Create a Pelco-D controller instance (replace with your actual IP)
    controller = PelcoDController("192.168.1.115", 9761)  # Default IP, change as needed
    
    # Print initial home position
    pan_pos, tilt_pos, pan_speed, tilt_speed = controller.get_home_position()
    print(f"Initial home position: Pan={pan_pos}°, Tilt={tilt_pos}°, Pan Speed={pan_speed}, Tilt Speed={tilt_speed}")
    
    # Set a custom home position if needed
    controller.set_home_position(pan_pos=0.0, tilt_pos=0.0, pan_speed=15.0, tilt_speed=10.0)
    
    # Connect the command signal to print messages
    def print_command(message):
        print(f"Command sent: {message}")
    
    controller.command_sent_signal.connect(print_command)
    
    # Simulate clicking the home button (this would use the service protocol)
    print("\nTesting home button functionality...")
    controller.send_command('home')
    
    # Wait a bit for the command to process
    time.sleep(2)
    
    # Test moving to home position directly using the public method
    print("\nTesting direct move to home...")
    controller.move_to_home_service_protocol()
    
    # Wait for processing
    time.sleep(2)
    
    # Test getting current positions
    print("\nTesting getting current positions...")
    pan, tilt = controller.get_current_positions_service_protocol()
    print(f"Current positions - Pan: {pan}, Tilt: {tilt}")
    
    # Clean up
    controller.close_connection()
    print("\nTest completed successfully!")


if __name__ == "__main__":
    test_home_button()