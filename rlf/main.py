import sys
import serial
import threading
import time
import socket
import configparser
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTextEdit, QMessageBox, QGroupBox, QSpinBox, QGridLayout, QProgressBar, QMenuBar, QAction, QStatusBar, QLineEdit
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette
import struct
from protocol_handler import ProtocolHandler


class LaserRangefinderApp(QMainWindow):
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
        self.config.read('config.ini')
        
        self.init_ui()
        self.update_connection_status()
        
        # Connect the custom signals to the slots
        self.update_signal.connect(self.update_display)
        self.log_signal.connect(self.log_message)
        self.update_multi_signal.connect(self.handle_multi_targets)
    
    def setup_dark_theme(self):
        """Настройка тёмной темы для приложения"""
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
        dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
        dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
        
        self.setPalette(dark_palette)
        
        # Применение стиля к приложению
        dark_style = """
        QMainWindow, QWidget, QGroupBox {
            background-color: #353535;
            color: #ffffff;
        }
        
        QLabel {
            color: #ffffff;
            background-color: transparent;
        }
        
        QPushButton {
            background-color: #4a4a4a;
            border: 1px solid #6a6a6a;
            padding: 5px;
            border-radius: 3px;
            color: #ffffff;
        }
        
        QPushButton:hover {
            background-color: #5a5a5a;
        }
        
        QPushButton:pressed {
            background-color: #3a3a3a;
        }
        
        QPushButton:disabled {
            background-color: #2a2a2a;
            color: #6a6a6a;
        }
        
        QComboBox {
            background-color: #2a2a2a;
            border: 1px solid #6a6a6a;
            padding: 3px;
            color: #ffffff;
        }
        
        QComboBox:focus {
            border: 1px solid #4a90d9;
        }
        
        QSpinBox {
            background-color: #2a2a2a;
            border: 1px solid #6a6a6a;
            color: #ffffff;
            padding: 3px;
        }
        
        QSpinBox:focus {
            border: 1px solid #4a90d9;
        }
        
        QTextEdit {
            background-color: #252525;
            border: 1px solid #6a6a6a;
            color: #ffffff;
        }
        
        QLineEdit {
            background-color: #2a2a2a;
            border: 1px solid #6a6a6a;
            color: #ffffff;
            padding: 3px;
        }
        
        QMenuBar {
            background-color: #353535;
            color: #ffffff;
        }
        
        QMenuBar::item {
            background: transparent;
        }
        
        QMenuBar::item:selected {
            background: #4a4a4a;
        }
        
        QStatusBar {
            background-color: #353535;
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
        # Чтение размеров и позиции окна из конфигурации
        width = self.config.getint('UI_SETTINGS', 'window_width', fallback=1000)
        height = self.config.getint('UI_SETTINGS', 'window_height', fallback=700)
        x = self.config.getint('UI_SETTINGS', 'window_x', fallback=100)
        y = self.config.getint('UI_SETTINGS', 'window_y', fallback=100)
        
        self.setWindowTitle("Laser Rangefinder Desktop Application")
        self.setGeometry(x, y, width, height)
        
        # Create menu bar
        menubar = QMenuBar()
        self.setMenuBar(menubar)
        
        # File menu
        file_menu = menubar.addMenu('File')
        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Disconnected")
        
        # Main central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # # Title
        # title_label = QLabel("3km Eye-Safe Laser Rangefinder Module")
        # title_label.setAlignment(Qt.AlignCenter)
        # title_label.setFont(QFont("Arial", 16, QFont.Bold))
        # title_label.setStyleSheet("""
        #     QLabel {
        #         background-color: #2a2a2a;
        #         color: #ffffff;
        #         padding: 10px;
        #         border-radius: 5px;
        #         font-weight: bold;
        #     }
        # """)
        # main_layout.addWidget(title_label)
        
        # Connection group box
        connection_group = QGroupBox("Connection Settings")
        connection_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #6a6a6a;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
                color: white;
                background-color: #353535;
            }
        """)
        connection_layout = QGridLayout(connection_group)  # Changed to QGridLayout
        
        # Connection type selection
        conn_type_label = QLabel("Connection Type:")
        self.conn_type_combo = QComboBox()
        self.conn_type_combo.addItems(["Serial", "TCP/IP"])
        self.conn_type_combo.currentTextChanged.connect(self.change_connection_type)
        self.conn_type_combo.setMinimumWidth(150)
        self.conn_type_combo.setMaximumWidth(200)
        
        # Add items to grid
        connection_layout.addWidget(conn_type_label, 0, 0)
        connection_layout.addWidget(self.conn_type_combo, 0, 1)
        
        # Serial Port selection
        self.serial_port_widget = QWidget()  # Wrapper widget for serial port layout
        serial_port_layout = QGridLayout()  # Изменили на QGridLayout
        serial_port_label = QLabel("Serial Port:")
        self.port_combo = QComboBox()
        self.refresh_ports()
        self.port_combo.setMinimumWidth(150)
        self.port_combo.setMaximumWidth(200)
        serial_port_layout.addWidget(serial_port_label, 0, 0)  # Строка 0, колонка 0
        serial_port_layout.addWidget(self.port_combo, 0, 1)    # Строка 0, колонка 1
        self.serial_port_widget.setLayout(serial_port_layout)
        
        # TCP IP and Port fields
        self.tcp_fields_widget = QWidget()  # Wrapper widget for TCP fields layout
        tcp_fields_layout = QGridLayout()
        tcp_ip_label = QLabel("TCP IP Address:")
        self.tcp_ip_input = QLineEdit(self.config.get('LASER_RANGING', 'tcp_ip_address', fallback='192.168.1.7'))
        self.tcp_ip_input.setMinimumWidth(150)
        self.tcp_ip_input.setMaximumWidth(200)
        tcp_port_label = QLabel("TCP Port:")
        self.tcp_port_input = QLineEdit(self.config.get('LASER_RANGING', 'tcp_port', fallback='20108'))
        self.tcp_port_input.setMinimumWidth(150)
        self.tcp_port_input.setMaximumWidth(200)
        tcp_fields_layout.addWidget(tcp_ip_label, 0, 0)
        tcp_fields_layout.addWidget(self.tcp_ip_input, 0, 1)
        tcp_fields_layout.addWidget(tcp_port_label, 1, 0)
        tcp_fields_layout.addWidget(self.tcp_port_input, 1, 1)
        self.tcp_fields_widget.setLayout(tcp_fields_layout)
        
        # Initially show serial fields and set default connection type
        conn_type_default = self.config.get('LASER_RANGING', 'connection_type', fallback='serial')
        self.conn_type_combo.setCurrentText(conn_type_default.title())  # title() capitalizes first letter
        self.change_connection_type(conn_type_default.title())
        
        # Baudrate selection (only for serial)
        self.baud_widget = QWidget()  # Wrapper widget for baud layout
        baud_layout = QGridLayout()  # Изменили на QGridLayout
        baud_label = QLabel("Baud Rate:")
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "57600", "115200"])
        self.baud_combo.setCurrentText("115200")  # Default
        self.baud_combo.setMinimumWidth(150)
        self.baud_combo.setMaximumWidth(200)
        baud_layout.addWidget(baud_label, 0, 0)  # Строка 0, колонка 0
        baud_layout.addWidget(self.baud_combo, 0, 1)  # Строка 0, колонка 1
        self.baud_widget.setLayout(baud_layout)
        
        # Connection button
        self.conn_btn = QPushButton("Connect")
        self.conn_btn.clicked.connect(self.toggle_connection)
        self.conn_btn.setMinimumSize(150, 30)
        
        # Place items in grid
        connection_layout.addWidget(self.serial_port_widget, 1, 0, 1, 2)  # Spans 2 columns
        connection_layout.addWidget(self.tcp_fields_widget, 2, 0, 2, 2)   # Spans 2 rows and 2 columns
        connection_layout.addWidget(self.baud_widget, 4, 0, 1, 2)         # Spans 2 columns
        connection_layout.addWidget(self.conn_btn, 5, 0, 1, 2)            # Spans 2 columns
        
        main_layout.addWidget(connection_group)
        
        # Ranging controls
        ranging_group = QGroupBox("Ranging Controls")
        ranging_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #6a6a6a;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
                color: white;
                background-color: #353535;
            }
        """)
        ranging_layout = QGridLayout(ranging_group)
        
        # Ranging mode
        mode_label = QLabel("Ranging Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single Ranging", "Continuous Ranging", "Stop Ranging"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        self.mode_combo.setMinimumWidth(150)
        self.mode_combo.setMaximumWidth(200)
        
        # Target selection
        target_label = QLabel("Target Selection:")
        self.target_combo = QComboBox()
        self.target_combo.addItems(["First Target", "Last Target", "Multi-target"])
        self.target_combo.setMinimumWidth(150)
        self.target_combo.setMaximumWidth(200)
        # Подключаем сигнал для обновления режима цели
        self.target_combo.currentTextChanged.connect(self.on_target_changed)
        
        # Frequency control
        freq_label = QLabel("Frequency (Hz):")
        self.freq_spin = QSpinBox()
        self.freq_spin.setRange(1, 10)
        self.freq_spin.setValue(1)
        self.freq_spin.setMinimumWidth(100)
        self.freq_spin.setMaximumWidth(150)
        
        # Range settings
        min_range_label = QLabel("Min Gating Distance (m):")
        self.min_range_spin = QSpinBox()
        self.min_range_spin.setRange(15, 20000)
        self.min_range_spin.setValue(15)
        self.min_range_spin.setMinimumWidth(100)
        self.min_range_spin.setMaximumWidth(150)
        
        max_range_label = QLabel("Max Gating Distance (m):")
        self.max_range_spin = QSpinBox()
        self.max_range_spin.setRange(15, 4200)
        self.max_range_spin.setValue(4200)
        self.max_range_spin.setMinimumWidth(100)
        self.max_range_spin.setMaximumWidth(150)
        
        # Apply range settings button
        self.apply_range_btn = QPushButton("Apply Range Settings")
        self.apply_range_btn.clicked.connect(self.apply_range_settings)
        self.apply_range_btn.setEnabled(False)
        self.apply_range_btn.setMinimumSize(150, 30)
        
        # Toggle ranging button (moved lower as requested)
        self.range_btn = QPushButton("Start Ranging")
        self.range_btn.clicked.connect(self.toggle_ranging)
        self.range_btn.setEnabled(False)
        self.range_btn.setMinimumSize(150, 30)
        
        # Add widgets to grid in a structured way
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
        
        # Position the ranging button lower in the grid as requested
        ranging_layout.addWidget(self.range_btn, 3, 0, 1, 4)  # Spanning 4 columns and positioned lower
        
        main_layout.addWidget(ranging_group)
        
        # Results display
        results_group = QGroupBox("Measurement Results")
        results_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #6a6a6a;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
                color: white;
                background-color: #353535;
            }
        """)
        results_layout = QVBoxLayout(results_group)
        
        self.distance_label = QLabel("Distance: -- m")
        self.distance_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.distance_label.setAlignment(Qt.AlignCenter)
        self.distance_label.setStyleSheet("""
            QLabel {
                background-color: #353535; 
                padding: 10px; 
                font-size: 24px; 
                font-weight: bold;
                border-radius: 5px;
                color: white;
            }
        """)
        results_layout.addWidget(self.distance_label)
        
        # Multi-target display
        self.multi_targets_label = QLabel("Multi-targets: --")
        self.multi_targets_label.setFont(QFont("Arial", 14))
        self.multi_targets_label.setAlignment(Qt.AlignCenter)
        self.multi_targets_label.setStyleSheet("""
            QLabel {
                background-color: #2d4d6b; 
                padding: 5px;
                border-radius: 3px;
                color: white;
            }
        """)
        self.multi_targets_label.setVisible(False)  # Initially hidden
        results_layout.addWidget(self.multi_targets_label)
        
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(200)
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("""
            QTextEdit {
                background-color: #252525;
                border: 1px solid #6a6a6a;
                color: #ffffff;
                padding: 5px;
            }
        """)
        results_layout.addWidget(self.status_text)
        
        main_layout.addWidget(results_group)
        
        # Progress bar for ranging activity
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # System info
        info_group = QGroupBox("System Information")
        info_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #6a6a6a;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
                color: white;
                background-color: #353535;
            }
        """)
        info_layout = QGridLayout(info_group)
        
        # Version info buttons
        self.fpga_version_btn = QPushButton("Query FPGA Version")
        self.fpga_version_btn.clicked.connect(self.query_fpga_version)
        self.fpga_version_btn.setMinimumSize(150, 30)
        self.mcu_version_btn = QPushButton("Query MCU Version")
        self.mcu_version_btn.clicked.connect(self.query_mcu_version)
        self.mcu_version_btn.setMinimumSize(150, 30)
        self.hardware_version_btn = QPushButton("Query Hardware Version")
        self.hardware_version_btn.clicked.connect(self.query_hardware_version)
        self.hardware_version_btn.setMinimumSize(150, 30)
        self.sn_btn = QPushButton("Query Serial Number")
        self.sn_btn.clicked.connect(self.query_serial_number)
        self.sn_btn.setMinimumSize(150, 30)
        
        info_layout.addWidget(self.fpga_version_btn, 0, 0)
        info_layout.addWidget(self.mcu_version_btn, 0, 1)
        info_layout.addWidget(self.hardware_version_btn, 1, 0)
        info_layout.addWidget(self.sn_btn, 1, 1)
        
        main_layout.addWidget(info_group)
        
        # Timer for UI updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(1000)  # Update every second
    
    def on_target_changed(self, _):
        """Handle target selection changes"""
        if self.is_connected:
            self.set_target_mode()
    
    def change_connection_type(self, connection_type):
        """Handle connection type changes"""
        self.connection_type = connection_type.lower()
        
        # Check if widgets are already initialized
        if hasattr(self, 'serial_port_widget'):
            self.serial_port_widget.setVisible(self.connection_type == "serial")
        if hasattr(self, 'tcp_fields_widget'):
            self.tcp_fields_widget.setVisible(self.connection_type == "tcp/ip")
        if hasattr(self, 'baud_widget'):
            self.baud_widget.setVisible(self.connection_type == "serial")
    
    def refresh_ports(self):
        """Refresh available serial ports"""
        import serial.tools.list_ports
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)
    
    def toggle_connection(self):
        """Toggle connection to the laser rangefinder"""
        if not self.is_connected:
            self.connect_to_device()
        else:
            self.disconnect()
    
    def connect_to_device(self):
        """Connect to the laser rangefinder device"""
        try:
            if self.connection_type == "serial":
                # Serial connection
                port = self.port_combo.currentText()
                baud = int(self.baud_combo.currentText())
                
                self.serial_conn = serial.Serial(port, baud, timeout=1)
                self.protocol_handler = ProtocolHandler(self.serial_conn)
                connection_info = f"{port} at {baud} baud"
            else:
                # TCP connection
                host = self.tcp_ip_input.text().strip()
                try:
                    port = int(self.tcp_port_input.text().strip())
                except ValueError:
                    QMessageBox.critical(self, "Invalid Input", "Please enter a valid TCP port number.")
                    return
                
                self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.tcp_socket.settimeout(5)  # 5 second timeout
                self.tcp_socket.connect((host, port))
                
                # Import here to avoid circular imports
                from tcp_protocol_handler import TcpProtocolHandler
                self.protocol_handler = TcpProtocolHandler(self.tcp_socket)
                connection_info = f"TCP {host}:{port}"
            
            self.is_connected = True
            self.update_connection_status()
            self.status_bar.showMessage(f"Connected via {self.connection_type.upper()} to {connection_info}")
            self.log_signal.emit(f"Connected via {self.connection_type.upper()} to {connection_info}")
            
            # Set first/last/multi target mode based on combo selection
            self.set_target_mode()
        except ValueError as ve:
            QMessageBox.critical(self, "Invalid Input", f"Invalid input value: {str(ve)}")
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to connect: {str(e)}")
            if self.tcp_socket:
                try:
                    self.tcp_socket.close()
                except:
                    pass
                self.tcp_socket = None
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()

    def disconnect(self):
        """Disconnect from the laser rangefinder"""
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
        self.status_bar.showMessage("Disconnected")
        self.log_signal.emit("Disconnected from device")
    
    def update_connection_status(self):
        """Update UI based on connection status"""
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
    
    def on_mode_changed(self, text):
        """Handle ranging mode changes"""
        if text == "Stop Ranging" and self.is_ranging:
            self.stop_ranging()
    
    def toggle_ranging(self):
        """Toggle ranging operation"""
        if not self.is_connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to the device first.")
            return
        
        # Проверяем, действительно ли протокол-обработчик может выполнять измерения
        if self.protocol_handler and not hasattr(self.protocol_handler, 'single_ranging'):
            self.log_signal.emit("Protocol handler not properly initialized")
            return

        if self.is_ranging:
            self.stop_ranging()
        else:
            self.start_ranging()
    
    def start_ranging(self):
        """Start ranging operation"""
        if not self.is_connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to the device first.")
            return
        
        mode = self.mode_combo.currentText()
        if mode == "Single Ranging":
            self.send_single_ranging_command()
            # For single ranging, we don't stay in ranging mode
            self.is_ranging = False
            self.update_ranging_button()
        elif mode == "Continuous Ranging":
            self.start_continuous_ranging()
        elif mode == "Stop Ranging":
            self.stop_ranging()
    
    def start_continuous_ranging(self):
        """Start continuous ranging in a separate thread"""
        if not self.is_connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to the device first.")
            return
        
        # Set ranging frequency
        self.set_ranging_frequency()
        
        self.is_ranging = True
        self.update_ranging_button()
        self.progress_bar.setVisible(True)
        
        # Start ranging in a separate thread
        self.ranging_thread = threading.Thread(target=self.continuous_ranging_worker, daemon=True)
        self.ranging_thread.start()
    
    def continuous_ranging_worker(self):
        """Worker function for continuous ranging"""
        if self.protocol_handler:
            self.protocol_handler.start_continuous_ranging()
        
        # Счетчик ошибок для предотвращения бесконечных попыток
        error_count = 0
        max_errors = 5
        
        while self.is_ranging:
            # Проверяем, активно ли соединение
            if not self.is_connected:
                self.log_signal.emit("Connection lost, stopping ranging...")
                break
                
            try:
                # In continuous mode, we just wait for responses
                if self.protocol_handler:
                    # Process any incoming responses
                    response = self.protocol_handler.read_response(timeout=0.05)  # Reduced timeout
                    if response:
                        parsed = self.protocol_handler._parse_response(response)
                        if parsed and parsed['command_code'] in [0x04, 0x06]:  # Continuous ranging or error
                            if parsed['command_code'] == 0x04 and len(parsed['params']) == 4:  # Valid ranging response
                                status, dist_high, dist_low, dist_decimal = parsed['params']
                                
                                # Calculate distance
                                distance = dist_high * 256 + dist_low + dist_decimal * 0.1
                                
                                # Decode status
                                status_desc, is_multi_target = self.protocol_handler._decode_ranging_status_extended(status)
                                
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
                
                # Сброс счетчика ошибок при успешной итерации
                error_count = 0
                
                # Небольшая пауза, чтобы не перегружать CPU
                time.sleep(0.01)
                
            except Exception as e:
                error_msg = str(e)
                # Проверяем, является ли ошибка таймаутом или проблемой соединения
                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    # Логируем таймаут, но не прекращаем процесс измерения
                    self.log_signal.emit("Communication timeout, continuing...")
                    error_count += 1
                elif "invalid header" in error_msg.lower() or "connection" in error_msg.lower():
                    # Ошибки протокола или соединения
                    self.log_signal.emit(f"Communication error: {error_msg}")
                    error_count += 1
                    # Проверим, возможно ли восстановить соединение
                    try:
                        if hasattr(self.protocol_handler, 'check_connection') and not self.protocol_handler.check_connection():
                            self.log_signal.emit("Connection lost, stopping ranging...")
                            break
                    except:
                        pass
                else:
                    self.log_signal.emit(f"Error during continuous ranging: {str(e)}")
                    error_count += 1
                
                # Прекращаем измерение при достижении максимального числа ошибок
                if error_count >= max_errors:
                    self.log_signal.emit("Too many errors, stopping ranging...")
                    break
    
    def stop_ranging(self):
        """Stop ranging operation"""
        if self.is_connected and self.protocol_handler:
            try:
                self.protocol_handler.stop_ranging()
            except Exception as e:
                self.log_signal.emit(f"Error stopping ranging: {str(e)}")
        
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
        """Handle multi-target data in the main thread"""
        if multi_targets_data:
            # Format multi-target display
            multi_targets_str = self.format_multi_targets_display(multi_targets_data)
            
            self.multi_targets_label.setText(f"Multi-targets: {multi_targets_str}")
            self.multi_targets_label.setVisible(True)
        else:
            self.multi_targets_data.clear()
            self.multi_targets_label.setVisible(False)
    
    def send_single_ranging_command(self):
        """Send single ranging command to device"""
        if self.protocol_handler:
            result = self.protocol_handler.single_ranging()
            if result:
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
                        self.update_signal.emit(f"{result['distance']:.1f}", result['status_description'])
                        self.update_multi_signal.emit({})  # Hide multi-target label
                else:
                    self.update_signal.emit(f"{result['distance']:.1f}", result['status_description'])
                    self.update_multi_signal.emit({})  # Hide multi-target label
                    
                self.log_signal.emit(f"Single ranging: {result['distance']:.1f}m - {result['status_description']}")
            else:
                self.log_signal.emit("Single ranging failed")
    
    def set_target_mode(self):
        """Set the target selection mode (first, last, multi)"""
        if not self.is_connected:
            return
            
        mode_map = {"First Target": self.protocol_handler.TARGET_FIRST, 
                   "Last Target": self.protocol_handler.TARGET_LAST, 
                   "Multi-target": self.protocol_handler.TARGET_MULTI}
        target_mode = mode_map.get(self.target_combo.currentText(), self.protocol_handler.TARGET_FIRST)
        
        if self.protocol_handler:
            success = self.protocol_handler.set_target_mode(target_mode)
            if success:
                self.log_signal.emit(f"Target mode set to: {self.target_combo.currentText()}")
            else:
                self.log_signal.emit(f"Failed to set target mode to: {self.target_combo.currentText()}")
    
    def set_ranging_frequency(self):
        """Set the ranging frequency"""
        freq = self.freq_spin.value()
        if self.protocol_handler:
            success = self.protocol_handler.set_ranging_frequency(freq)
            if success:
                self.log_signal.emit(f"Ranging frequency set to: {freq}Hz")
            else:
                self.log_signal.emit(f"Failed to set ranging frequency to: {freq}Hz")
    
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
                self.log_signal.emit(f"Range settings applied: Min={min_dist}m, Max={max_dist}m")
            else:
                self.log_signal.emit(f"Failed to apply range settings: Min={min_dist}m, Max={max_dist}m")
        except ValueError as e:
            QMessageBox.warning(self, "Invalid Range", f"Invalid range value: {str(e)}")
    
    def query_fpga_version(self):
        """Query FPGA software version"""
        if self.protocol_handler:
            result = self.protocol_handler.query_fpga_version()
            if result:
                version_str = f"FPGA Version: {result['version']}, Date: {result['year']}-{result['month']:02d}-{result['date']:02d}, Author: {result['author']}"
                self.log_signal.emit(version_str)
            else:
                self.log_signal.emit("Failed to query FPGA version")
    
    def query_mcu_version(self):
        """Query MCU software version"""
        if self.protocol_handler:
            result = self.protocol_handler.query_mcu_version()
            if result:
                version_str = f"MCU Version: {result['version']}, Date: {result['year']}-{result['month']:02d}-{result['date']:02d}, Author: {result['author']}"
                self.log_signal.emit(version_str)
            else:
                self.log_signal.emit("Failed to query MCU version")
    
    def query_hardware_version(self):
        """Query hardware version"""
        if self.protocol_handler:
            result = self.protocol_handler.query_hardware_version()
            if result:
                version_str = f"Hardware Versions - MB: {result['motherboard']}, CT: {result['control_board']}, APD: {result['detection_board']}, LD: {result['driver_board']}"
                self.log_signal.emit(version_str)
            else:
                self.log_signal.emit("Failed to query hardware version")
    
    def query_serial_number(self):
        """Query serial number"""
        if self.protocol_handler:
            result = self.protocol_handler.query_sn_number()
            if result:
                sn_str = f"Serial Number: {result['serial_number']} (Manufactured: {result['year']}-{result['month']:02d})"
                self.log_signal.emit(sn_str)
            else:
                self.log_signal.emit("Failed to query serial number")
    
    def update_display(self, distance, status_desc):
        """Update the display with new measurement"""
        if distance != "--":
            self.distance_label.setText(f"Distance: {distance} m")
            # Если расстояние в допустимых пределах, показываем зеленый фон
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
            # Если статус указывает на "out of range", показываем красный фон
            if "out of range" in status_desc.lower() or "abnormal" in status_desc.lower():
                self.distance_label.setStyleSheet("""
                    QLabel {
                        background-color: #b71c1c; 
                        padding: 10px; 
                        font-size: 24px; 
                        font-weight: bold;
                        border-radius: 5px;
                        color: white;
                    }
                """)
            else:
                # Для многократных целей или других случаев, когда нет конкретного расстояния
                self.distance_label.setStyleSheet("""
                    QLabel {
                        background-color: #353535; 
                        padding: 10px; 
                        font-size: 24px; 
                        font-weight: bold;
                        border-radius: 5px;
                        color: white;
                    }
                """)
    
    def log_message(self, message):
        """Log a message to the status text"""
        timestamp = time.strftime("%H:%M:%S")
        self.status_text.append(f"[{timestamp}] {message}")
    
    def update_ui(self):
        """Periodic UI updates"""
        # Update progress bar for continuous ranging
        if self.is_ranging:
            self.progress_bar.setValue((self.progress_bar.value() + 5) % 100)
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About 3km Eye-Safe Laser Rangefinder",
            "<b>3km Eye-Safe Laser Rangefinder Desktop Application</b><br><br>"
            "This application controls a 3km eye-safe laser rangefinder module.<br>"
            "Operating wavelength: 1535nm (eye-safe Class I)<br>"
            "Maximum range: Up to 4200m for building targets<br><br>"
            "Developed using PyQt5 and pySerial."
        )
    
    def closeEvent(self, event):
        """Handle application closing"""
        # Stop ranging operations
        if self.is_ranging:
            self.stop_ranging()
        
        # Disconnect from device
        if self.is_connected:
            self.disconnect()
        
        # Wait a bit for threads to finish
        if self.ranging_thread and self.ranging_thread.is_alive():
            self.ranging_thread.join(timeout=2)
        
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = LaserRangefinderApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()