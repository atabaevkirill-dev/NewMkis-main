import sys
import serial
import threading
import time
import socket
import configparser
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QComboBox, QTextEdit, QMessageBox, QGroupBox, QSpinBox, 
                             QGridLayout, QMenuBar, QStatusBar, QLineEdit, QFrame, QProgressBar)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette
import struct
import os
import sys

# Добавляем путь к rlf, если он еще не добавлен
rlf_path = os.path.join(os.path.dirname(__file__), '..')
if rlf_path not in sys.path:
    sys.path.insert(0, rlf_path)

from rlf.protocol_handler import ProtocolHandler


class RangefinderWidget(QWidget):
    # Custom signal for updating UI from thread
    update_signal = pyqtSignal(str, str)
    log_signal = pyqtSignal(str)
    update_multi_signal = pyqtSignal(dict)  # dict - {target_num: {distance, status_desc}}
    
    def __init__(self):
        super().__init__()
        
        # Установка тёмной темы
        self.setup_dark_theme()
        
        self.serial_conn = None
        self.tcp_socket = None
        self.protocol_handler = None
        self.is_connected = False
        self.is_ranging = False
        self.ranging_thread = None
        self.connection_type = "serial"  # Default to serial
        self.multi_targets_data = {}  # Хранение данных для многократных целей
        
        # Load configuration
        self.config = configparser.ConfigParser()
        try:
            self.config.read('rlf/config.ini')
        except:
            # Если файл не найден, создаем базовую конфигурацию
            self.config.add_section('LASER_RANGING')
            self.config.set('LASER_RANGING', 'tcp_ip_address', '192.168.1.7')
            self.config.set('LASER_RANGING', 'tcp_port', '20108')
            self.config.set('LASER_RANGING', 'connection_type', 'serial')
            self.config.set('LASER_RANGING', 'default_port', 'COM1')
            self.config.set('LASER_RANGING', 'default_baud', '115200')
            self.config.set('LASER_RANGING', 'default_mode', 'single')
            self.config.set('LASER_RANGING', 'default_target', 'first')
            self.config.set('LASER_RANGING', 'default_frequency', '1')
            self.config.set('LASER_RANGING', 'min_gating_distance', '15')
            self.config.set('LASER_RANGING', 'max_gating_distance', '4200')
            
            self.config.add_section('UI_SETTINGS')
            self.config.set('UI_SETTINGS', 'window_width', '1000')
            self.config.set('UI_SETTINGS', 'window_height', '700')
            self.config.set('UI_SETTINGS', 'window_x', '100')
            self.config.set('UI_SETTINGS', 'window_y', '100')
            self.config.set('UI_SETTINGS', 'font_family', 'Arial')
            self.config.set('UI_SETTINGS', 'font_size', '12')

        self.init_ui()
        self.update_connection_status()
        
        # Connect the custom signals to the slots
        self.update_signal.connect(self.update_display)
        self.log_signal.connect(self.log_message)
        self.update_multi_signal.connect(self.handle_multi_targets)
        
        # Log current configuration
        self.log_message(f"Configuration loaded - Connection: {self.config.get('LASER_RANGING', 'connection_type', fallback='serial')}, "
                         f"Port: {self.config.get('LASER_RANGING', 'default_port', fallback='COM1')}, "
                         f"Baud: {self.config.get('LASER_RANGING', 'default_baud', fallback='115200')}")
    
    def setup_dark_theme(self):
        """Настройка тёмной темы для приложения"""
        dark_style = """
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            font-family: "Segoe UI", Arial, sans-serif;
        }
        
        QGroupBox {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            border-radius: 6px;
            margin-top: 1ex;
            padding: 10px;
            font-weight: bold;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0px 5px 0px 5px;
            color: #ffffff;
        }
        
        QLabel {
            color: #ffffff;
            background-color: transparent;
        }
        
        QPushButton {
            background-color: #4a4a4a;
            border: 1px solid #666666;
            padding: 6px 12px;
            border-radius: 4px;
            min-width: 60px;
            color: white;
        }
        
        QPushButton:hover {
            background-color: #5a5a5a;
            border: 1px solid #777777;
        }
        
        QPushButton:pressed {
            background-color: #3a3a3a;
            border: 1px solid #555555;
        }
        
        QPushButton:disabled {
            background-color: #333333;
            color: #777777;
            border: 1px solid #444444;
        }
        
        QComboBox {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            padding: 5px;
            color: #ffffff;
        }
        
        QComboBox:focus {
            border: 1px solid #777777;
        }
        
        QSpinBox {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            color: #ffffff;
            padding: 5px;
        }
        
        QSpinBox:focus {
            border: 1px solid #777777;
        }
        
        QTextEdit {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            color: #ffffff;
        }
        
        QLineEdit {
            background-color: #3c3c3c;
            border: 1px solid #555555;
            color: #ffffff;
            padding: 5px;
        }
        
        QMenuBar {
            background-color: #3c3c3c;
            color: #ffffff;
        }
        
        QMenuBar::item {
            background: transparent;
        }
        
        QMenuBar::item:selected {
            background: #555555;
        }
        
        QStatusBar {
            background-color: #3c3c3c;
            color: #ffffff;
        }
        
        QProgressBar {
            border: 1px solid #6a6a6a;
            text-align: center;
            color: white;
            background-color: #2a2a2a;
        }
        
        QProgressBar::chunk {
            background-color: #4a90d9;
            width: 10px;
        }
        """
        
        self.setStyleSheet(dark_style)
    
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("3km Eye-Safe Laser Rangefinder Module")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("""
            QLabel {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(title_label)
        
        # Connection group box
        connection_group = QGroupBox("Connection Settings")
        connection_layout = QGridLayout(connection_group)
        
        # Connection type selection
        conn_type_label = QLabel("Connection Type:")
        self.conn_type_combo = QComboBox()
        self.conn_type_combo.addItems(["Serial", "TCP/IP"])
        self.conn_type_combo.currentTextChanged.connect(self.change_connection_type)
        self.conn_type_combo.setMinimumWidth(120)
        self.conn_type_combo.setMaximumWidth(150)
        
        # Add items to grid
        connection_layout.addWidget(conn_type_label, 0, 0)
        connection_layout.addWidget(self.conn_type_combo, 0, 1)
        
        # Serial Port selection
        self.serial_port_widget = QWidget()  # Wrapper widget for serial port layout
        serial_port_layout = QGridLayout()
        serial_port_label = QLabel("Serial Port:")
        self.port_combo = QComboBox()
        self.refresh_ports()
        self.port_combo.setMinimumWidth(120)
        self.port_combo.setMaximumWidth(150)
        serial_port_layout.addWidget(serial_port_label, 0, 0)  # Строка 0, колонка 0
        serial_port_layout.addWidget(self.port_combo, 0, 1)    # Строка 0, колонка 1
        
        # Refresh ports button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.refresh_btn.setMinimumSize(80, 25)
        serial_port_layout.addWidget(self.refresh_btn, 0, 2)
        
        self.serial_port_widget.setLayout(serial_port_layout)
        
        # TCP IP and Port fields
        self.tcp_fields_widget = QWidget()  # Wrapper widget for TCP fields layout
        tcp_fields_layout = QGridLayout()
        tcp_ip_label = QLabel("TCP IP Address:")
        self.tcp_ip_input = QLineEdit(self.config.get('LASER_RANGING', 'tcp_ip_address', fallback='192.168.1.7'))
        self.tcp_ip_input.setMinimumWidth(120)
        self.tcp_ip_input.setMaximumWidth(150)
        tcp_port_label = QLabel("TCP Port:")
        self.tcp_port_input = QLineEdit(self.config.get('LASER_RANGING', 'tcp_port', fallback='20108'))
        self.tcp_port_input.setMinimumWidth(120)
        self.tcp_port_input.setMaximumWidth(150)
        tcp_fields_layout.addWidget(tcp_ip_label, 0, 0)
        tcp_fields_layout.addWidget(self.tcp_ip_input, 0, 1)
        tcp_fields_layout.addWidget(tcp_port_label, 1, 0)
        tcp_fields_layout.addWidget(self.tcp_port_input, 1, 1)
        self.tcp_fields_widget.setLayout(tcp_fields_layout)
        
        # Baudrate selection (only for serial)
        self.baud_widget = QWidget()  # Wrapper widget for baud layout
        baud_layout = QGridLayout()
        baud_label = QLabel("Baud Rate:")
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "57600", "115200"])
        self.baud_combo.setCurrentText(self.config.get('LASER_RANGING', 'default_baud', fallback='115200'))  # Default
        self.baud_combo.setMinimumWidth(120)
        self.baud_combo.setMaximumWidth(150)
        baud_layout.addWidget(baud_label, 0, 0)
        baud_layout.addWidget(self.baud_combo, 0, 1)
        self.baud_widget.setLayout(baud_layout)
        
        # Initially show serial fields and set default connection type
        conn_type_default = self.config.get('LASER_RANGING', 'connection_type', fallback='serial')
        self.conn_type_combo.setCurrentText(conn_type_default.title())  # title() capitalizes first letter
        self.change_connection_type(conn_type_default.title())
        
        # Connection button
        self.conn_btn = QPushButton("Connect")
        self.conn_btn.clicked.connect(self.toggle_connection)
        self.conn_btn.setMinimumSize(100, 25)
        
        # Place items in grid
        connection_layout.addWidget(self.serial_port_widget, 1, 0, 1, 2)  # Spans 2 columns
        connection_layout.addWidget(self.tcp_fields_widget, 2, 0, 2, 2)   # Spans 2 rows and 2 columns
        connection_layout.addWidget(self.baud_widget, 4, 0, 1, 2)         # Spans 2 columns
        connection_layout.addWidget(self.conn_btn, 5, 0, 1, 2)            # Spans 2 columns
        
        main_layout.addWidget(connection_group)
        
        # Ranging controls
        ranging_group = QGroupBox("Ranging Controls")
        ranging_layout = QGridLayout(ranging_group)
        
        # Ranging mode
        mode_label = QLabel("Ranging Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single", "Continuous", "Stop"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.mode_combo.setMinimumWidth(100)
        self.mode_combo.setMaximumWidth(120)
        
        # Target selection
        target_label = QLabel("Target:")
        self.target_combo = QComboBox()
        self.target_combo.addItems(["First", "Last", "Multi"])
        self.target_combo.setMinimumWidth(100)
        self.target_combo.setMaximumWidth(120)
        # Подключаем сигнал для обновления режима цели
        self.target_combo.currentTextChanged.connect(self.on_target_changed)
        
        # Frequency control
        freq_label = QLabel("Freq (Hz):")
        self.freq_spin = QSpinBox()
        self.freq_spin.setRange(1, 10)
        self.freq_spin.setValue(int(self.config.get('LASER_RANGING', 'default_frequency', fallback='1')))
        self.freq_spin.setMinimumWidth(80)
        self.freq_spin.setMaximumWidth(100)
        
        # Range settings
        min_range_label = QLabel("Min (m):")
        self.min_range_spin = QSpinBox()
        self.min_range_spin.setRange(15, 20000)
        self.min_range_spin.setValue(int(self.config.get('LASER_RANGING', 'min_gating_distance', fallback='15')))
        self.min_range_spin.setMinimumWidth(80)
        self.min_range_spin.setMaximumWidth(100)
        
        max_range_label = QLabel("Max (m):")
        self.max_range_spin = QSpinBox()
        self.max_range_spin.setRange(100, 20000)
        self.max_range_spin.setValue(int(self.config.get('LASER_RANGING', 'max_gating_distance', fallback='4200')))
        self.max_range_spin.setMinimumWidth(80)
        self.max_range_spin.setMaximumWidth(100)
        
        # Apply range settings button
        self.apply_range_btn = QPushButton("Apply Range")
        self.apply_range_btn.clicked.connect(self.apply_range_settings)
        self.apply_range_btn.setEnabled(False)
        self.apply_range_btn.setMinimumSize(100, 25)
        
        # Toggle ranging button (moved lower as requested)
        self.range_btn = QPushButton("Start Ranging")
        self.range_btn.clicked.connect(self.toggle_ranging)
        self.range_btn.setEnabled(False)
        self.range_btn.setMinimumSize(100, 25)
        
        # Add controls to layout
        ranging_layout.addWidget(mode_label, 0, 0)
        ranging_layout.addWidget(self.mode_combo, 0, 1)
        ranging_layout.addWidget(target_label, 0, 2)
        ranging_layout.addWidget(self.target_combo, 0, 3)
        ranging_layout.addWidget(freq_label, 1, 0)
        ranging_layout.addWidget(self.freq_spin, 1, 1)
        ranging_layout.addWidget(min_range_label, 1, 2)
        ranging_layout.addWidget(self.min_range_spin, 1, 3)
        ranging_layout.addWidget(max_range_label, 2, 0)
        ranging_layout.addWidget(self.max_range_spin, 2, 1)
        ranging_layout.addWidget(self.apply_range_btn, 2, 2, 1, 2)  # Spanning 2 columns
        ranging_layout.addWidget(self.range_btn, 3, 0, 1, 4)  # Spanning 4 columns and positioned lower
        
        main_layout.addWidget(ranging_group)
        
        # Results display
        results_group = QGroupBox("Measurement Results")
        results_layout = QVBoxLayout(results_group)
        
        self.distance_label = QLabel("Distance: -- m")
        self.distance_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.distance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.distance_label.setStyleSheet("""
            QLabel {
                background-color: #3c3c3c; 
                padding: 8px; 
                font-size: 18px; 
                font-weight: bold;
                border-radius: 4px;
                color: white;
            }
        """)
        results_layout.addWidget(self.distance_label)
        
        # Multi-target display
        self.multi_targets_label = QLabel("Multi-targets: --")
        self.multi_targets_label.setFont(QFont("Arial", 12, QFont.Weight.Normal))
        self.multi_targets_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.multi_targets_label.setStyleSheet("""
            QLabel {
                background-color: #2d4d6b; 
                padding: 4px;
                border-radius: 2px;
                color: white;
            }
        """)
        self.multi_targets_label.setVisible(False)  # Initially hidden
        results_layout.addWidget(self.multi_targets_label)
        
        self.results_display = QTextEdit()
        self.results_display.setMaximumHeight(120)
        self.results_display.setReadOnly(True)
        self.results_display.setStyleSheet("""
            QTextEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                color: #ffffff;
                padding: 4px;
            }
        """)
        results_layout.addWidget(self.results_display)
        
        main_layout.addWidget(results_group)
        
        # Progress bar for ranging activity
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # System info
        info_group = QGroupBox("System Information")
        info_layout = QGridLayout(info_group)
        
        # Version info buttons
        self.fpga_version_btn = QPushButton("FPGA Ver")
        self.fpga_version_btn.clicked.connect(self.query_fpga_version)
        self.fpga_version_btn.setMinimumSize(100, 25)
        self.mcu_version_btn = QPushButton("MCU Ver")
        self.mcu_version_btn.clicked.connect(self.query_mcu_version)
        self.mcu_version_btn.setMinimumSize(100, 25)
        self.hardware_version_btn = QPushButton("HW Ver")
        self.hardware_version_btn.clicked.connect(self.query_hardware_version)
        self.hardware_version_btn.setMinimumSize(100, 25)
        self.sn_btn = QPushButton("SN")
        self.sn_btn.clicked.connect(self.query_serial_number)
        self.sn_btn.setMinimumSize(100, 25)
        
        info_layout.addWidget(self.fpga_version_btn, 0, 0)
        info_layout.addWidget(self.mcu_version_btn, 0, 1)
        info_layout.addWidget(self.hardware_version_btn, 1, 0)
        info_layout.addWidget(self.sn_btn, 1, 1)
        
        main_layout.addWidget(info_group)
        
        # Timer for UI updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)  # Update every second
        
        # Log section
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        
        main_layout.addWidget(log_group)
        
        # Initially hide TCP fields
        self.tcp_fields_widget.hide()
        
    def refresh_ports(self):
        """Refresh available serial ports"""
        import serial.tools.list_ports
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)
    
    def change_connection_type(self, conn_type):
        """Change connection type between serial and TCP"""
        if conn_type.lower() == "serial":
            self.connection_type = "serial"
            self.serial_port_widget.show()
            self.baud_widget.show()
            self.tcp_fields_widget.hide()
        else:
            self.connection_type = "tcp"
            self.serial_port_widget.hide()
            self.baud_widget.hide()
            self.tcp_fields_widget.show()
    
    def toggle_connection(self):
        """Toggle connection to the rangefinder"""
        if not self.is_connected:
            self.connect_to_device()
        else:
            self.disconnect_from_device()
    
    def connect_to_device(self):
        """Connect to the rangefinder device"""
        try:
            if self.connection_type == "serial":
                port = self.port_combo.currentText()
                baud = int(self.baud_combo.currentText())
                
                self.serial_conn = serial.Serial(port, baud, timeout=1)
                self.protocol_handler = ProtocolHandler(self.serial_conn)
                
                # Test connection
                # self.protocol_handler.perform_self_check()  # May not be needed
                
                self.log_message(f"Connected to {port} at {baud} baud")
            else:
                host = self.tcp_ip_input.text()
                port = int(self.tcp_port_input.text())
                
                self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.tcp_socket.settimeout(5)  # 5 second timeout
                self.tcp_socket.connect((host, port))
                
                # Import here to avoid circular imports
                from rlf.tcp_protocol_handler import TcpProtocolHandler
                self.protocol_handler = TcpProtocolHandler(self.tcp_socket)
                
                self.log_message(f"Connected to {host}:{port} via TCP")
            
            self.is_connected = True
            self.update_connection_status()
            self.log_message(f"Connected via {self.connection_type.upper()}")
            
            # Set first/last/multi target mode based on combo selection
            self.set_target_mode()
            
            # Log protocol handler availability
            if self.protocol_handler:
                self.log_message("Protocol handler initialized successfully")
            else:
                self.log_message("ERROR: Protocol handler not initialized")
                
        except ValueError as ve:
            QMessageBox.critical(self, "Invalid Input", f"Invalid input value: {str(ve)}")
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Could not connect: {str(e)}")
            if self.tcp_socket:
                try:
                    self.tcp_socket.close()
                except:
                    pass
                self.tcp_socket = None
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
    
    def disconnect_from_device(self):
        """Disconnect from the rangefinder device"""
        if self.is_ranging:
            self.stop_ranging()
            
        if self.connection_type == "serial" and self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        elif self.connection_type == "tcp/ip" and self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        
        self.serial_conn = None
        self.tcp_socket = None
        self.protocol_handler = None
        self.is_connected = False
        self.is_ranging = False
        self.update_connection_status()
        self.log_message("Disconnected from device")
    
    def update_connection_status(self):
        """Update the UI based on connection status"""
        if self.is_connected:
            self.conn_btn.setText("Disconnect")
            self.range_btn.setEnabled(True)
            self.apply_range_btn.setEnabled(True)
            self.fpga_version_btn.setEnabled(True)
            self.mcu_version_btn.setEnabled(True)
            self.hardware_version_btn.setEnabled(True)
            self.sn_btn.setEnabled(True)
        else:
            self.conn_btn.setText("Connect")
            self.range_btn.setEnabled(False)
            self.apply_range_btn.setEnabled(False)
            self.fpga_version_btn.setEnabled(False)
            self.mcu_version_btn.setEnabled(False)
            self.hardware_version_btn.setEnabled(False)
            self.sn_btn.setEnabled(False)
    
    def on_mode_changed(self, mode):
        """Handle ranging mode changes"""
        if mode == "Stop Ranging" and self.is_ranging:
            self.stop_ranging()
    
    def toggle_ranging(self):
        """Toggle ranging operation"""
        self.log_signal.emit("Toggle ranging button pressed")
        if not self.is_connected:
            self.log_signal.emit("Device not connected!")
            QMessageBox.warning(self, "Not Connected", "Please connect to the device first.")
            return
        
        # Проверяем, действительно ли протокол-обработчик может выполнять измерения
        if self.protocol_handler is None:
            self.log_signal.emit("Protocol handler not initialized!")
            QMessageBox.critical(self, "Error", "Protocol handler not initialized. Please reconnect.")
            return

        if self.is_ranging:
            self.stop_ranging()
        else:
            self.start_ranging()
    
    def start_ranging(self):
        """Start ranging operation"""
        self.log_signal.emit("Start ranging called")
        if not self.is_connected:
            self.log_signal.emit("Device not connected!")
            QMessageBox.warning(self, "Not Connected", "Please connect to the device first.")
            return
        
        mode = self.mode_combo.currentText()
        self.log_signal.emit(f"Selected mode: {mode}")
        
        if mode == "Single Ranging":
            self.log_signal.emit("Sending single ranging command")
            self.send_single_ranging_command()
            # For single ranging, we don't stay in ranging mode
            self.is_ranging = False
            self.update_ranging_button()
        elif mode == "Continuous Ranging":
            self.log_signal.emit("Starting continuous ranging")
            self.start_continuous_ranging()
        elif mode == "Stop Ranging":
            self.log_signal.emit("Stop mode selected")
            self.stop_ranging()
    
    def start_continuous_ranging(self):
        """Start continuous ranging in a separate thread"""
        self.log_signal.emit("Start continuous ranging method called")
        if not self.is_connected:
            self.log_signal.emit("Device not connected!")
            QMessageBox.warning(self, "Not Connected", "Please connect to the device first.")
            return

        # Check if connection is active
        if not self.is_connected:
            self.log_signal.emit("Device not connected!")
            QMessageBox.warning(self, "Not Connected", "Please connect to the device first.")
            return

        # Set ranging frequency
        self.set_ranging_frequency()
        
        # Ensure target mode is properly set
        self.set_target_mode()
        
        self.is_ranging = True
        self.update_ranging_button()
        self.progress_bar.setVisible(True)
        
        # Start ranging in a separate thread
        self.log_signal.emit("Starting ranging thread")
        self.ranging_thread = threading.Thread(target=self.continuous_ranging_worker, daemon=True)
        self.ranging_thread.start()
    
    def continuous_ranging_worker(self):
        """Worker function for continuous ranging"""
        if self.protocol_handler:
            self.protocol_handler.start_continuous_ranging()
        
        # Error counter to prevent endless attempts
        error_count = 0
        max_errors = 5
        
        while self.is_ranging:
            # Check if connection is active
            if not self.is_connected:
                self.log_signal.emit("Connection lost, stopping ranging...")
                break
                
            try:
                # In continuous mode, we just wait for responses
                if self.protocol_handler:
                    # Process any incoming responses
                    response = self.protocol_handler.read_response(timeout=0.05)  # Reduced timeout
                    if response:
                        self.log_signal.emit(f"Received raw response: {' '.join([f'{byte:02X}' for byte in response])}")
                        parsed = self.protocol_handler._parse_response(response)
                        if parsed:
                            self.log_signal.emit(f"Parsed response: cmd=0x{parsed['command_code']:02X}, params=[{', '.join([f'{p:02X}' for p in parsed['params']])}], device_code=0x{parsed['device_code']:02X}")
                            
                        if parsed and parsed['command_code'] in [0x04, 0x06]:  # Continuous ranging or error
                            if parsed['command_code'] == 0x04 and len(parsed['params']) == 4:  # Valid ranging response
                                status, dist_high, dist_low, dist_decimal = parsed['params']
                                
                                # Calculate distance
                                distance = dist_high * 256 + dist_low + dist_decimal * 0.1
                                
                                # Decode status
                                status_desc, is_multi_target = self.protocol_handler._decode_ranging_status_extended(status)
                                
                                # Debug logging
                                self.log_signal.emit(f"Raw data: status={status:02X}, dist_high={dist_high}, dist_low={dist_low}, dist_decimal={dist_decimal}")
                                self.log_signal.emit(f"Calculated distance: {distance:.1f}m, Status: {status_desc}")
                                
                                # Check if distance is valid (not out of range)
                                if "out of range" in status_desc.lower():
                                    self.update_signal.emit("--", status_desc)
                                else:
                                    # For multi-target mode, store all targets until we get all of them
                                    if is_multi_target:
                                        # Extract target number (upper 4 bits of status)
                                        target_num = (status >> 4) & 0x0F
                                        
                                        # Store the target data
                                        self.multi_targets_data[target_num] = {
                                            'distance': distance,
                                            'status_desc': status_desc
                                        }
                                        
                                        # Emit signal to update UI from main thread
                                        self.update_multi_signal.emit(self.multi_targets_data.copy())
                                    else:
                                        # Single target - clear multi-target data and hide label
                                        self.multi_targets_data.clear()
                                        self.update_multi_signal.emit({})  # Hide multi-target label
                                        
                                        # Emit signal to update UI from main thread
                                        self.update_signal.emit(f"{distance:.1f}", status_desc)
                            elif parsed['command_code'] == 0x06:  # Ranging abnormal
                                # Send special signal indicating abnormal ranging
                                self.update_signal.emit("--", "Ranging Abnormal")
                                self.log_signal.emit("Ranging abnormal detected")
                    else:
                        # Log if no response was received
                        self.log_signal.emit("No response received from device")
                # Reset error counter on successful iteration
                error_count = 0
                
                # Small pause to avoid overloading CPU
                time.sleep(0.01)
                
            except Exception as e:
                error_msg = str(e)
                # Check if error is timeout or connection issue
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    # Log timeout but don't stop ranging
                    self.log_signal.emit("Communication timeout, continuing...")
                    error_count += 1
                elif "invalid header" in error_msg.lower() or "connection" in error_msg.lower():
                    # Protocol or connection errors
                    self.log_signal.emit(f"Communication error: {error_msg}")
                    error_count += 1
                else:
                    self.log_signal.emit(f"Error during continuous ranging: {str(e)}")
                    error_count += 1
                
                # Stop ranging when max errors reached
                if error_count >= max_errors:
                    self.log_signal.emit("Too many errors, stopping ranging...")
                    break
    
    def stop_ranging(self):
        """Stop ranging operation"""
        if self.is_connected and self.protocol_handler:
            try:
                self.protocol_handler.stop_ranging()
            except Exception as e:
                self.log_message(f"Error stopping ranging: {str(e)}")
        
        self.is_ranging = False
        self.progress_bar.setVisible(False)
        
        if self.ranging_thread and self.ranging_thread.is_alive():
            self.ranging_thread.join(timeout=1)
        
        # Clear multi-target data when stopping
        self.multi_targets_data.clear()
        self.update_multi_signal.emit({})  # Hide multi-target label
        
        self.update_ranging_button()
    
    def update_ranging_button(self):
        """Update the ranging button text based on current state"""
        if self.is_ranging:
            self.range_btn.setText("Stop Ranging")
        else:
            self.range_btn.setText("Start Ranging")
    
    def format_multi_targets_display(self, multi_targets_data=None):
        """Format the display string for multi-target results"""
        if multi_targets_data is None:
            multi_targets_data = self.multi_targets_data
            
        if not multi_targets_data:
            return "--"
        
        # Sort targets by key (target number) and format them
        sorted_targets = sorted(multi_targets_data.items())
        target_strings = []
        
        for target_num, data in sorted_targets:
            target_strings.append(f"#{target_num}: {data['distance']:.1f}m")
        
        return ", ".join(target_strings)
    
    def handle_multi_targets(self, multi_targets_data):
        """Handle multi-target data updates"""
        try:
            # Update multi-target results display
            if multi_targets_data:
                # Format multi-target display
                multi_targets_str = self.format_multi_targets_display(multi_targets_data)
                
                # Update the multi-target display area if it exists
                if hasattr(self, 'multi_targets_label'):
                    self.multi_targets_label.setText(multi_targets_str)
                    self.multi_targets_label.setVisible(True)
                else:
                    # Create the label if it doesn't exist yet
                    self.multi_targets_label = QLabel(multi_targets_str)
                    self.multi_targets_label.setWordWrap(True)
                    self.multi_targets_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    self.multi_targets_label.setStyleSheet("""
                        QLabel {
                            background-color: #3c3c3c;
                            padding: 10px;
                            border-radius: 5px;
                            color: white;
                        }
                    """)
                    # Add to the layout after the distance label
                    if hasattr(self, 'results_layout'):
                        self.results_layout.addWidget(self.multi_targets_label)
            else:
                # Hide the multi-target display when not in multi-target mode
                if hasattr(self, 'multi_targets_label'):
                    self.multi_targets_label.setVisible(False)
        except Exception as e:
            print(f"Error in handle_multi_targets: {str(e)}")
    
    def send_single_ranging_command(self):
        """Send single ranging command to device"""
        self.log_signal.emit("send_single_ranging_command called")
        if self.protocol_handler:
            self.log_signal.emit("About to call protocol_handler.single_ranging()")
            result = self.protocol_handler.single_ranging()
            self.log_signal.emit(f"Sent single ranging command, result: {result}")
            if result:
                # Debug logging
                self.log_signal.emit(f"Single ranging raw result: {result}")
                
                # Check if it's multi-target mode
                target_mode = self.target_combo.currentText()
                if target_mode == "Multi-target":
                    # In multi-target mode, single ranging might still return one target
                    # But we'll handle it differently if needed
                    status_desc, is_multi_target = self.protocol_handler._decode_ranging_status_extended(result['status'])
                    
                    if is_multi_target:
                        target_num = (result['status'] >> 4) & 0x0F
                        self.multi_targets_data[target_num] = {
                            'distance': result['distance'],
                            'status_desc': status_desc
                        }
                        
                        multi_targets_str = self.format_multi_targets_display()
                        self.update_signal.emit("--", f"Multi-target: {multi_targets_str}")
                        self.update_multi_signal.emit(self.multi_targets_data.copy())
                    else:
                        # Check if distance is out of range
                        if "out of range" in status_desc.lower():
                            self.update_signal.emit("--", status_desc)
                        else:
                            self.update_signal.emit(f"{result['distance']:.1f}", result['status_description'])
                        self.update_multi_signal.emit({})  # Hide multi-target label
                else:
                    # Check if distance is out of range
                    if "out of range" in result['status_description'].lower():
                        self.update_signal.emit("--", result['status_description'])
                    else:
                        self.update_signal.emit(f"{result['distance']:.1f}", result['status_description'])
                    self.update_multi_signal.emit({})  # Hide multi-target label
                    
                self.log_message(f"Single ranging: {result['distance']:.1f}m - {result['status_description']}")
            else:
                self.log_message("Single ranging failed or returned no result")
                self.log_signal.emit("Single ranging returned no result")
                self.update_signal.emit("--", "No result")
        else:
            self.log_signal.emit("Protocol handler is None - cannot send single ranging command")
            self.update_signal.emit("--", "Protocol handler error")
    
    def on_target_changed(self, target):
        """Handle target selection changes"""
        if self.is_connected:
            self.set_target_mode()
    
    def set_target_mode(self):
        """Set the target selection mode (first, last, multi)"""
        if not self.is_connected or not self.protocol_handler:
            return
            
        # Define target modes directly instead of accessing through protocol_handler
        TARGET_FIRST = 0x01
        TARGET_LAST = 0x02
        TARGET_MULTI = 0x03
        
        mode_map = {"First Target": TARGET_FIRST, 
                   "Last Target": TARGET_LAST, 
                   "Multi-target": TARGET_MULTI}
        target_mode = mode_map.get(self.target_combo.currentText(), TARGET_FIRST)
        
        if self.protocol_handler:
            success = self.protocol_handler.set_target_mode(target_mode)
            if success:
                self.log_message(f"Target mode set to: {self.target_combo.currentText()}")
            else:
                self.log_message(f"Failed to set target mode to: {self.target_combo.currentText()}")
    
    def set_ranging_frequency(self):
        """Set the ranging frequency"""
        freq = self.freq_spin.value()
        if self.protocol_handler:
            success = self.protocol_handler.set_ranging_frequency(freq)
            if success:
                self.log_message(f"Ranging frequency set to: {freq}Hz")
            else:
                self.log_message(f"Failed to set ranging frequency to: {freq}Hz")
    
    def apply_range_settings(self):
        """Apply minimum and maximum gating distance settings"""
        try:
            min_dist = self.min_range_spin.value()
            max_dist = self.max_range_spin.value()
            
            success_min = True
            success_max = True
            
            if self.protocol_handler:
                success_min = self.protocol_handler.set_min_gating_distance(min_dist)
                success_max = self.protocol_handler.set_max_gating_distance(max_dist)
            
            if success_min and success_max:
                self.log_message(f"Range settings applied: Min={min_dist}m, Max={max_dist}m")
            else:
                self.log_message(f"Failed to apply range settings: Min={min_dist}m, Max={max_dist}m")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Range", f"Invalid range value: {str(e)}")
    
    def query_fpga_version(self):
        """Query FPGA software version"""
        if self.protocol_handler:
            result = self.protocol_handler.query_fpga_version()
            if result:
                version_str = f"FPGA Version: {result['version']}, Date: {result['year']}-{result['month']:02d}-{result['date']:02d}, Author: {result['author']}"
                self.log_message(version_str)
            else:
                self.log_message("Failed to query FPGA version")
    
    def query_mcu_version(self):
        """Query MCU software version"""
        if self.protocol_handler:
            result = self.protocol_handler.query_mcu_version()
            if result:
                version_str = f"MCU Version: {result['version']}, Date: {result['year']}-{result['month']:02d}-{result['date']:02d}, Author: {result['author']}"
                self.log_message(version_str)
            else:
                self.log_message("Failed to query MCU version")
    
    def query_hardware_version(self):
        """Query hardware version"""
        if self.protocol_handler:
            result = self.protocol_handler.query_hardware_version()
            if result:
                version_str = f"Hardware Versions - MB: {result['motherboard']}, CT: {result['control_board']}, APD: {result['detection_board']}, LD: {result['driver_board']}"
                self.log_message(version_str)
            else:
                self.log_message("Failed to query hardware version")
    
    def query_serial_number(self):
        """Query serial number"""
        if self.protocol_handler:
            result = self.protocol_handler.query_sn_number()
            if result:
                sn_str = f"Serial Number: {result['serial_number']} (Manufactured: {result['year']}-{result['month']:02})"
                self.log_message(sn_str)
            else:
                self.log_message("Failed to query serial number")
    
    def update_display(self, distance, status_desc):
        """Update the display with new measurement"""
        try:
            if distance != "--":
                self.distance_label.setText(f"Distance: {distance} m")
                # If distance is in valid range, show green background
                self.distance_label.setStyleSheet("""
                    QLabel {
                        background-color: #2d6b45; 
                        padding: 10px; 
                        font-size: 24px; 
                        font-weight: bold;
                        border-radius: 5px;
                        color: white;
                    }
                """)
            else:
                # If status indicates "out of range", show orange background
                if "out of range" in status_desc.lower() or "abnormal" in status_desc.lower():
                    self.distance_label.setText(f"Status: {status_desc}")
                    self.distance_label.setStyleSheet("""
                        QLabel {
                            background-color: #FF8C00; 
                            padding: 10px; 
                            font-size: 24px; 
                            font-weight: bold;
                            border-radius: 5px;
                            color: white;
                        }
                    """)
                else:
                    # For other statuses, show the status message
                    self.distance_label.setText(f"Status: {status_desc}")
                    # For multi-targets or other cases where no specific distance is available
                    self.distance_label.setStyleSheet("""
                        QLabel {
                            background-color: #3c3c3c; 
                            padding: 10px; 
                            font-size: 24px; 
                            font-weight: bold;
                            border-radius: 5px;
                            color: white;
                        }
                    """)
        except Exception as e:
            print(f"Error in update_display: {str(e)}")
    
    def log_message(self, message):
        """Log a message to the status text"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_display.append(f"[{timestamp}] {message}")
    
    def update_ui(self):
        """Periodic UI updates"""
        # Update progress bar for continuous ranging
        if self.is_ranging:
            self.progress_bar.setValue((self.progress_bar.value() + 5) % 100)
    
    def closeEvent(self, event):
        """Handle cleanup when closing the widget"""
        # Stop ranging operations
        if self.is_ranging:
            self.stop_ranging()
        
        # Disconnect from device
        if self.is_connected:
            self.disconnect_from_device()
        
        # Wait a bit for threads to finish
        if self.ranging_thread and self.ranging_thread.is_alive():
            self.ranging_thread.join(timeout=2)
        
        event.accept()