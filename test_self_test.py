#!/usr/bin/env python3
"""
Test script to verify the self-test button implementation using TechLazer service protocol
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from ptz.pelcod_controller import PelcoDController
from PyQt6.QtWidgets import QApplication
import time


def test_self_test_buttons():
    """Test the self-test buttons functionality with service protocol"""
    app = QApplication(sys.argv)
    
    # Create a Pelco-D controller instance (replace with your actual IP)
    controller = PelcoDController("192.168.1.115", 9761)  # Default IP, change as needed
    
    # Connect the command signal to print messages
    def print_command(message):
        print(f"Command sent: {message}")
    
    controller.command_sent_signal.connect(print_command)
    
    # Test pan self-test
    print("\nTesting pan axis self-test...")
    pan_success = controller.start_pan_self_test_service_protocol()
    print(f"Pan self-test started: {pan_success}")
    
    # Wait a bit
    time.sleep(1)
    
    # Test tilt self-test
    print("\nTesting tilt axis self-test...")
    tilt_success = controller.start_tilt_self_test_service_protocol()
    print(f"Tilt self-test started: {tilt_success}")
    
    # Wait for processing
    time.sleep(1)
    
    # Test getting axis states
    print("\nTesting getting axis states...")
    pan_state, tilt_state = controller.get_axis_states_service_protocol()
    print(f"Axis states - Pan: {pan_state}, Tilt: {tilt_state}")
    
    # Test getting fault flags
    print("\nTesting getting fault flags...")
    pan_faults, tilt_faults = controller.get_fault_flags_service_protocol()
    print(f"Fault flags - Pan: {pan_faults}, Tilt: {tilt_faults}")
    
    # Clean up
    controller.close_connection()
    print("\nTest completed successfully!")


if __name__ == "__main__":
    test_self_test_buttons()