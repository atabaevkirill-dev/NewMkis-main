import os
import sys
import socket
import threading
import time
import struct
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QLabel, QPushButton, QSlider, QLCDNumber, QHBoxLayout, QSpinBox, QComboBox, QCheckBox, QDial, QGridLayout
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from ptz.ptz_controller import PTZController
from camera.config_manager import config_manager
from .techlazer_service_protocol import TechLazerServiceProtocol

# Импортируем модуль serial
import serial

class PelcoDController(QWidget):
    command_sent_signal = pyqtSignal(str)  # Signal for command status updates
    
    def __init__(self, ip, port=9761):
        super().__init__()
        self.ip = ip
        self.port = port  # Use the port passed to the constructor, don't override it
        self.socket = None
        self.connected = False
        self.speed = 0x20  # Default speed (32 out of 63 max)
        
        # Initialize TechLazer service protocol controller (port 9760)
        self.service_protocol = TechLazerServiceProtocol(ip=ip, port=9760)
        
        self.reconnect_timer = None  # Timer for automatic reconnection
        self.setup_ui()
        self.connect_device()
        self.setup_reconnect_timer()
        
        # Create PTZ controller for Camera 1
        cam1_config = config_manager.get_camera_config("camera1")
        self.camera1_ptz = PTZController(
            cam1_config.get("ip", ""),
            cam1_config.get("port", 80),
            cam1_config.get("username", ""),
            cam1_config.get("password", "")
        )
        self.camera1_ptz.init_ptz()
        
    def zoom_camera_in(self):
        """Zoom in camera 1 using ONVIF"""
        try:
            self.camera1_ptz.zoom('in')
        except Exception as e:
            print(f"Error in zoom_camera_in: {str(e)}")
            self.command_sent_signal.emit(f"Error in zoom_camera_in: {str(e)}")

    def zoom_camera_out(self):
        """Zoom out camera 1 using ONVIF"""
        try:
            self.camera1_ptz.zoom('out')
        except Exception as e:
            print(f"Error in zoom_camera_out: {str(e)}")
            self.command_sent_signal.emit(f"Error in zoom_camera_out: {str(e)}")

    def stop_camera_zoom(self):
        """Stop zooming camera 1 using ONVIF"""
        try:
            self.camera1_ptz.stop_zoom()
        except Exception as e:
            print(f"Error in stop_camera_zoom: {str(e)}")
            self.command_sent_signal.emit(f"Error in stop_camera_zoom: {str(e)}")
   
      
    
    def setup_reconnect_timer(self):
        """Setup a timer to periodically try to reconnect if disconnected"""
        self.reconnect_timer = QTimer()
        self.reconnect_timer.timeout.connect(self.try_reconnect)
        self.reconnect_timer.start(10000)  # Try to reconnect every 10 seconds
        
 


    def reconnect_camera(self):
        """Reconnect to the camera"""
        if not self.is_connected():
            print(f"Reconnecting to camera {self.ip}")
            self.connect()

    def send_command(self, command):
        """Send a command to the camera (legacy method)"""
        # This method is kept for backward compatibility
        self._send_command_thread(command)

 
    def try_reconnect(self):
        """Try to reconnect if disconnected"""
        # Only attempt to reconnect if we're not already connected
        if not self.connected:
            print(f"Attempting to reconnect to Pelco-D device at {self.ip}:{self.port}")
            self.connect_device()
        else:
            # If we're already connected, just print a message and continue
            print(f"Already connected to Pelco-D device at {self.ip}:{self.port}, skipping reconnection")
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Connection info group
        conn_group = QGroupBox()
        conn_layout = QVBoxLayout()
        self.conn_info_label = QLabel(f"IP: {self.ip}:{self.port}")  # This already shows the port
        self.conn_status_label = QLabel("Status: Disconnected")
        conn_layout.addWidget(self.conn_info_label)
        conn_layout.addWidget(self.conn_status_label)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # Speed control group
        speed_group = QGroupBox()
        speed_layout = QVBoxLayout()
        
        # Speed slider
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(63)
        self.speed_slider.setValue(self.speed)
        self.speed_slider.valueChanged.connect(self.speed_changed)
        
        # Speed display
        self.speed_display = QLCDNumber()
        self.speed_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.speed_display.display(self.speed)
        
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_display)
        speed_group.setLayout(speed_layout)
        layout.addWidget(speed_group)
        
        # Protocol settings group
        # protocol_group = QGroupBox("Protocol Settings")
        # protocol_layout = QGridLayout()
        
        # Protocol selection
        protocol_label = QLabel("Protocol:")
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["Pelco-D", "Pelco-P"])
        self.protocol_combo.setCurrentText("Pelco-D")
        
        # Address setting
        address_label = QLabel("Device Address:")
        self.address_spin = QSpinBox()
        self.address_spin.setMinimum(1)
        self.address_spin.setMaximum(255)
        self.address_spin.setValue(1)
        
        # Baud rate setting
        baud_label = QLabel("Baud Rate:")
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["2400", "4800", "9600", "19200", "38400"])
        self.baud_combo.setCurrentText("9600")
        
        # Invert tilt checkbox
        self.invert_tilt_checkbox = QCheckBox("Invert Tilt Control")
        self.invert_tilt_checkbox.setToolTip("Check this if up/down controls work in opposite direction")
        self.invert_tilt_checkbox.setChecked(True)  # Включаем инверсию по умолчанию
        
        # Oscillation controls
        oscillation_group = QGroupBox()
        oscillation_layout = QVBoxLayout()
        
        # Toggle button for oscillation mode
        self.oscillate_button = QPushButton("Start Spin Test")
        self.oscillate_button.setCheckable(True)
        self.oscillate_button.clicked.connect(self.toggle_oscillation)
        
        # Horizontal oscillation settings with QDial only
        h_osc_layout = QHBoxLayout()
        # h_osc_layout.addWidget(QLabel("Horizontal:"))
        self.h_min_dial = QDial()
        self.h_min_dial.setRange(-180, 180)
        self.h_min_dial.setValue(-45)
        self.h_min_dial.setFixedSize(60, 60)  # Make dial square
        self.h_min_dial.setNotchesVisible(False)
        self.h_min_dial.setStyleSheet("""
            QDial {
                background-color: #3c3c3c;
                border-radius: 10px;
            }
            QDial::groove {
                border: 1px solid #555555;
                background: #2b2b2b;
                border-radius: 5px;
            }
            QDial::handle {
                background: #666666;
                border: 1px solid #888888;
                width: 10px;
                height: 10px;
                border-radius: 5px;
            }
        """)
        
        # Create labels to show values directly on dials
        h_min_label = QLabel("-45°")
        h_min_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_min_label.setStyleSheet("font-size: 10px; color: #cccccc;")
        self.h_min_dial.valueChanged.connect(
            lambda value: h_min_label.setText(f"{value}°"))
        
        # h_osc_layout.addWidget(QLabel("Min:"))
        # h_osc_layout.addWidget(self.h_min_dial)
        # h_osc_layout.addWidget(h_min_label)
        
        self.h_max_dial = QDial()
        self.h_max_dial.setRange(-180, 180)
        self.h_max_dial.setValue(45)
        self.h_max_dial.setFixedSize(60, 60)  # Make dial square
        self.h_max_dial.setNotchesVisible(False)
        self.h_max_dial.setStyleSheet("""
            QDial {
                background-color: #3c3c3c;
                border-radius: 10px;
            }
            QDial::groove {
                border: 1px solid #555555;
                background: #2b2b2b;
                border-radius: 5px;
            }
            QDial::handle {
                background: #666666;
                border: 1px solid #888888;
                width: 10px;
                height: 10px;
                border-radius: 5px;
            }
        """)
        
        h_max_label = QLabel("45°")
        h_max_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_max_label.setStyleSheet("font-size: 10px; color: #cccccc;")
        self.h_max_dial.valueChanged.connect(
            lambda value: h_max_label.setText(f"{value}°"))
        
        # h_osc_layout.addWidget(QLabel("Max:"))
        # h_osc_layout.addWidget(self.h_max_dial)
        # h_osc_layout.addWidget(h_max_label)
        
        # Vertical oscillation settings with QDial only
        v_osc_layout = QHBoxLayout()
        # v_osc_layout.addWidget(QLabel("Tilt:"))
        self.v_min_dial = QDial()
        self.v_min_dial.setRange(-180, 180)
        self.v_min_dial.setValue(-30)
        self.v_min_dial.setFixedSize(60, 60)  # Make dial square
        self.v_min_dial.setNotchesVisible(False)
        self.v_min_dial.setStyleSheet("""
            QDial {
                background-color: #3c3c3c;
                border-radius: 10px;
            }
            QDial::groove {
                border: 1px solid #555555;
                background: #2b2b2b;
                border-radius: 5px;
            }
            QDial::handle {
                background: #666666;
                border: 1px solid #888888;
                width: 10px;
                height: 10px;
                border-radius: 5px;
            }
        """)
        
        v_min_label = QLabel("-30°")
        v_min_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_min_label.setStyleSheet("font-size: 10px; color: #cccccc;")
        self.v_min_dial.valueChanged.connect(
            lambda value: v_min_label.setText(f"{value}°"))
        
        v_osc_layout.addWidget(QLabel("Min:"))
        v_osc_layout.addWidget(self.v_min_dial)
        v_osc_layout.addWidget(v_min_label)
        
        self.v_max_dial = QDial()
        self.v_max_dial.setRange(-180, 180)
        self.v_max_dial.setValue(30)
        self.v_max_dial.setFixedSize(60, 60)  # Make dial square
        self.v_max_dial.setNotchesVisible(False)
        self.v_max_dial.setStyleSheet("""
            QDial {
                background-color: #3c3c3c;
                border-radius: 10px;
            }
            QDial::groove {
                border: 1px solid #555555;
                background: #2b2b2b;
                border-radius: 5px;
            }
            QDial::handle {
                background: #666666;
                border: 1px solid #888888;
                width: 10px;
                height: 10px;
                border-radius: 5px;
            }
        """)
        
        v_max_label = QLabel("30°")
        v_max_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_max_label.setStyleSheet("font-size: 10px; color: #cccccc;")
        self.v_max_dial.valueChanged.connect(
            lambda value: v_max_label.setText(f"{value}°"))
        
        v_osc_layout.addWidget(QLabel("Max:"))
        v_osc_layout.addWidget(self.v_max_dial)
        v_osc_layout.addWidget(v_max_label)
        
        # Speed settings for oscillation
        osc_speed_layout = QHBoxLayout()
        osc_speed_layout.addWidget(QLabel("Speed:"))
        self.osc_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.osc_speed_slider.setMinimum(1)
        self.osc_speed_slider.setMaximum(63)
        self.osc_speed_slider.setValue(30)
        self.osc_speed_display = QLCDNumber()
        self.osc_speed_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.osc_speed_display.display(30)
        self.osc_speed_slider.valueChanged.connect(
            lambda value: self.osc_speed_display.display(value)
        )
        osc_speed_layout.addWidget(self.osc_speed_slider)
        osc_speed_layout.addWidget(self.osc_speed_display)
        
        oscillation_layout.addWidget(self.oscillate_button)
        oscillation_layout.addLayout(h_osc_layout)
        oscillation_layout.addLayout(v_osc_layout)
        oscillation_layout.addLayout(osc_speed_layout)
        
        oscillation_group.setLayout(oscillation_layout)
        layout.addWidget(oscillation_group)
        
        # Temperature sensor
        self.temp_label = QLabel("Temperature:")
        self.temp_value = QLabel("? °C")
        # Voltage sensor
        self.voltage_label = QLabel("Voltage:")
        self.voltage_value = QLabel("? V")
        # Pan state
        self.pan_state_label = QLabel("Pan State:")
        self.pan_state_value = QLabel("?")
        # Tilt state
        self.tilt_state_label = QLabel("Tilt State:")
        self.tilt_state_value = QLabel("?")
        # Position info
        self.pan_pos_label = QLabel("Pan Position:")
        self.pan_pos_value = QLabel("? °")
        self.tilt_pos_label = QLabel("Tilt Position:")
        self.tilt_pos_value = QLabel("? °")
        
        # PTZ Control Group for Pelco-D Unit
        ptz_group = QGroupBox()
        ptz_layout = QGridLayout()
        
        # Create PTZ buttons
        self.up_btn = QPushButton("↑")
        self.down_btn = QPushButton("↓")
        self.left_btn = QPushButton("←")
        self.right_btn = QPushButton("→")
        self.up_left_btn = QPushButton("↖")
        self.up_right_btn = QPushButton("↗")
        self.down_left_btn = QPushButton("↙")
        self.down_right_btn = QPushButton("↘")
        self.zoom_in_btn = QPushButton("Zoom +")
        self.zoom_out_btn = QPushButton("Zoom -")
        self.stop_btn = QPushButton("Stop")
        self.home_btn = QPushButton("Home")
        self.pan_self_test_btn = QPushButton("Self-Test Pan")
        self.tilt_self_test_btn = QPushButton("Self-Test Tilt")
        
        # Set button sizes
        button_size = 40
        self.up_btn.setFixedSize(100, button_size)
        self.down_btn.setFixedSize(100, button_size)
        self.left_btn.setFixedSize(100, button_size)
        self.right_btn.setFixedSize(100, button_size)
        self.up_left_btn.setFixedSize(100, button_size)
        self.up_right_btn.setFixedSize(100, button_size)
        self.down_left_btn.setFixedSize(100, button_size)
        self.down_right_btn.setFixedSize(100, button_size)
        self.zoom_in_btn.setFixedSize(100, button_size)
        self.zoom_out_btn.setFixedSize(100, button_size)
        self.stop_btn.setFixedHeight(button_size)
        self.home_btn.setFixedHeight(button_size)
        self.pan_self_test_btn.setFixedHeight(button_size)
        self.tilt_self_test_btn.setFixedHeight(button_size)
        
        # Connect buttons to functions with press and release events
        self.up_btn.pressed.connect(lambda: self.send_command('up'))
        self.up_btn.released.connect(lambda: self.send_command('stop'))
        self.down_btn.pressed.connect(lambda: self.send_command('down'))
        self.down_btn.released.connect(lambda: self.send_command('stop'))
        self.left_btn.pressed.connect(lambda: self.send_command('left'))
        self.left_btn.released.connect(lambda: self.send_command('stop'))
        self.right_btn.pressed.connect(lambda: self.send_command('right'))
        self.right_btn.released.connect(lambda: self.send_command('stop'))
        self.up_left_btn.pressed.connect(lambda: self.send_command('up_left'))
        self.up_left_btn.released.connect(lambda: self.send_command('stop'))
        self.up_right_btn.pressed.connect(lambda: self.send_command('up_right'))
        self.up_right_btn.released.connect(lambda: self.send_command('stop'))
        self.down_left_btn.pressed.connect(lambda: self.send_command('down_left'))
        self.down_left_btn.released.connect(lambda: self.send_command('stop'))
        self.down_right_btn.pressed.connect(lambda: self.send_command('down_right'))
        self.down_right_btn.released.connect(lambda: self.send_command('stop'))
        self.zoom_in_btn.pressed.connect(self.zoom_camera_in)
        self.zoom_in_btn.released.connect(self.stop_camera_zoom)
        self.zoom_out_btn.pressed.connect(self.zoom_camera_out)
        self.zoom_out_btn.released.connect(self.stop_camera_zoom)
        self.stop_btn.clicked.connect(lambda: self.send_command('stop'))
        self.home_btn.clicked.connect(lambda: self.send_command('home'))
        
        # Connect self-test buttons
        self.pan_self_test_btn.clicked.connect(self.start_pan_self_test_service_protocol)
        self.tilt_self_test_btn.clicked.connect(self.start_tilt_self_test_service_protocol)
        
        # Arrange buttons in grid
        ptz_layout.addWidget(self.up_btn, 0, 1)
        ptz_layout.addWidget(self.up_left_btn, 0, 0)
        ptz_layout.addWidget(self.up_right_btn, 0, 2)
        ptz_layout.addWidget(self.left_btn, 1, 0)
        ptz_layout.addWidget(self.stop_btn, 1, 1)
        ptz_layout.addWidget(self.right_btn, 1, 2)
        ptz_layout.addWidget(self.down_left_btn, 2, 0)
        ptz_layout.addWidget(self.down_btn, 2, 1)
        ptz_layout.addWidget(self.down_right_btn, 2, 2)
        ptz_layout.addWidget(self.zoom_in_btn, 3, 0)
        ptz_layout.addWidget(self.zoom_out_btn, 3, 2)
        ptz_layout.addWidget(self.home_btn, 4, 0, 1, 1)
        ptz_layout.addWidget(self.pan_self_test_btn, 4, 1, 1, 1)
        ptz_layout.addWidget(self.tilt_self_test_btn, 4, 2, 1, 1)
        
        ptz_group.setLayout(ptz_layout)
        layout.addWidget(ptz_group)
        layout.addStretch()
        self.setLayout(layout)
        
        # Oscillation state variables
        self.oscillation_active = False
        self.oscillation_timer = QTimer()
        self.oscillation_timer.timeout.connect(self.oscillation_step)
        self.current_direction = {'pan': 1, 'tilt': 1}  # 1 for positive, -1 for negative
        self.current_position = {'pan': 0, 'tilt': 0}
        
        # Home position configuration
        self.home_pan_position = 0.0  # Default home pan position in degrees
        self.home_tilt_position = 0.0  # Default home tilt position in degrees
        self.home_pan_speed = 15.0    # Default home movement speed for pan
        self.home_tilt_speed = 10.0   # Default home movement speed for tilt
        
    def set_home_position(self, pan_pos=0.0, tilt_pos=0.0, pan_speed=15.0, tilt_speed=10.0):
        """
        Set the home position for the device
        :param pan_pos: Home pan position in degrees (0.00-359.99)
        :param tilt_pos: Home tilt position in degrees (0.00-359.99)
        :param pan_speed: Max speed for pan movement to home
        :param tilt_speed: Max speed for tilt movement to home
        """
        if 0.00 <= pan_pos <= 359.99:
            self.home_pan_position = pan_pos
        else:
            print(f"Warning: Pan position {pan_pos} is out of range (0.00-359.99), using default 0.0")
        
        if 0.00 <= tilt_pos <= 359.99:
            self.home_tilt_position = tilt_pos
        else:
            print(f"Warning: Tilt position {tilt_pos} is out of range (0.00-359.99), using default 0.0")
            
        if pan_speed > 0:
            self.home_pan_speed = pan_speed
        if tilt_speed > 0:
            self.home_tilt_speed = tilt_speed

    def get_home_position(self):
        """Get the current home position settings"""
        return self.home_pan_position, self.home_tilt_position, self.home_pan_speed, self.home_tilt_speed

    def speed_changed(self, value):
        self.speed = value
        self.speed_display.display(value)
        self.command_sent_signal.emit(f"Speed changed to: {value}")
        
    def connect_device(self):
        # Run connection in separate thread to prevent blocking UI
        connect_thread = threading.Thread(target=self._connect_device_thread, daemon=True)
        connect_thread.start()
    
    def _connect_device_thread(self):
        # Close existing socket if it exists
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
                
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.ip, self.port))
            self.connected = True
            success_msg = f"Connected to Pelco-D device at {self.ip}:{self.port}"
            print(success_msg)
            self.command_sent_signal.emit(success_msg)
            # Update connection status label
            self.conn_status_label.setText("Status: Connected")
            self.conn_status_label.setStyleSheet("color: green;")
            self.enable_controls()
            
            # Stop reconnect timer when successfully connected (safely from UI thread)
            if self.reconnect_timer and self.reconnect_timer.isActive():
                QTimer.singleShot(0, lambda: self.reconnect_timer.stop() if self.reconnect_timer.isActive() else None)
                
        except socket.timeout:
            error_msg = f"Failed to connect to Pelco-D device at {self.ip}:{self.port} - Connection timed out"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            # Update connection status label
            self.conn_status_label.setText("Status: Connection timed out")
            self.conn_status_label.setStyleSheet("color: orange;")
            self.disable_controls()
        except ConnectionRefusedError:
            error_msg = f"Failed to connect to Pelco-D device at {self.ip}:{self.port} - Connection refused"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            # Update connection status label
            self.conn_status_label.setText("Status: Connection refused")
            self.conn_status_label.setStyleSheet("color: red;")
            self.disable_controls()
        except Exception as e:
            error_msg = f"Failed to connect to Pelco-D device at {self.ip}:{self.port} - {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            # Update connection status label
            self.conn_status_label.setText(f"Status: Error - {str(e)[:30]}")
            self.conn_status_label.setStyleSheet("color: red;")
            self.disable_controls()
    
    def disable_controls(self):
        # Use QTimer to safely update UI from another thread
        QTimer.singleShot(0, self._disable_controls_ui)
    
    def _disable_controls_ui(self):
        # Disable buttons if connection failed
        self.up_btn.setEnabled(False)
        self.down_btn.setEnabled(False)
        self.left_btn.setEnabled(False)
        self.right_btn.setEnabled(False)
        # self.zoom_in_btn.setEnabled(False)
        # self.zoom_out_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.home_btn.setEnabled(False)
        self.pan_self_test_btn.setEnabled(False)
        self.tilt_self_test_btn.setEnabled(False)
        self.speed_slider.setEnabled(False)
        # Update connection status label
        self.conn_status_label.setText("Status: Disconnected")
        self.conn_status_label.setStyleSheet("color: red;")
    
    def send_command(self, command):
        # Run command sending in separate thread to prevent blocking UI
        try:
            command_thread = threading.Thread(target=self._send_command_thread, args=(command,), daemon=True)
            command_thread.start()
        except Exception as e:
            error_msg = f"Error starting command thread: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
    
    def _send_command_thread(self, command):
        """Send a command in a separate thread to prevent UI blocking"""
        # For protocol-agnostic commands, determine based on command format
        # If it starts with '$' it's a service protocol command
        if isinstance(command, str) and command.startswith('$'):
            # Always use service protocol for commands starting with $
            self._send_command_thread_service_protocol(command)
        elif command == 'home':
            # Use service protocol for home command instead of Pelco-D
            self._send_home_command_service_protocol()
        else:
            # Use traditional Pelco-D command
            self._send_command_thread_pelco_d(command)
            
    def _send_command_thread_pelco_d(self, command):
        if not self.connected:
            # Try to reconnect
            self._connect_device_thread()
            if not self.connected:
                msg = f"Not connected to Pelco-D device at {self.ip}"
                print(msg)
                self.command_sent_signal.emit(msg)
                return
            
        try:
            # Pelco-D protocol structure:
            # Sync (1 byte) | Address (1 byte) | Command1 (1 byte) | Command2 (1 byte) | Data1 (1 byte) | Data2 (1 byte) | Checksum (1 byte)
            
            address = self.address_spin.value() if hasattr(self, 'address_spin') else 0x01  # Use address from settings
            command1 = 0x00
            command2 = 0x00
            data1 = 0x00  # Speed for pan (0x00 to 0x3F)
            data2 = 0x00  # Speed for tilt (0x00 to 0x3F)
            
            # Check if tilt inversion is enabled
            invert_tilt = self.invert_tilt_checkbox.isChecked() if hasattr(self, 'invert_tilt_checkbox') else False
            
            if command == 'up':
                if invert_tilt:
                    command1 = 0x08
                else:
                    command1 = 0x00
            elif command == 'down':
                if invert_tilt:
                    command1 = 0x00
                else:
                    command1 = 0x08
            elif command == 'left':
                command1 = 0x04
            elif command == 'right':
                command1 = 0x02
            elif command == 'up_left':
                if invert_tilt:
                    command1 = 0x0C
                else:
                    command1 = 0x04
            elif command == 'up_right':
                if invert_tilt:
                    command1 = 0x0A
                else:
                    command1 = 0x02
            elif command == 'down_left':
                if invert_tilt:
                    command1 = 0x04
                else:
                    command1 = 0x0C
            elif command == 'down_right':
                if invert_tilt:
                    command1 = 0x02
                else:
                    command1 = 0x0A
            elif command == 'stop':
                command1 = 0x0F
            elif command == 'home':
                command1 = 0x07
            elif command == 'zoom_in':
                command2 = 0x02
            elif command == 'zoom_out':
                command2 = 0x03
            elif command == 'preset_recall':
                command2 = 0x09
            elif command == 'preset_set':
                command2 = 0x0B
            elif command == 'preset_clear':
                command2 = 0x0C
            elif command == 'preset_home':
                command2 = 0x0D
            elif command == 'preset_recall_home':
                command2 = 0x0E
            elif command == 'preset_recall_last':
                command2 = 0x0F
            elif command == 'preset_recall_next':
                command2 = 0x10
            elif command == 'preset_recall_prev':
                command2 = 0x11
            elif command == 'preset_recall_first':
                command2 = 0x12
            elif command == 'stop_zoom':  # Adding a new command to replace duplicates
                command2 = 0x00  # No zoom
            elif command == 'focus_near':
                command2 = 0x04
            elif command == 'focus_far':
                command2 = 0x05
            elif command == 'iris_open':
                command2 = 0x06
            elif command == 'iris_close':
                command2 = 0x07
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x16
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x17
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x18
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x19
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x1A
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x1B
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x1C
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x1D
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x1E
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x1F
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x20
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x21
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x22
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x23
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x24
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x25
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x26
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x27
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x28
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x29
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x2A
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x2B
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x2C
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x2D
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x2E
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x2F
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x30
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x31
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x32
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x33
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x34
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x35
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x36
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x37
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x38
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x39
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x3A
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x3B
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x3C
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x3D
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x3E
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x3F
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x40
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x41
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x42
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x43
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x44
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x45
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x46
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x47
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x48
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x49
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x4A
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x4B
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x4C
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x4D
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x4E
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x4F
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x50
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x51
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x52
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x53
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x54
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x55
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x56
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x57
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x58
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x59
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x5A
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x5B
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x5C
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x5D
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x5E
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x5F
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x60
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x61
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x62
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x63
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x64
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x65
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x66
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x67
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x68
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x69
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x68  # Исправлено дублирование
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x69  # Исправлено дублирование
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x6A
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x6B
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x6C
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x6D
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x6E
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x6F
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x70
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x71
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x72
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x73
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x74
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x75
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x76
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x77
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x78
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x79
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x7A
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x7B
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x7C
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x7D
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x7E
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x7F
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x80
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x81
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x82
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x83
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x84
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x85
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x86
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x87
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x88
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x89
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x8A
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x8B
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x8C
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x8D
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x8E
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x8F
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x90
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x91
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x92
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x93
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x94
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x95
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x96
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x97
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x98
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x99
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x9A
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x9B
            #elif command == 'preset_recall_first':  # Удалено дублирование
            #    command2 = 0x9C
            #elif command == 'preset_recall_last':   # Удалено дублирование
            #    command2 = 0x9D
            #elif command == 'preset_recall_next':   # Удалено дублирование
            #    command2 = 0x9E  # Добавлено завершающее значение
            #elif command == 'preset_recall_prev':   # Удалено дублирование
            #    command2 = 0x9F  # Добавлено завершающее значение
            elif command == 'preset_recall_prev':
                command2 = 0xAF
            elif command == 'preset_recall_first':
                command2 = 0xB0
            elif command == 'preset_recall_last':
                command2 = 0xB1
            elif command == 'preset_recall_next':
                command2 = 0xB2
            else:
                raise ValueError(f"Unknown command: {command}")
            
            data1 = self.speed
            data2 = self.speed
            
            # Calculate checksum
            checksum = address + command1 + command2 + data1 + data2
            checksum = checksum & 0xFF  # Mask to 8 bits
            
            # Create command packet
            command_packet = bytes([0xFF, address, command1, command2, data1, data2, checksum])
            
            # Send command
            self.socket.send(command_packet)
            self.command_sent_signal.emit(f"Sent command: {command}")
            
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            error_msg = f"Connection error: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            QTimer.singleShot(0, lambda: self._update_connection_status_ui(False))
            
        except Exception as e:
            error_msg = f"Error sending command: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
    
    def _connect_device_thread(self):
        # Close existing socket if it exists
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
                
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.ip, self.port))
            self.connected = True
            success_msg = f"Connected to Pelco-D device at {self.ip}:{self.port}"
            print(success_msg)
            self.command_sent_signal.emit(success_msg)
            # Update connection status label
            self.conn_status_label.setText("Status: Connected")
            self.conn_status_label.setStyleSheet("color: green;")
            self.enable_controls()
            
            # Stop reconnect timer when successfully connected (safely from UI thread)
            if self.reconnect_timer and self.reconnect_timer.isActive():
                QTimer.singleShot(0, lambda: self.reconnect_timer.stop() if self.reconnect_timer.isActive() else None)
                
        except socket.timeout:
            error_msg = f"Failed to connect to Pelco-D device at {self.ip}:{self.port} - Connection timed out"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            # Update connection status label
            self.conn_status_label.setText("Status: Connection timed out")
            self.conn_status_label.setStyleSheet("color: orange;")
            self.disable_controls()
        except ConnectionRefusedError:
            error_msg = f"Failed to connect to Pelco-D device at {self.ip}:{self.port} - Connection refused"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            # Update connection status label
            self.conn_status_label.setText("Status: Connection refused")
            self.conn_status_label.setStyleSheet("color: red;")
            self.disable_controls()
        except Exception as e:
            error_msg = f"Failed to connect to Pelco-D device at {self.ip}:{self.port} - {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            # Update connection status label
            self.conn_status_label.setText(f"Status: Error - {str(e)[:30]}")
            self.conn_status_label.setStyleSheet("color: red;")
            self.disable_controls()
    
    def close_connection(self):
        """Close the connection and stop the reconnect timer"""
        # Stop the reconnect timer safely from the UI thread
        if self.reconnect_timer and self.reconnect_timer.isActive():
            # Use QTimer.singleShot to stop the timer from the UI thread
            QTimer.singleShot(0, lambda: self.reconnect_timer.stop() if self.reconnect_timer.isActive() else None)
            
        # Close the Pelco-D socket
        if self.socket:
            try:
                # Shutdown the socket gracefully
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except:
                # If shutdown fails, just close forcefully
                try:
                    self.socket.close()
                except:
                    pass
            self.socket = None
            self.connected = False
            self.disable_controls()
            self.command_sent_signal.emit("Connection closed")
            # Update connection status label
            self.conn_status_label.setText("Status: Disconnected")
            self.conn_status_label.setStyleSheet("color: red;")
        
        # Close the service protocol connection
        if self.service_protocol:
            self.service_protocol.close()

    def closeEvent(self, event):
        """Handle widget closing"""
        self.close_connection()
        event.accept()

    def toggle_oscillation(self):
        """Toggle oscillation mode on/off"""
        if self.oscillate_button.isChecked():
            self.start_oscillation()
        else:
            self.stop_oscillation()
    
    def start_oscillation(self):
        """Start oscillation mode"""
        if not self.connected:
            self.command_sent_signal.emit("Cannot start oscillation: Not connected to device")
            self.oscillate_button.setChecked(False)
            return
            
        self.oscillation_active = True
        self.oscillate_button.setText("Stop Oscillation")
        self.command_sent_signal.emit("Oscillation mode started")
        
        # Initialize current position (in real implementation, you might get actual position from device)
        self.current_position = {'pan': 0, 'tilt': 0}
        self.current_direction = {'pan': 1, 'tilt': 1}
        
        # Start oscillation timer (update every 100ms)
        self.oscillation_timer.start(100)
        
        # Disable manual controls during oscillation
        self.set_manual_controls_enabled(False)
    
    def stop_oscillation(self):
        """Stop oscillation mode"""
        self.oscillation_active = False
        self.oscillation_timer.stop()
        
        # Stop any ongoing movement
        self.send_command('stop')
        
        self.oscillate_button.setText("Start Oscillation")
        self.command_sent_signal.emit("Oscillation mode stopped")
        
        # Re-enable manual controls
        self.set_manual_controls_enabled(True)
    
    def oscillation_step(self):
        """Perform one step of oscillation"""
        if not self.oscillation_active:
            return
            
        # Get oscillation parameters from dials
        h_min = self.h_min_dial.value()
        h_max = self.h_max_dial.value()
        v_min = self.v_min_dial.value()
        v_max = self.v_max_dial.value()
        speed = self.osc_speed_slider.value()
        
        # Save current speed and restore after
        old_speed = self.speed
        self.speed = speed
        
        # Update pan position - continuous rotation
        # Calculate new pan position with continuous rotation
        new_pan = self.current_position['pan'] + (self.current_direction['pan'] * 2)
        if new_pan >= h_max:
            self.current_position['pan'] = h_min  # Wrap to min when reaching max
        elif new_pan <= h_min:
            self.current_position['pan'] = h_max  # Wrap to max when reaching min
        else:
            self.current_position['pan'] = new_pan
            
        # Update tilt position - oscillation between min and max with direction change
        new_tilt = self.current_position['tilt'] + (self.current_direction['tilt'] * 1.5)
        if new_tilt >= v_max:
            self.current_direction['tilt'] = -1  # Change direction to negative
            self.current_position['tilt'] = v_max
        elif new_tilt <= v_min:
            self.current_direction['tilt'] = 1   # Change direction to positive
            self.current_position['tilt'] = v_min
        else:
            self.current_position['tilt'] = new_tilt
            
        # Send combined movement command
        if self.current_direction['pan'] > 0 and self.current_direction['tilt'] > 0:
            self.send_command('up_right')
        elif self.current_direction['pan'] > 0 and self.current_direction['tilt'] < 0:
            self.send_command('down_right')
        elif self.current_direction['pan'] < 0 and self.current_direction['tilt'] > 0:
            self.send_command('up_left')
        elif self.current_direction['pan'] < 0 and self.current_direction['tilt'] < 0:
            self.send_command('down_left')
        elif self.current_direction['pan'] > 0:
            self.send_command('right')
        elif self.current_direction['pan'] < 0:
            self.send_command('left')
        elif self.current_direction['tilt'] > 0:
            self.send_command('up')
        elif self.current_direction['tilt'] < 0:
            self.send_command('down')
            
        # Restore speed
        self.speed = old_speed
    
    def set_manual_controls_enabled(self, enabled):
        """Enable/disable manual controls during oscillation"""
        controls = [
            self.up_btn, self.down_btn, self.left_btn, self.right_btn,
            self.up_left_btn, self.up_right_btn, self.down_left_btn, 
            self.down_right_btn, self.zoom_in_btn, self.zoom_out_btn,
            self.home_btn, self.pan_self_test_btn, self.tilt_self_test_btn
        ]
        for control in controls:
            control.setEnabled(enabled)
        
        # Always disable speed slider during oscillation
        self.speed_slider.setEnabled(enabled)

    def _send_command_thread(self, command):
        """Send a command in a separate thread to prevent UI blocking"""
        # For protocol-agnostic commands, determine based on command format
        # If it starts with '$' it's a service protocol command
        if isinstance(command, str) and command.startswith('$'):
            # Always use service protocol for commands starting with $
            self._send_command_thread_service_protocol(command)
        elif command == 'home':
            # Use service protocol for home command instead of Pelco-D
            self._send_home_command_service_protocol()
        else:
            # Use traditional Pelco-D command
            self._send_command_thread_pelco_d(command)

    def _send_command_thread_pelco_d(self, command):
        """Send a Pelco-D command in a separate thread to prevent UI blocking"""
        if not self.connected:
            # Only try to reconnect if not already connected
            self._connect_device_thread()
            if not self.connected:
                msg = f"Not connected to Pelco-D device at {self.ip}"
                print(msg)
                self.command_sent_signal.emit(msg)
                return
            
        try:
            # Pelco-D protocol structure:
            # Sync (1 byte) | Address (1 byte) | Command1 (1 byte) | Command2 (1 byte) | Data1 (1 byte) | Data2 (1 byte) | Checksum (1 byte)
            
            address = self.address_spin.value() if hasattr(self, 'address_spin') else 0x01  # Use address from settings
            
            # Initialize command bytes
            command1 = 0x00
            command2 = 0x00
            data1 = self.speed  # Speed for pan (0x00 to 0x3F)
            data2 = self.speed  # Speed for tilt (0x00 to 0x3F)
            
            # Check if tilt inversion is enabled
            invert_tilt = self.invert_tilt_checkbox.isChecked() if hasattr(self, 'invert_tilt_checkbox') else False
            
            # Set command bytes based on direction
            if command == 'up':
                if invert_tilt:
                    command2 = 0x10  # Tilt down (inverted)
                else:
                    command2 = 0x08  # Tilt up
            elif command == 'down':
                if invert_tilt:
                    command2 = 0x08  # Tilt up (inverted)
                else:
                    command2 = 0x10  # Tilt down
            elif command == 'left':
                command2 = 0x04  # Pan left
            elif command == 'right':
                command2 = 0x02  # Pan right
            elif command == 'up_left':
                # Combination of up and left
                if invert_tilt:
                    command2 = 0x10  # Tilt down (inverted)
                else:
                    command2 = 0x08  # Tilt up
                command2 |= 0x04  # Pan left
            elif command == 'up_right':
                # Combination of up and right
                if invert_tilt:
                    command2 = 0x10  # Tilt down (inverted)
                else:
                    command2 = 0x08  # Tilt up
                command2 |= 0x02  # Pan right
            elif command == 'down_left':
                # Combination of down and left
                if invert_tilt:
                    command2 = 0x08  # Tilt up (inverted)
                else:
                    command2 = 0x10  # Tilt down
                command2 |= 0x04  # Pan left
            elif command == 'down_right':
                # Combination of down and right
                if invert_tilt:
                    command2 = 0x08  # Tilt up (inverted)
                else:
                    command2 = 0x10  # Tilt down
                command2 |= 0x02  # Pan right
            elif command == 'stop' or command == 'stop_zoom':
                # All movement bits are 0 for stop
                command1 = 0x00
                command2 = 0x00
                data1 = 0x00
                data2 = 0x00
            elif command == 'home':
                command1 = 0x07  # Goto preset 1
                data1 = 0x01
                data2 = 0x00
            
            # Build packet
            sync_byte = 0xFF
            checksum = (address + command1 + command2 + data1 + data2) & 0xFF
            
            packet = struct.pack('BBBBBBB', sync_byte, address, command1, command2, data1, data2, checksum)
                
            # Send packet
            self.socket.send(packet)
            cmd_msg = f"Sent Pelco-D command: {command} (invert_tilt: {invert_tilt})"
            print(cmd_msg)
            self.command_sent_signal.emit(cmd_msg)
            
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            # Handle connection errors
            error_msg = f"Connection error: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            self.connected = False
            # Update connection status in UI
            QTimer.singleShot(0, lambda: self._update_connection_status_ui(False))
            # Try to reconnect only if the reconnect timer is not already active
            if not (self.reconnect_timer and self.reconnect_timer.isActive()):
                self._connect_device_thread()
        except Exception as e:
            error_msg = f"Error sending command {command}: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
    
    def _send_command_thread_service_protocol(self, command):
        """Send a service protocol command in a separate thread to prevent UI blocking"""
        try:
            # Connect to service protocol if not already connected
            if not self.service_protocol.connected:
                success = self.service_protocol.connect()
                if not success:
                    error_msg = f"Failed to connect to service protocol at {self.ip}:9760"
                    print(error_msg)
                    self.command_sent_signal.emit(error_msg)
                    return
            
            # Send the command directly to service protocol
            response = self.service_protocol._send_command(command)
            if response is not None:
                cmd_msg = f"Sent service protocol command: {command}, received: {response}"
                print(cmd_msg)
                self.command_sent_signal.emit(cmd_msg)
            else:
                error_msg = f"Failed to send service protocol command: {command}"
                print(error_msg)
                self.command_sent_signal.emit(error_msg)
                
        except Exception as e:
            error_msg = f"Error sending service protocol command {command}: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)

    def _send_home_command_service_protocol(self):
        """Send home command using the TechLazer service protocol"""
        try:
            # Connect to service protocol if not already connected
            if not self.service_protocol.connected:
                success = self.service_protocol.connect()
                if not success:
                    error_msg = f"Failed to connect to service protocol at {self.ip}:9760"
                    print(error_msg)
                    self.command_sent_signal.emit(error_msg)
                    return
            
            # Send home command - move to configured home position using service protocol
            pan_success = self.service_protocol.move_to_pan_position(self.home_pan_position, self.home_pan_speed)
            tilt_success = self.service_protocol.move_to_tilt_position(self.home_tilt_position, self.home_tilt_speed)
            
            if pan_success and tilt_success:
                cmd_msg = f"Sent home command via service protocol (moved to {self.home_pan_position}°, {self.home_tilt_position}°)"
                print(cmd_msg)
                self.command_sent_signal.emit(cmd_msg)
            else:
                error_msg = "Failed to move to home position via service protocol"
                print(error_msg)
                self.command_sent_signal.emit(error_msg)
                
        except Exception as e:
            error_msg = f"Error sending home command via service protocol: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
    
    def send_command(self, command):
        """Send a command to the camera (legacy method) - now respects protocol selection"""
        # For protocol-agnostic commands, determine based on command format
        # If it starts with '$' it's a service protocol command
        if isinstance(command, str) and command.startswith('$'):
            # Always use service protocol for commands starting with $
            command_thread = threading.Thread(target=self._send_command_thread_service_protocol, args=(command,), daemon=True)
            command_thread.start()
        elif command == 'home':
            # Use service protocol for home command
            command_thread = threading.Thread(target=self._send_home_command_service_protocol, args=(), daemon=True)
            command_thread.start()
        else:
            # Use traditional Pelco-D command
            command_thread = threading.Thread(target=self._send_command_thread_pelco_d, args=(command,), daemon=True)
            command_thread.start()
    
    def _update_connection_status_ui(self, connected):
        """Update connection status in the UI"""
        self.connected = connected
        if connected:
            self.conn_status_label.setText("Status: Connected")
            self.conn_status_label.setStyleSheet("color: green;")
            self.enable_controls()
        else:
            self.conn_status_label.setText("Status: Disconnected")
            self.conn_status_label.setStyleSheet("color: red;")
            self.disable_controls()
    
    def disable_controls(self):
        """Disable all control buttons"""
        self._disable_controls_ui()
    
    def enable_controls(self):
        """Enable all control buttons"""
        self._enable_controls_ui()
    
    def disable_controls(self):
        """Disable all control buttons"""
        # Use QTimer to safely update UI from another thread
        QTimer.singleShot(0, self._disable_controls_ui)
    
    def _disable_controls_ui(self):
        """Disable buttons if connection failed"""
        controls = [
            self.up_btn, self.down_btn, self.left_btn, self.right_btn,
            self.zoom_in_btn, self.zoom_out_btn, self.stop_btn, self.home_btn
        ]
        for control in controls:
            control.setEnabled(False)
        
        # Update connection status label
        self.conn_status_label.setText("Status: Disconnected")
        self.conn_status_label.setStyleSheet("color: red;")
    
    def enable_controls(self):
        """Enable all control buttons"""
        # Use QTimer to safely update UI from another thread
        QTimer.singleShot(0, self._enable_controls_ui)
    
    def _enable_controls_ui(self):
        """Enable all control buttons (called from main thread)"""
        # Only enable controls if we're connected
        if self.connected:
            controls = [
                self.up_btn, self.down_btn, self.left_btn, self.right_btn,
                self.zoom_in_btn, self.zoom_out_btn, self.stop_btn, self.home_btn,
                self.pan_self_test_btn, self.tilt_self_test_btn
            ]
            for control in controls:
                control.setEnabled(True)
            self.speed_slider.setEnabled(True)
            # Update status label
            self.conn_status_label.setText("Status: Connected")
            self.conn_status_label.setStyleSheet("color: green;")
    
    def update_device_state(self, state_data):
        """Update device state information in the UI"""
        # Use QTimer to safely update UI from another thread
        QTimer.singleShot(0, lambda: self._update_device_state_ui(state_data))
    
    def _update_device_state_ui(self, state_data):
        """Update device state information in the UI (called from main thread)"""
        if 'temperature' in state_data:
            self.temp_value.setText(f"{state_data['temperature']} °C")
        if 'voltage' in state_data:
            self.voltage_value.setText(f"{state_data['voltage']} V")
        if 'pan_state' in state_data:
            self.pan_state_value.setText(state_data['pan_state'])
        if 'tilt_state' in state_data:
            self.tilt_state_value.setText(state_data['tilt_state'])
        if 'pan_position' in state_data:
            self.pan_pos_value.setText(f"{state_data['pan_position']} °")
        if 'tilt_position' in state_data:
            self.tilt_pos_value.setText(f"{state_data['tilt_position']} °")
    
    def closeEvent(self, event):
        """Handle widget closing"""
        self.close_connection()
        event.accept()
    
    def update_connection(self, new_ip, new_port):
        """Update connection with new IP and port, then reconnect"""
        # Store the new connection parameters
        old_ip = self.ip
        old_port = self.port
        self.ip = new_ip
        self.port = new_port
        
        # Update UI to show new connection info
        self.conn_info_label.setText(f"IP: {self.ip}:{self.port}")
        
        # Close existing connection
        self.close_connection()
        
        # Update status message
        msg = f"Connection updated from {old_ip}:{old_port} to {self.ip}:{self.port}, attempting to reconnect..."
        print(msg)
        self.command_sent_signal.emit(msg)
        
        # Establish new connection with new parameters
        self.connect_device()

    # === TechLazer Service Protocol Methods ===
    
    def connect_service_protocol(self):
        """Connect to the TechLazer service protocol on port 9760"""
        try:
            success = self.service_protocol.connect()
            if success:
                self.command_sent_signal.emit(f"Connected to TechLazer service protocol at {self.ip}:9760")
                return True
            else:
                self.command_sent_signal.emit(f"Failed to connect to TechLazer service protocol at {self.ip}:9760")
                return False
        except Exception as e:
            error_msg = f"Error connecting to TechLazer service protocol: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            return False
    
    def get_service_protocol_info(self):
        """Get information from the service protocol"""
        try:
            # Get firmware version
            version = self.service_protocol.get_firmware_version()
            # Get current positions
            pan_pos = self.service_protocol.get_current_pan_position()
            tilt_pos = self.service_protocol.get_current_tilt_position()
            # Get axis states
            pan_state = self.service_protocol.get_pan_axis_state()
            tilt_state = self.service_protocol.get_tilt_axis_state()
            # Get temperatures and voltages
            temp = self.service_protocol.get_current_temperature()
            voltage = self.service_protocol.get_supply_voltage()
            
            # Update UI with this information
            info = {
                'version': version,
                'pan_position': f"{pan_pos:.2f}" if pan_pos is not None else "?",
                'tilt_position': f"{tilt_pos:.2f}" if tilt_pos is not None else "?",
                'pan_state': str(pan_state) if pan_state is not None else "?",
                'tilt_state': str(tilt_state) if tilt_state is not None else "?",
                'temperature': f"{temp:.1f}°C" if temp is not None else "? °C",
                'voltage': f"{voltage:.1f}V" if voltage is not None else "? V"
            }
            
            self.update_device_state(info)
            return info
        except Exception as e:
            error_msg = f"Error getting service protocol info: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            return None
    
    def move_pan_absolute(self, target_pos, max_speed=None):
        """Move pan axis to absolute position using service protocol"""
        if max_speed is None:
            max_speed = 20.0  # Default max speed
            
        try:
            success = self.service_protocol.move_to_pan_position(target_pos, max_speed)
            if success:
                msg = f"Pan moved to {target_pos}° with max speed {max_speed}°/s"
                self.command_sent_signal.emit(msg)
                return True
            else:
                self.command_sent_signal.emit("Failed to move pan axis")
                return False
        except Exception as e:
            error_msg = f"Error moving pan axis: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            return False
    
    def move_tilt_absolute(self, target_pos, max_speed=None):
        """Move tilt axis to absolute position using service protocol"""
        if max_speed is None:
            max_speed = 10.0  # Default max speed
            
        try:
            success = self.service_protocol.move_to_tilt_position(target_pos, max_speed)
            if success:
                msg = f"Tilt moved to {target_pos}° with max speed {max_speed}°/s"
                self.command_sent_signal.emit(msg)
                return True
            else:
                self.command_sent_signal.emit("Failed to move tilt axis")
                return False
        except Exception as e:
            error_msg = f"Error moving tilt axis: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            return False
    
    def move_to_home_service_protocol(self):
        """Public method to move to home position using service protocol"""
        self._send_home_command_service_protocol()
        
    def get_current_positions_service_protocol(self):
        """Get current pan and tilt positions using service protocol"""
        try:
            pan_pos = self.service_protocol.get_current_pan_position()
            tilt_pos = self.service_protocol.get_current_tilt_position()
            return pan_pos, tilt_pos
        except Exception as e:
            print(f"Error getting current positions from service protocol: {str(e)}")
            return None, None
    
    def start_pan_self_test_service_protocol(self):
        """Start pan axis self-test using service protocol"""
        try:
            # Connect to service protocol if not already connected
            if not self.service_protocol.connected:
                success = self.service_protocol.connect()
                if not success:
                    error_msg = f"Failed to connect to service protocol at {self.ip}:9760"
                    print(error_msg)
                    self.command_sent_signal.emit(error_msg)
                    return False
            
            # Send pan self-test command
            response = self.service_protocol.start_pan_self_test()
            
            if response:
                cmd_msg = "Started pan axis self-test via service protocol"
                print(cmd_msg)
                self.command_sent_signal.emit(cmd_msg)
                return True
            else:
                error_msg = "Failed to start pan axis self-test via service protocol"
                print(error_msg)
                self.command_sent_signal.emit(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Error starting pan axis self-test via service protocol: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            return False
    
    def start_tilt_self_test_service_protocol(self):
        """Start tilt axis self-test using service protocol"""
        try:
            # Connect to service protocol if not already connected
            if not self.service_protocol.connected:
                success = self.service_protocol.connect()
                if not success:
                    error_msg = f"Failed to connect to service protocol at {self.ip}:9760"
                    print(error_msg)
                    self.command_sent_signal.emit(error_msg)
                    return False
            
            # Send tilt self-test command
            response = self.service_protocol.start_tilt_self_test()
            
            if response:
                cmd_msg = "Started tilt axis self-test via service protocol"
                print(cmd_msg)
                self.command_sent_signal.emit(cmd_msg)
                return True
            else:
                error_msg = "Failed to start tilt axis self-test via service protocol"
                print(error_msg)
                self.command_sent_signal.emit(error_msg)
                return False
                
        except Exception as e:
            error_msg = f"Error starting tilt axis self-test via service protocol: {str(e)}"
            print(error_msg)
            self.command_sent_signal.emit(error_msg)
            return False

    def get_axis_states_service_protocol(self):
        """Get current states of pan and tilt axes using service protocol"""
        try:
            pan_state = self.service_protocol.get_pan_axis_state()
            tilt_state = self.service_protocol.get_tilt_axis_state()
            return pan_state, tilt_state
        except Exception as e:
            print(f"Error getting axis states from service protocol: {str(e)}")
            return None, None
    
    def get_fault_flags_service_protocol(self):
        """Get fault flags for pan and tilt axes using service protocol"""
        try:
            pan_faults = self.service_protocol.get_pan_fault_flags()
            tilt_faults = self.service_protocol.get_tilt_fault_flags()
            return pan_faults, tilt_faults
        except Exception as e:
            print(f"Error getting fault flags from service protocol: {str(e)}")
            return None, None

