import tkinter as tk
from tkinter import ttk
import socket
import struct
import threading
import time
import re
from datetime import timedelta
import serial
import serial.tools.list_ports
import os
import sys


class LEDControllerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LED Controller - RelayX3 Protocol")
        self.root.geometry("1200x700")
        
        # Device connection parameters
        self.device_ip = "192.168.127.254"
        self.device_port = 4001
        self.device_address = 1  # Default device address
        self.connection_socket = None
        self.serial_connection = None
        self.is_connected = False
        self.connection_type = tk.StringVar(value="network")  # Default to network connection
        
        # Auto-reconnect attributes
        self.auto_reconnect = True
        self.reconnect_interval = 5  # seconds between reconnection attempts
        
        # Timer threads storage
        self.timer_threads = []
        self.timer_running = {}  # Track which timers are currently running
        
        # History of connections
        self.connection_history = []
        self.load_connection_history()
        
        # Create the main frame
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create top frame for IP and port configuration
        config_frame = tk.LabelFrame(main_frame, text="Device Configuration", padx=10, pady=5)
        config_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Connection type selection
        tk.Label(config_frame, text="Connection Type:").grid(row=0, column=0, sticky=tk.W)
        connection_type_frame = tk.Frame(config_frame)
        connection_type_frame.grid(row=1, column=0, columnspan=6, sticky=tk.W+tk.E, pady=(5, 10))
        self.network_radio = tk.Radiobutton(connection_type_frame, text="Network (TCP/IP)", variable=self.connection_type, 
                      value="network", command=self.update_connection_fields, font=("Arial", 10, "bold"))
        self.network_radio.pack(side=tk.LEFT, padx=(0, 20))
        self.serial_radio = tk.Radiobutton(connection_type_frame, text="Serial (COM Port)", variable=self.connection_type, 
                      value="serial", command=self.update_connection_fields, font=("Arial", 10, "bold"))
        self.serial_radio.pack(side=tk.LEFT)
        
        # Network configuration
        self.network_frame = tk.LabelFrame(config_frame, text="Network Settings", padx=5, pady=5)
        self.network_frame.grid(row=2, column=0, columnspan=6, sticky=tk.W+tk.E, pady=(0, 10))
        
        tk.Label(self.network_frame, text="IP Address:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        # Create a Combobox for IP addresses history
        self.ip_combo = ttk.Combobox(self.network_frame, width=15)
        self.ip_combo.grid(row=0, column=1, padx=(0, 15))
        self.ip_combo['values'] = [item[0] for item in self.connection_history if item[2] == 'network']
        self.ip_combo.set(self.device_ip)
        
        tk.Label(self.network_frame, text="Port:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        # Create a Combobox for Port numbers history
        self.port_combo = ttk.Combobox(self.network_frame, width=10)
        self.port_combo.grid(row=0, column=3, padx=(0, 15))
        # Extract unique ports for network connections
        ports = list(set([item[1] for item in self.connection_history if item[2] == 'network']))
        self.port_combo['values'] = sorted(ports, key=int)
        self.port_combo.set(str(self.device_port))
        
        # Device address input field (common for both connection types)
        tk.Label(self.network_frame, text="Device Address:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        self.address_entry = tk.Entry(self.network_frame, width=10)
        self.address_entry.insert(0, str(self.device_address))
        self.address_entry.grid(row=0, column=5)
        
        # Button to update parameters
        update_params_btn = tk.Button(self.network_frame, text="Apply Changes", command=self.update_device_params)
        update_params_btn.grid(row=0, column=6, padx=(10, 0))
        
        # Bind events to update params automatically
        self.ip_combo.bind('<FocusOut>', lambda event: self.update_device_params())
        self.ip_combo.bind('<Return>', lambda event: self.update_device_params())
        self.port_combo.bind('<FocusOut>', lambda event: self.update_device_params())
        self.port_combo.bind('<Return>', lambda event: self.update_device_params())
        self.address_entry.bind('<FocusOut>', lambda event: self.update_device_params())
        self.address_entry.bind('<Return>', lambda event: self.update_device_params())
        
        # Serial configuration
        self.serial_frame = tk.LabelFrame(config_frame, text="Serial Settings", padx=5, pady=5)
        self.serial_frame.grid(row=2, column=0, columnspan=6, sticky=tk.W+tk.E, pady=(0, 10))
        self.serial_frame.grid_remove()  # Initially hidden
        
        tk.Label(self.serial_frame, text="Serial Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.serial_port_var = tk.StringVar()
        self.serial_port_dropdown = tk.OptionMenu(self.serial_frame, self.serial_port_var, "Select Port")
        self.serial_port_dropdown.grid(row=0, column=1, padx=(0, 15))
        
        tk.Label(self.serial_frame, text="Baud Rate:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.baud_rate_var = tk.StringVar(value="9600")
        baud_options = ["9600", "19200", "38400", "115200"]
        self.baud_rate_dropdown = tk.OptionMenu(self.serial_frame, self.baud_rate_var, *baud_options)
        self.baud_rate_dropdown.grid(row=0, column=3, padx=(0, 15))
        
        # Additional serial settings
        tk.Label(self.serial_frame, text="Data Bits:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        self.data_bits_var = tk.StringVar(value="8")
        data_bits_options = ["5", "6", "7", "8"]
        self.data_bits_dropdown = tk.OptionMenu(self.serial_frame, self.data_bits_var, *data_bits_options)
        self.data_bits_dropdown.grid(row=0, column=5, padx=(0, 15))
        
        tk.Label(self.serial_frame, text="Stop Bits:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        self.stop_bits_var = tk.StringVar(value="1")
        stop_bits_options = ["1", "2"]
        self.stop_bits_dropdown = tk.OptionMenu(self.serial_frame, self.stop_bits_var, *stop_bits_options)
        self.stop_bits_dropdown.grid(row=1, column=1, padx=(0, 15))
        
        tk.Label(self.serial_frame, text="Parity:").grid(row=1, column=2, sticky=tk.W, padx=(0, 5))
        self.parity_var = tk.StringVar(value="None")
        parity_options = ["None", "Even", "Odd", "Mark", "Space"]
        self.parity_dropdown = tk.OptionMenu(self.serial_frame, self.parity_var, *parity_options)
        self.parity_dropdown.grid(row=1, column=3, padx=(0, 15))
        
        # Refresh button for serial ports
        refresh_serial_btn = tk.Button(self.serial_frame, text="Refresh Ports", command=self.refresh_serial_ports)
        refresh_serial_btn.grid(row=1, column=4, padx=(0, 15))
        
        # Populate initial serial ports
        self.refresh_serial_ports()
        
        # Create middle frame for timer controls
        timer_frame = tk.LabelFrame(main_frame, text="Timer Controls", padx=10, pady=5)
        timer_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Sequential/Parallel control
        self.operation_mode = tk.StringVar(value="parallel")  # Default to parallel
        tk.Radiobutton(timer_frame, text="Sequential", variable=self.operation_mode, value="sequential").pack(side=tk.LEFT, padx=(0, 10))
        tk.Radiobutton(timer_frame, text="Parallel", variable=self.operation_mode, value="parallel").pack(side=tk.LEFT, padx=(0, 20))
        
        # Start all timers button
        self.start_all_timers_btn = tk.Button(timer_frame, text="Start All Timers", bg="lightblue", width=15, command=self.start_all_timers)
        self.start_all_timers_btn.pack(side=tk.RIGHT)
        
        # Stop all timers button
        self.stop_all_timers_btn = tk.Button(timer_frame, text="Stop All Timers", bg="orange", width=15, command=self.stop_all_timers)
        self.stop_all_timers_btn.pack(side=tk.RIGHT, padx=(0, 5))
        
        # Create channels frames
        channels_frame = tk.Frame(main_frame)
        channels_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True)
        
        left_frame = tk.LabelFrame(channels_frame, text="Channel 1", padx=10, pady=10)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        right_frame = tk.LabelFrame(channels_frame, text="Channel 2", padx=10, pady=10)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        third_frame = tk.LabelFrame(channels_frame, text="Channel 3", padx=10, pady=10)
        third_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        # Left channel widgets
        self.left_status_label = tk.Label(left_frame, text="Status: OFF", bg="red", fg="white", font=("Arial", 12))
        self.left_status_label.pack(pady=5)
        
        # Left channel timer controls
        left_timer_frame = tk.LabelFrame(left_frame, text="Timer Settings", padx=5, pady=5)
        left_timer_frame.pack(pady=5, fill=tk.X)
        
        # Hours, minutes, seconds inputs for left channel
        tk.Label(left_timer_frame, text="Hours:").grid(row=0, column=0)
        self.left_hours = tk.Spinbox(left_timer_frame, from_=0, to=3, width=5)
        self.left_hours.grid(row=0, column=1, padx=5)
        
        tk.Label(left_timer_frame, text="Minutes:").grid(row=0, column=2)
        self.left_minutes = tk.Spinbox(left_timer_frame, from_=0, to=59, width=5)
        self.left_minutes.grid(row=0, column=3, padx=5)
        
        tk.Label(left_timer_frame, text="Seconds:").grid(row=0, column=4)
        self.left_seconds = tk.Spinbox(left_timer_frame, from_=3, to=10800, width=5)  # 3 seconds to 3 hours (10800 seconds)
        self.left_seconds.grid(row=0, column=5, padx=5)
        
        # Cycles input for left channel
        tk.Label(left_timer_frame, text="Cycles:").grid(row=1, column=0)
        self.left_cycles = tk.Spinbox(left_timer_frame, from_=1, to=999, width=5)
        self.left_cycles.grid(row=1, column=1, padx=5)
        tk.Label(left_timer_frame, text="(999 = ∞)").grid(row=1, column=2, columnspan=2, sticky=tk.W)
        
        # Timer countdown display for left channel
        self.left_timer_display = tk.Label(left_frame, text="Time remaining: --:--:--", 
                                         bg="lightgray", font=("Arial", 10))
        self.left_timer_display.pack(pady=2, fill=tk.X)
        
        # Count display for left channel
        self.left_count_display = tk.Label(left_frame, text="Count: 0/0", 
                                         bg="lightgray", font=("Arial", 10))
        self.left_count_display.pack(pady=2, fill=tk.X)
        
        left_button_frame = tk.Frame(left_frame)
        left_button_frame.pack(pady=10)
        
        self.left_on_btn = tk.Button(left_button_frame, text="ON", bg="lightgreen", width=10, height=2, command=self.left_on_click)
        self.left_on_btn.pack(side=tk.TOP, pady=5)
        
        self.left_off_btn = tk.Button(left_button_frame, text="OFF", bg="pink", width=10, height=2, command=self.left_off_click)
        self.left_off_btn.pack(side=tk.BOTTOM, pady=5)
        
        # Left channel timer start button
        self.left_timer_btn = tk.Button(left_frame, text="Start Timer", bg="lightyellow", width=15, command=lambda: self.start_timer("left"))
        self.left_timer_btn.pack(pady=5)
        
        # Left channel timer stop button
        self.left_stop_timer_btn = tk.Button(left_frame, text="Stop Timer", bg="orange", width=15, command=lambda: self.stop_timer("left"))
        self.left_stop_timer_btn.pack(pady=5)
        
        # Right channel widgets
        self.right_status_label = tk.Label(right_frame, text="Status: OFF", bg="red", fg="white", font=("Arial", 12))
        self.right_status_label.pack(pady=5)
        
        # Right channel timer controls
        right_timer_frame = tk.LabelFrame(right_frame, text="Timer Settings", padx=5, pady=5)
        right_timer_frame.pack(pady=5, fill=tk.X)
        
        # Hours, minutes, seconds inputs for right channel
        tk.Label(right_timer_frame, text="Hours:").grid(row=0, column=0)
        self.right_hours = tk.Spinbox(right_timer_frame, from_=0, to=3, width=5)
        self.right_hours.grid(row=0, column=1, padx=5)
        
        tk.Label(right_timer_frame, text="Minutes:").grid(row=0, column=2)
        self.right_minutes = tk.Spinbox(right_timer_frame, from_=0, to=59, width=5)
        self.right_minutes.grid(row=0, column=3, padx=5)
        
        tk.Label(right_timer_frame, text="Seconds:").grid(row=0, column=4)
        self.right_seconds = tk.Spinbox(right_timer_frame, from_=3, to=10800, width=5)  # 3 seconds to 3 hours
        self.right_seconds.grid(row=0, column=5, padx=5)
        
        # Cycles input for right channel
        tk.Label(right_timer_frame, text="Cycles:").grid(row=1, column=0)
        self.right_cycles = tk.Spinbox(right_timer_frame, from_=1, to=999, width=5)
        self.right_cycles.grid(row=1, column=1, padx=5)
        tk.Label(right_timer_frame, text="(999 = ∞)").grid(row=1, column=2, columnspan=2, sticky=tk.W)
        
        # Timer countdown display for right channel
        self.right_timer_display = tk.Label(right_frame, text="Time remaining: --:--:--", 
                                          bg="lightgray", font=("Arial", 10))
        self.right_timer_display.pack(pady=2, fill=tk.X)
        
        # Count display for right channel
        self.right_count_display = tk.Label(right_frame, text="Count: 0/0", 
                                          bg="lightgray", font=("Arial", 10))
        self.right_count_display.pack(pady=2, fill=tk.X)
        
        right_button_frame = tk.Frame(right_frame)
        right_button_frame.pack(pady=10)
        
        self.right_on_btn = tk.Button(right_button_frame, text="ON", bg="lightgreen", width=10, height=2, command=self.right_on_click)
        self.right_on_btn.pack(side=tk.TOP, pady=5)
        
        self.right_off_btn = tk.Button(right_button_frame, text="OFF", bg="pink", width=10, height=2, command=self.right_off_click)
        self.right_off_btn.pack(side=tk.BOTTOM, pady=5)
        
        # Right channel timer start button
        self.right_timer_btn = tk.Button(right_frame, text="Start Timer", bg="lightyellow", width=15, command=lambda: self.start_timer("right"))
        self.right_timer_btn.pack(pady=5)
        
        # Right channel timer stop button
        self.right_stop_timer_btn = tk.Button(right_frame, text="Stop Timer", bg="orange", width=15, command=lambda: self.stop_timer("right"))
        self.right_stop_timer_btn.pack(pady=5)
        
        # Third channel widgets
        self.third_status_label = tk.Label(third_frame, text="Status: OFF", bg="red", fg="white", font=("Arial", 12))
        self.third_status_label.pack(pady=5)
        
        # Third channel timer controls
        third_timer_frame = tk.LabelFrame(third_frame, text="Timer Settings", padx=5, pady=5)
        third_timer_frame.pack(pady=5, fill=tk.X)
        
        # Hours, minutes, seconds inputs for third channel
        tk.Label(third_timer_frame, text="Hours:").grid(row=0, column=0)
        self.third_hours = tk.Spinbox(third_timer_frame, from_=0, to=3, width=5)
        self.third_hours.grid(row=0, column=1, padx=5)
        
        tk.Label(third_timer_frame, text="Minutes:").grid(row=0, column=2)
        self.third_minutes = tk.Spinbox(third_timer_frame, from_=0, to=59, width=5)
        self.third_minutes.grid(row=0, column=3, padx=5)
        
        tk.Label(third_timer_frame, text="Seconds:").grid(row=0, column=4)
        self.third_seconds = tk.Spinbox(third_timer_frame, from_=3, to=10800, width=5)  # 3 seconds to 3 hours
        self.third_seconds.grid(row=0, column=5, padx=5)
        
        # Cycles input for third channel
        tk.Label(third_timer_frame, text="Cycles:").grid(row=1, column=0)
        self.third_cycles = tk.Spinbox(third_timer_frame, from_=1, to=999, width=5)
        self.third_cycles.grid(row=1, column=1, padx=5)
        tk.Label(third_timer_frame, text="(999 = ∞)").grid(row=1, column=2, columnspan=2, sticky=tk.W)
        
        # Timer countdown display for third channel
        self.third_timer_display = tk.Label(third_frame, text="Time remaining: --:--:--", 
                                          bg="lightgray", font=("Arial", 10))
        self.third_timer_display.pack(pady=2, fill=tk.X)
        
        # Count display for third channel
        self.third_count_display = tk.Label(third_frame, text="Count: 0/0", 
                                          bg="lightgray", font=("Arial", 10))
        self.third_count_display.pack(pady=2, fill=tk.X)
        
        third_button_frame = tk.Frame(third_frame)
        third_button_frame.pack(pady=10)
        
        self.third_on_btn = tk.Button(third_button_frame, text="ON", bg="lightgreen", width=10, height=2, command=self.third_on_click)
        self.third_on_btn.pack(side=tk.TOP, pady=5)
        
        self.third_off_btn = tk.Button(third_button_frame, text="OFF", bg="pink", width=10, height=2, command=self.third_off_click)
        self.third_off_btn.pack(side=tk.BOTTOM, pady=5)
        
        # Third channel timer start button
        self.third_timer_btn = tk.Button(third_frame, text="Start Timer", bg="lightyellow", width=15, command=lambda: self.start_timer("third"))
        self.third_timer_btn.pack(pady=5)
        
        # Third channel timer stop button
        self.third_stop_timer_btn = tk.Button(third_frame, text="Stop Timer", bg="orange", width=15, command=lambda: self.stop_timer("third"))
        self.third_stop_timer_btn.pack(pady=5)
        
        # Add advanced settings frame
        self.advanced_settings_frame = tk.LabelFrame(main_frame, text="Advanced Settings", padx=10, pady=5)
        self.advanced_settings_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Buttons for advanced features
        self.read_settings_btn = tk.Button(self.advanced_settings_frame, text="Read Settings", width=15, command=self.read_settings)
        self.read_settings_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.write_settings_btn = tk.Button(self.advanced_settings_frame, text="Write Settings", width=15, command=self.write_settings)
        self.write_settings_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.read_status_btn = tk.Button(self.advanced_settings_frame, text="Read Status", width=15, command=self.read_status)
        self.read_status_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.read_temperature_btn = tk.Button(self.advanced_settings_frame, text="Read Temperature", width=15, command=self.read_temperature)
        self.read_temperature_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.read_voltage_btn = tk.Button(self.advanced_settings_frame, text="Read Voltage", width=15, command=self.read_voltage)
        self.read_voltage_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Frame for displaying read values
        self.values_frame = tk.LabelFrame(main_frame, text="Read Values", padx=10, pady=5)
        self.values_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # Labels for displaying various read values
        self.temperature_label = tk.Label(self.values_frame, text="Temperature: -- °C", bg="lightgray", font=("Arial", 10))
        self.temperature_label.pack(fill=tk.X, pady=2)
        
        self.voltage_label = tk.Label(self.values_frame, text="Voltage: -- V", bg="lightgray", font=("Arial", 10))
        self.voltage_label.pack(fill=tk.X, pady=2)
        
        self.status_label = tk.Label(self.values_frame, text="Status: --", bg="lightgray", font=("Arial", 10))
        self.status_label.pack(fill=tk.X, pady=2)
        
        # Connection status frame
        conn_frame = tk.Frame(root)
        conn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        
        # Connection status label
        self.connection_status_label = tk.Label(conn_frame, text="Connection: Disconnected", bg="red", fg="white", font=("Arial", 10))
        self.connection_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Connect/Disconnect button
        self.conn_button = tk.Button(conn_frame, text="Connect", width=10, command=self.toggle_connection)
        self.conn_button.pack(side=tk.RIGHT, padx=(5, 0))
        
        # State tracking
        self.left_state = False  # False = OFF, True = ON
        self.right_state = False
        self.third_state = False

        # Timer state tracking
        self.left_timer_running = False
        self.right_timer_running = False
        self.third_timer_running = False

        # Operation mode (parallel or sequential) - already defined earlier in init

        # Auto-reconnect settings
        self.auto_reconnect = True
        self.reconnect_interval = 5  # seconds

        # Timer threads storage
        self.timer_threads = []

        # Initialize connection
        self.update_device_params()
        self.update_timer_display("left", 0, 0, 0)
        self.update_timer_display("right", 0, 0, 0)
        self.update_timer_display("third", 0, 0, 0)

        # Initialize serial connection parameters
        self.serial_connection = None

        # Disable control buttons initially
        self.enable_control_buttons(False)

        # Attempt initial connection
        self.connect_to_device()

        # Ensure UI reflects the correct state at startup
        self.left_status_label.config(text="Status: OFF", bg="red")
        self.right_status_label.config(text="Status: OFF", bg="red")
        self.third_status_label.config(text="Status: OFF", bg="red")

    def is_valid_ip(self, ip):
        """Validate IP address"""
        pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if re.match(pattern, ip):
            parts = ip.split('.')
            return all(0 <= int(part) <= 255 for part in parts)
        return False

    def get_resource_path(self, relative_path):
        """Get absolute path to resource, works for dev and for PyInstaller"""
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        
        return os.path.join(base_path, relative_path)
    
    def get_appdata_path(self):
        """Get path to store application data"""
        # Use AppData folder for storing connection history
        import platform
        if platform.system() == "Windows":
            appdata = os.getenv('APPDATA')
            if appdata:
                app_folder = os.path.join(appdata, "LEDController")
                os.makedirs(app_folder, exist_ok=True)
                return os.path.join(app_folder, "connection_history.txt")
        # Fallback to local directory if APPDATA is not available
        return os.path.join(os.path.expanduser("~"), ".led_controller_history")

    def load_connection_history(self):
        """Load connection history from file if it exists"""
        try:
            history_file = self.get_appdata_path()
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) == 3:  # ip, port, type
                        self.connection_history.append((parts[0], parts[1], parts[2]))
        except FileNotFoundError:
            # Create a default entry if file doesn't exist
            self.connection_history = [("192.168.127.254", "4001", "network")]
        except Exception as e:
            print(f"Error loading connection history: {e}")
            # Create a default entry if file has errors
            self.connection_history = [("192.168.127.254", "4001", "network")]
    
    def save_connection_to_history(self, ip, port, conn_type):
        """Save connection details to history"""
        # Check if this connection is already in history
        exists = False
        for i, record in enumerate(self.connection_history):
            if record[0] == ip and record[1] == str(port) and record[2] == conn_type:
                # Move this record to the beginning
                self.connection_history.insert(0, self.connection_history.pop(i))
                exists = True
                break
        
        if not exists:
            # Add new record at the beginning
            self.connection_history.insert(0, (ip, str(port), conn_type))
            # Keep only last 10 records
            if len(self.connection_history) > 10:
                self.connection_history = self.connection_history[:10]
        
        # Save to file
        try:
            history_file = self.get_appdata_path()
            with open(history_file, "w", encoding="utf-8") as f:
                for record in self.connection_history:
                    f.write(f"{record[0]},{record[1]},{record[2]}\n")
        except Exception as e:
            print(f"Could not save connection history: {e}")

    def update_device_params(self):
        """Update device parameters from input fields"""
        errors_found = []
        
        # Validate and update IP address
        ip_text = self.ip_combo.get().strip()
        if not self.is_valid_ip(ip_text):
            errors_found.append("Invalid IP address! Using default.")
            self.device_ip = "192.168.127.254"
            self.ip_combo.set(self.device_ip)
        else:
            self.device_ip = ip_text
        
        # Validate and update port
        port_text = self.port_combo.get().strip()
        try:
            port = int(port_text)
            if 1 <= port <= 65535:
                self.device_port = port
            else:
                raise ValueError("Port out of range")
        except ValueError:
            errors_found.append("Invalid port number! Using default.")
            self.device_port = 4001
            self.port_combo.set(str(self.device_port))
        
        # Validate and update device address
        address_text = self.address_entry.get().strip()
        try:
            addr = int(address_text)
            if 0 <= addr <= 255:  # Valid range for a single byte
                self.device_address = addr
            else:
                raise ValueError("Address out of range")
        except ValueError:
            errors_found.append("Invalid device address! Using default.")
            self.device_address = 1
            self.address_entry.delete(0, tk.END)
            self.address_entry.insert(0, str(self.device_address))
        
        # Provide feedback to user
        if errors_found:
            error_msg = "; ".join(errors_found)
            self.connection_status_label.config(text=error_msg, bg="red")
        else:
            self.connection_status_label.config(
                text=f"Parameters updated - IP: {self.device_ip}, Port: {self.device_port}, Addr: {self.device_address}", 
                bg="lightgreen"
            )

    def show_connection_error(self):
        """Show connection error message"""
        conn_type = "Serial" if self.connection_type.get() == "serial" else "Network"
        self.connection_status_label.config(text=f"Error: Not connected to {conn_type} device!", bg="red")
        # Flash the label to make it more noticeable
        original_color = self.connection_status_label.cget("bg")
        self.connection_status_label.config(bg="orange")
        self.root.after(500, lambda: self.connection_status_label.config(bg=original_color))

    def attempt_reconnect(self):
        """Attempt to reconnect automatically"""
        if self.is_connected or not self.auto_reconnect:
            return
            
        self.root.after(0, lambda: self.connection_status_label.config(text="Attempting to reconnect...", bg="yellow"))
        self.connect_to_device()
        
        # Schedule next reconnection attempt
        if not self.is_connected:
            self.root.after(self.reconnect_interval * 1000, self.attempt_reconnect)

    def left_on_click(self):
        """Handle left channel ON button click"""
        if not self.is_connected:
            self.show_connection_error()
            return
            
        self.left_state = True
        self.left_status_label.config(text="Status: ON", bg="green")
        # 0x8800 - turn on output 1
        self.send_pelco_d_command(self.device_address, 0x88, 0x00, 0x00, 0x00)

    def left_off_click(self):
        """Handle left channel OFF button click"""
        if not self.is_connected:
            self.show_connection_error()
            return
            
        self.left_state = False
        self.left_status_label.config(text="Status: OFF", bg="red")
        # 0x0800 - turn off output 1
        self.send_pelco_d_command(self.device_address, 0x08, 0x00, 0x00, 0x00)

    def right_on_click(self):
        """Handle right channel ON button click"""
        if not self.is_connected:
            self.show_connection_error()
            return
            
        self.right_state = True
        self.right_status_label.config(text="Status: ON", bg="green")
        # 0x0200 - turn on output 2
        self.send_pelco_d_command(self.device_address, 0x02, 0x00, 0x00, 0x00)

    def right_off_click(self):
        """Handle right channel OFF button click"""
        if not self.is_connected:
            self.show_connection_error()
            return
            
        self.right_state = False
        self.right_status_label.config(text="Status: OFF", bg="red")
        # 0x0400 - turn off output 2
        self.send_pelco_d_command(self.device_address, 0x04, 0x00, 0x00, 0x00)

    def third_on_click(self):
        """Handle third channel ON button click"""
        if not self.is_connected:
            self.show_connection_error()
            return
            
        self.third_state = True
        self.third_status_label.config(text="Status: ON", bg="green")
        # 0x0020 - turn on output 3
        self.send_pelco_d_command(self.device_address, 0x00, 0x20, 0x00, 0x00)

    def third_off_click(self):
        """Handle third channel OFF button click"""
        if not self.is_connected:
            self.show_connection_error()
            return
            
        self.third_state = False
        self.third_status_label.config(text="Status: OFF", bg="red")
        # 0x0040 - turn off output 3
        self.send_pelco_d_command(self.device_address, 0x00, 0x40, 0x00, 0x00)

    def get_timer_seconds(self, channel):
        """Calculate total seconds from hours, minutes, seconds for a channel"""
        if channel == "left":
            hours = int(self.left_hours.get())
            minutes = int(self.left_minutes.get())
            seconds = int(self.left_seconds.get())
        elif channel == "right":
            hours = int(self.right_hours.get())
            minutes = int(self.right_minutes.get())
            seconds = int(self.right_seconds.get())
        else:  # third
            hours = int(self.third_hours.get())
            minutes = int(self.third_minutes.get())
            seconds = int(self.third_seconds.get())
        
        total_seconds = hours * 3600 + minutes * 60 + seconds
        # Ensure minimum 3 seconds
        return max(total_seconds, 3)

    def get_cycles_count(self, channel):
        """Get the number of cycles for a channel (999 means infinite)"""
        if channel == "left":
            cycles = int(self.left_cycles.get())
        elif channel == "right":
            cycles = int(self.right_cycles.get())
        else:  # third
            cycles = int(self.third_cycles.get())
        
        # Return infinity if cycles is 999, otherwise return the number
        return float('inf') if cycles == 999 else cycles

    def start_timer(self, channel):
        """Start timer for a specific channel"""
        if not self.is_connected:
            self.show_connection_error()
            return
        
        # Check if timer is already running for this channel
        if getattr(self, f'{channel}_timer_running', False):
            # Show message that timer is already running
            self.connection_status_label.config(text=f"{channel.capitalize()} timer already running!", bg="orange")
            return
        
        # Calculate total seconds for the timer
        duration = self.get_timer_seconds(channel)
        total_cycles = self.get_cycles_count(channel)
        
        # Mark this timer as running
        setattr(self, f'{channel}_timer_running', True)
        
        # Create a new thread for the timer
        timer_thread = threading.Thread(target=self.run_timer_with_cycles, args=(channel, duration, total_cycles))
        timer_thread.daemon = True
        timer_thread.start()
        self.timer_threads.append(timer_thread)

    def stop_all_timers(self):
        """Stop all running timers"""
        # Reset flags for all channels
        self.left_timer_running = False
        self.right_timer_running = False
        self.third_timer_running = False
        self.all_timers_running = False  # Added for sequential mode
        
        # Turn off all channels
        self.root.after(0, lambda: self.left_off_click())
        self.root.after(0, lambda: self.right_off_click())
        self.root.after(0, lambda: self.third_off_click())
        
        # Reset displays
        self.root.after(0, lambda: self.update_timer_display("left", 0, 0, 0))
        self.root.after(0, lambda: self.update_timer_display("right", 0, 0, 0))
        self.root.after(0, lambda: self.update_timer_display("third", 0, 0, 0))
        
        # Update status
        self.connection_status_label.config(text="All timers stopped", bg="yellow")
        self.root.after(1000, lambda: self.connection_status_label.config(text="Connected", bg="green"))

    def stop_timer(self, channel):
        """Stop timer for a specific channel"""
        # For sequential mode, we need to stop all timers when any timer is stopped
        if self.operation_mode.get() == "sequential":
            self.all_timers_running = False
        else:
            # For parallel mode, stop only the specific timer
            setattr(self, f'{channel}_timer_running', False)
        
        # Turn the channel OFF
        if channel == "left":
            self.root.after(0, lambda: self.left_off_click())
        elif channel == "right":
            self.root.after(0, lambda: self.right_off_click())
        else:  # third
            self.root.after(0, lambda: self.third_off_click())
        
        # Update display
        self.root.after(0, lambda: self.update_timer_display(channel, 0, 0, 0))
        
        # Update status
        self.connection_status_label.config(text=f"{channel.capitalize()} timer stopped", bg="yellow")
        self.root.after(1000, lambda: self.connection_status_label.config(text="Connected", bg="green"))

    def update_timer_display(self, channel, remaining_time, current_cycle, total_cycles):
        """Update the timer display for a channel"""
        # Format the time as HH:MM:SS
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        seconds = remaining_time % 60
        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        # Update the appropriate display
        if channel == "left":
            self.left_timer_display.config(text=f"Time remaining: {time_str}")
            self.left_count_display.config(text=f"Count: {current_cycle}/{int(total_cycles) if total_cycles != float('inf') else '∞'}")
        elif channel == "right":
            self.right_timer_display.config(text=f"Time remaining: {time_str}")
            self.right_count_display.config(text=f"Count: {current_cycle}/{int(total_cycles) if total_cycles != float('inf') else '∞'}")
        else:  # third
            self.third_timer_display.config(text=f"Time remaining: {time_str}")
            self.third_count_display.config(text=f"Count: {current_cycle}/{int(total_cycles) if total_cycles != float('inf') else '∞'}")

    def run_timer_with_cycles(self, channel, duration, total_cycles):
        """Run the actual timer logic with cycles in a separate thread"""
        cycle_count = 0
        
        while getattr(self, f'{channel}_timer_running', True):
            # Check if we've reached the desired number of cycles
            if total_cycles != float('inf') and cycle_count >= total_cycles:
                break
                
            # Update count display
            self.root.after(0, lambda ch=channel, cc=cycle_count+1, tc=total_cycles: 
                           self.update_timer_display(ch, duration, cc, tc))
            
            # Turn the channel ON
            if channel == "left":
                self.root.after(0, lambda: self.left_on_click())
            elif channel == "right":
                self.root.after(0, lambda: self.right_on_click())
            else:  # third
                self.root.after(0, lambda: self.third_on_click())
            
            # Wait for the specified duration or until timer is stopped, updating display
            remaining_time = duration
            while remaining_time > 0 and getattr(self, f'{channel}_timer_running', True):
                self.root.after(0, lambda ch=channel, rt=remaining_time, cc=cycle_count+1, tc=total_cycles: 
                               self.update_timer_display(ch, rt, cc, tc))
                
                time.sleep(1)
                remaining_time -= 1
            
            if not getattr(self, f'{channel}_timer_running', True):
                break
                
            # Turn the channel OFF
            if channel == "left":
                self.root.after(0, lambda: self.left_off_click())
            elif channel == "right":
                self.root.after(0, lambda: self.right_off_click())
            else:  # third
                self.root.after(0, lambda: self.third_off_click())
            
            # Wait for the specified duration again or until timer is stopped, updating display
            remaining_time = duration
            while remaining_time > 0 and getattr(self, f'{channel}_timer_running', True):
                self.root.after(0, lambda ch=channel, rt=remaining_time, cc=cycle_count+1, tc=total_cycles: 
                               self.update_timer_display(ch, rt, cc, tc))
                
                time.sleep(1)
                remaining_time -= 1
            
            # Increment cycle count
            cycle_count += 1
        
        # Turn the channel OFF when stopping and reset displays
        if channel == "left":
            self.root.after(0, lambda: self.left_off_click())
            self.root.after(0, lambda: self.update_timer_display("left", 0, cycle_count, total_cycles))
        elif channel == "right":
            self.root.after(0, lambda: self.right_off_click())
            self.root.after(0, lambda: self.update_timer_display("right", 0, cycle_count, total_cycles))
        else:  # third
            self.root.after(0, lambda: self.third_off_click())
            self.root.after(0, lambda: self.update_timer_display("third", 0, cycle_count, total_cycles))

    def run_sequential_timers_with_cycles(self, left_duration, left_cycles):
        """Run left, right and third timers sequentially: left ON-OFF then right ON-OFF, then third ON-OFF, repeated for cycles"""
        total_cycles = left_cycles  # Using left_cycles parameter as total sequential cycles
        cycle_count = 0
        
        # Используем общий флаг для отслеживания остановки всех таймеров
        self.all_timers_running = True
        
        while self.all_timers_running and (total_cycles == float('inf') or cycle_count < total_cycles):
            # Update count display for left channel
            self.root.after(0, lambda cc=cycle_count+1, tc=total_cycles: 
                           self.update_timer_display("left", left_duration, cc, tc))
            
            # Turn left channel ON
            self.root.after(0, lambda: self.left_on_click())
            
            # Wait for the specified duration or until timer is stopped, updating display
            remaining_time = left_duration
            while remaining_time > 0 and self.all_timers_running:
                self.root.after(0, lambda rt=remaining_time, cc=cycle_count+1, tc=total_cycles: 
                               self.update_timer_display("left", rt, cc, tc))
                
                time.sleep(1)
                remaining_time -= 1
            
            # Turn left channel OFF
            self.root.after(0, lambda: self.left_off_click())
            
            # Brief pause between channels
            time.sleep(0.5)
            
            # Check if we should continue after pausing
            if not self.all_timers_running:
                break
                
            # Get duration for right channel
            right_duration = self.get_timer_seconds("right")
            
            # Update count display for right channel
            self.root.after(0, lambda cc=cycle_count+1, tc=self.get_cycles_count("right"): 
                           self.update_timer_display("right", right_duration, cc, tc))
            
            # Turn right channel ON
            self.root.after(0, lambda: self.right_on_click())
            
            # Wait for the specified duration or until timer is stopped, updating display
            remaining_time = right_duration  # Using individual duration for right channel
            while remaining_time > 0 and self.all_timers_running:
                self.root.after(0, lambda rt=remaining_time, cc=cycle_count+1, tc=self.get_cycles_count("right"): 
                               self.update_timer_display("right", rt, cc, tc))
                
                time.sleep(1)
                remaining_time -= 1
            
            # Turn right channel OFF
            self.root.after(0, lambda: self.right_off_click())
            
            # Brief pause between channels
            time.sleep(0.5)
            
            # Check if we should continue after pausing
            if not self.all_timers_running:
                break
                
            # Get duration for third channel
            third_duration = self.get_timer_seconds("third")
            
            # Update count display for third channel
            self.root.after(0, lambda cc=cycle_count+1, tc=self.get_cycles_count("third"): 
                           self.update_timer_display("third", third_duration, cc, tc))
            
            # Turn third channel ON
            self.root.after(0, lambda: self.third_on_click())
            
            # Wait for the specified duration or until timer is stopped, updating display
            remaining_time = third_duration  # Using individual duration for third channel
            while remaining_time > 0 and self.all_timers_running:
                self.root.after(0, lambda rt=remaining_time, cc=cycle_count+1, tc=self.get_cycles_count("third"): 
                               self.update_timer_display("third", rt, cc, tc))
                
                time.sleep(1)
                remaining_time -= 1
            
            # Turn third channel OFF
            self.root.after(0, lambda: self.third_off_click())
            
            # Increment cycle count
            cycle_count += 1
            
            # Brief pause between cycles
            time.sleep(0.5)

        # Turn off all channels when done and reset displays
        self.root.after(0, lambda: self.left_off_click())
        self.root.after(0, lambda: self.right_off_click())
        self.root.after(0, lambda: self.third_off_click())
        
        # Reset the timer running flags
        self.all_timers_running = False
        
        # Reset displays when done
        self.root.after(0, lambda: self.update_timer_display("left", 0, cycle_count, left_cycles))
        self.root.after(0, lambda: self.update_timer_display("right", 0, cycle_count, self.get_cycles_count("right")))
        self.root.after(0, lambda: self.update_timer_display("third", 0, cycle_count, self.get_cycles_count("third")))
    
    def start_all_timers(self):
        """Start all channel timers based on operation mode"""
        if not self.is_connected:
            self.show_connection_error()
            return
        
        if self.operation_mode.get() == "sequential":
            # In sequential mode: left -> right -> third channels for the specified duration
            left_duration = self.get_timer_seconds("left")
            left_cycles = self.get_cycles_count("left")
            
            # Set the flag for all timers
            self.all_timers_running = True
            
            timer_thread = threading.Thread(target=self.run_sequential_timers_with_cycles, 
                                          args=(left_duration, left_cycles))
            timer_thread.daemon = True
            timer_thread.start()
            self.timer_threads.append(timer_thread)
        else:  # parallel
            # Run all timers simultaneously
            self.start_timer("left")
            self.start_timer("right")
            self.start_timer("third")


    def toggle_connection(self):
        """Toggle connection state"""
        if self.is_connected:
            self.disconnect_from_device()
        else:
            self.connect_to_device()
    
    def connect_to_device(self):
        """Establish connection to the device (either network or serial)"""
        if self.is_connected:
            return
            
        # Update device parameters from input fields
        self.update_device_params()
        
        # Determine connection type and connect accordingly
        if self.connection_type.get() == "network":
            # Try to connect in a separate thread
            thread = threading.Thread(target=self._connect_network_thread)
            thread.daemon = True
            thread.start()
        else:  # serial
            thread = threading.Thread(target=self._connect_serial_thread)
            thread.daemon = True
            thread.start()
    
    def _connect_network_thread(self):
        """Connect to device via network in a separate thread"""
        try:
            # Update status
            self.root.after(0, lambda: self.connection_status_label.config(text="Connecting...", bg="yellow"))
            
            # Close any existing connection
            if self.connection_socket:
                try:
                    self.connection_socket.close()
                except:
                    pass  # Ignore errors when closing old socket
            
            # Create socket and connect to device
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # 5 second timeout
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Disable Nagle's algorithm
            
            sock.connect((self.device_ip, self.device_port))
            
            # Store the socket and update connection status
            self.connection_socket = sock
            self.is_connected = True
            
            # Save connection to history
            self.save_connection_to_history(self.device_ip, self.device_port, "network")
            
            # Enable buttons that depend on connection
            self.enable_control_buttons(True)
            
            # Update UI
            self.root.after(0, lambda: [
                self.connection_status_label.config(text="Connected", bg="green"),
                self.conn_button.config(text="Disconnect")
            ])
            
        except Exception as e:
            # Handle connection error
            self.root.after(0, lambda: [
                self.connection_status_label.config(text=f"Connection Error: {str(e)}", bg="red"),
                self.conn_button.config(text="Connect")
            ])
            
            # Attempt to reconnect if auto_reconnect is enabled
            if self.auto_reconnect:
                self.root.after(self.reconnect_interval * 1000, self.attempt_reconnect)

    def _connect_serial_thread(self):
        """Connect to device via serial in a separate thread"""
        try:
            # Update status
            self.root.after(0, lambda: self.connection_status_label.config(text="Connecting...", bg="yellow"))
            
            # Get serial parameters from UI
            port = self.serial_port_var.get()
            baudrate = int(self.baud_rate_var.get())
            bytesize = int(self.data_bits_var.get())
            stopbits = int(self.stop_bits_var.get())
            
            # Convert parity setting
            parity_map = {"None": serial.PARITY_NONE, "Even": serial.PARITY_EVEN, 
                         "Odd": serial.PARITY_ODD, "Mark": serial.PARITY_MARK, "Space": serial.PARITY_SPACE}
            parity = parity_map[self.parity_var.get()]
            
            # Open serial connection with all parameters
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                stopbits=stopbits,
                parity=parity,
                timeout=1
            )
            
            # Store the serial connection and update connection status
            self.serial_connection = ser
            self.is_connected = True
            
            # Save connection to history
            self.save_connection_to_history(port, baudrate, "serial")
            
            # Enable buttons that depend on connection
            self.enable_control_buttons(True)
            
            # Update UI
            self.root.after(0, lambda: [
                self.connection_status_label.config(text="Connected", bg="green"),
                self.conn_button.config(text="Disconnect")
            ])
            
        except Exception as e:
            # Handle connection error
            self.root.after(0, lambda: [
                self.connection_status_label.config(text=f"Serial Connection Error: {str(e)}", bg="red"),
                self.conn_button.config(text="Connect")
            ])
            
            # Attempt to reconnect if auto_reconnect is enabled
            if self.auto_reconnect:
                self.root.after(self.reconnect_interval * 1000, self.attempt_reconnect)

    def enable_control_buttons(self, enabled):
        """Enable or disable control buttons based on connection status"""
        # Channel ON/OFF buttons
        self.left_on_btn.config(state="normal" if enabled else "disabled")
        self.left_off_btn.config(state="normal" if enabled else "disabled")
        self.right_on_btn.config(state="normal" if enabled else "disabled")
        self.right_off_btn.config(state="normal" if enabled else "disabled")
        self.third_on_btn.config(state="normal" if enabled else "disabled")
        self.third_off_btn.config(state="normal" if enabled else "disabled")
        
        # Timer buttons
        self.left_timer_btn.config(state="normal" if enabled else "disabled")
        self.left_stop_timer_btn.config(state="normal" if enabled else "disabled")
        self.right_timer_btn.config(state="normal" if enabled else "disabled")
        self.right_stop_timer_btn.config(state="normal" if enabled else "disabled")
        self.third_timer_btn.config(state="normal" if enabled else "disabled")
        self.third_stop_timer_btn.config(state="normal" if enabled else "disabled")
        
        # All timers buttons
        self.start_all_timers_btn.config(state="normal" if enabled else "disabled")
        self.stop_all_timers_btn.config(state="normal" if enabled else "disabled")
        
        # Advanced settings buttons
        self.read_settings_btn.config(state="normal" if enabled else "disabled")
        self.write_settings_btn.config(state="normal" if enabled else "disabled")
        self.read_status_btn.config(state="normal" if enabled else "disabled")
        self.read_temperature_btn.config(state="normal" if enabled else "disabled")
        self.read_voltage_btn.config(state="normal" if enabled else "disabled")

    def disconnect_from_device(self):
        """Close the connection to the device"""
        if not self.is_connected:
            return
            
        try:
            if self.connection_type.get() == "network" and self.connection_socket:
                self.connection_socket.close()
            elif self.serial_connection:
                self.serial_connection.close()
        except Exception as e:
            # Log the error but continue with disconnection
            print(f"Error during disconnection: {e}")
        
        # Update connection status
        self.connection_socket = None
        self.serial_connection = None
        self.is_connected = False
        
        # Disable control buttons
        self.enable_control_buttons(False)
        
        # Update UI
        self.connection_status_label.config(text="Disconnected", bg="red")
        self.conn_button.config(text="Connect")

    def send_pelco_d_command(self, address, cmd1, cmd2, data1, data2, callback=None):
        """Send Pelco D command to the device (either network or serial) in a separate thread"""
        thread = threading.Thread(
            target=self._send_pelco_d_command_thread,
            args=(address, cmd1, cmd2, data1, data2, callback)
        )
        thread.daemon = True
        thread.start()
    
    def _send_pelco_d_command_thread(self, address, cmd1, cmd2, data1, data2, callback=None):
        """Actually send the Pelco D command in a separate thread to prevent GUI blocking"""
        try:
            # Update status bar
            command_str = f"{cmd1:02X}{cmd2:02X}"
            
            # Create the packet
            raw_sum = address + cmd1 + cmd2 + data1 + data2
            checksum = raw_sum & 0xFF  # Take only the least significant byte
            packet = bytearray([0xFF, address, cmd1, cmd2, data1, data2, checksum])
            
            # Send the command if connected
            if self.is_connected:
                if self.connection_type.get() == "network" and self.connection_socket:
                    # Check if socket is still alive before sending
                    try:
                        # Send the packet
                        self.connection_socket.sendall(packet)
                        
                        # If this is a command that expects a response, read the response
                        if callback:
                            response = self._read_response()
                            if response:
                                self.root.after(0, lambda: callback(response))
                    except socket.error as se:
                        # Socket is no longer valid, mark connection as lost
                        print(f"Socket error occurred: {se}")
                        self.is_connected = False
                        self.connection_socket = None
                        
                        # Attempt to reconnect if auto_reconnect is enabled
                        if self.auto_reconnect:
                            self.root.after(self.reconnect_interval * 1000, self.attempt_reconnect)
                        
                        # Show connection error
                        self.root.after(0, lambda: self.show_connection_error())
                        return
                elif self.connection_type.get() == "serial" and self.serial_connection:
                    self.serial_connection.write(packet)
                    
                    # If this is a command that expects a response, read the response
                    if callback:
                        response = self._read_response_serial()
                        if response:
                            self.root.after(0, lambda: callback(response))
            elif not self.is_connected:
                self.root.after(0, lambda: self.show_connection_error())
            
        except (socket.error, serial.SerialException) as e:
            # Handle network/serial communication errors
            self.root.after(0, lambda: self.connection_status_label.config(
                text=f"Communication Error: {str(e)}", bg="red"))
            
            # Mark connection as lost
            self.is_connected = False
            if self.connection_type.get() == "network":
                self.connection_socket = None
            else:
                self.serial_connection = None
                
            # Attempt to reconnect if auto_reconnect is enabled
            if self.auto_reconnect:
                self.root.after(self.reconnect_interval * 1000, self.attempt_reconnect)
                
        except Exception as e:
            # Handle any other errors
            self.root.after(0, lambda: self.connection_status_label.config(
                text=f"Send Error: {str(e)}", bg="red"))

    def _read_response(self):
        """Read response from network connection"""
        try:
            # Responses are typically 7 bytes: 0xFF, address, 0x00, command, MSB, LSB, checksum
            response = self.connection_socket.recv(7)
            if len(response) == 7:
                return response
        except socket.timeout:
            print("Response timeout")
        except Exception as e:
            print(f"Error reading response: {e}")
        return None

    def _read_response_serial(self):
        """Read response from serial connection"""
        try:
            # Responses are typically 7 bytes: 0xFF, address, 0x00, command, MSB, LSB, checksum
            if self.serial_connection.in_waiting >= 7:
                response = self.serial_connection.read(7)
                if len(response) == 7:
                    return response
        except Exception as e:
            print(f"Error reading serial response: {e}")
        return None

    # Advanced functions for RelayX3
    def read_settings(self):
        """Read device settings using command 0x0081"""
        if not self.is_connected:
            self.show_connection_error()
            return
        
        # Command 0x0081 - read flags
        self.send_pelco_d_command(self.device_address, 0x00, 0x81, 0x00, 0x00, callback=self.process_read_settings_response)

    def process_read_settings_response(self, response):
        """Process the response from read settings command"""
        if len(response) < 7:
            return
        
        # Update UI with received data
        self.connection_status_label.config(text="Settings read successfully", bg="lightgreen")

    def write_settings(self):
        """Write device settings using command 0x00A1"""
        if not self.is_connected:
            self.show_connection_error()
            return
        
        # Command 0x00A1 - write flags
        # This would need actual flag values from the UI, for now using dummy values
        self.send_pelco_d_command(self.device_address, 0x00, 0xA1, 0x00, 0x00)

    def read_status(self):
        """Read device status using command 0x0077"""
        if not self.is_connected:
            self.show_connection_error()
            return
        
        # Command 0x0077 - read status
        self.send_pelco_d_command(self.device_address, 0x00, 0x77, 0x00, 0x00, callback=self.process_read_status_response)

    def process_read_status_response(self, response):
        """Process the response from read status command"""
        if len(response) < 7:
            return
        
        # Extract MSB and LSB from response
        msb = response[4]
        lsb = response[5]
        
        # Combine MSB and LSB to form the status word
        status_word = (msb << 8) | lsb
        
        # Decode the status bits according to the spec
        voltage_control = bool(status_word & 0x0001)
        voltage_error = bool(status_word & 0x0002)
        polarity_control = bool(status_word & 0x0004)
        polarity_error = bool(status_word & 0x0008)
        output1_on = bool(status_word & 0x0010)
        output1_error = bool(status_word & 0x0020)
        output1_temp_error = bool(status_word & 0x0040)
        output2_on = bool(status_word & 0x0080)
        output2_error = bool(status_word & 0x0100)
        output2_temp_error = bool(status_word & 0x0200)
        output3_on = bool(status_word & 0x0400)
        output3_error = bool(status_word & 0x0800)
        output3_temp_error = bool(status_word & 0x1000)
        
        # Update UI with decoded status
        status_text = f"Status: Out1:{'ON' if output1_on else 'OFF'}, " \
                     f"Out2:{'ON' if output2_on else 'OFF'}, " \
                     f"Out3:{'ON' if output3_on else 'OFF'}, " \
                     f"Errs:{'Y' if any([output1_error, output2_error, output3_error]) else 'N'}"
        
        self.status_label.config(text=status_text)
        self.connection_status_label.config(text="Status read successfully", bg="lightgreen")

    def read_temperature(self):
        """Read device temperature using command 0x0071"""
        if not self.is_connected:
            self.show_connection_error()
            return
        
        # Command 0x0071 - read temperature
        self.send_pelco_d_command(self.device_address, 0x00, 0x71, 0x00, 0x00, callback=self.process_read_temperature_response)

    def process_read_temperature_response(self, response):
        """Process the response from read temperature command"""
        if len(response) < 7:
            return
        
        # Extract MSB and LSB from response
        msb = response[4]
        lsb = response[5]
        
        # Combine MSB and LSB to form signed short
        temp_raw = (msb << 8) | lsb
        # Convert to signed 16-bit integer
        if temp_raw >= 32768:
            temp_raw -= 65536
        
        # Temperature is multiplied by 100 according to spec
        temperature_celsius = temp_raw / 100.0
        
        # Update UI with temperature
        self.temperature_label.config(text=f"Temperature: {temperature_celsius:.2f} °C")
        self.connection_status_label.config(text="Temperature read successfully", bg="lightgreen")

    def read_voltage(self):
        """Read device voltage using command 0x0073"""
        if not self.is_connected:
            self.show_connection_error()
            return
        
        # Command 0x0073 - read voltage
        self.send_pelco_d_command(self.device_address, 0x00, 0x73, 0x00, 0x00, callback=self.process_read_voltage_response)

    def process_read_voltage_response(self, response):
        """Process the response from read voltage command"""
        if len(response) < 7:
            return
        
        # Extract MSB and LSB from response
        msb = response[4]
        lsb = response[5]
        
        # Combine MSB and LSB to form unsigned short
        voltage_raw = (msb << 8) | lsb
        
        # Voltage is multiplied by 100 according to spec
        voltage_volts = voltage_raw / 100.0
        
        # Update UI with voltage
        self.voltage_label.config(text=f"Voltage: {voltage_volts:.2f} V")
        self.connection_status_label.config(text="Voltage read successfully", bg="lightgreen")

    def update_connection_fields(self):
        """Switch between network and serial configuration fields"""
        if self.connection_type.get() == "network":
            self.network_frame.grid()
            self.serial_frame.grid_remove()
            
            # Update the comboboxes with relevant history
            network_ips = list(set([item[0] for item in self.connection_history if item[2] == 'network']))
            self.ip_combo['values'] = network_ips
            network_ports = list(set([item[1] for item in self.connection_history if item[2] == 'network']))
            self.port_combo['values'] = sorted(network_ports, key=int)
        else:  # serial
            self.network_frame.grid_remove()
            self.serial_frame.grid()

            # Update serial options if needed
            self.refresh_serial_ports()

    def refresh_serial_ports(self):
        """Refresh the list of available serial ports"""
        # Get available serial ports
        available_ports = [port.device for port in serial.tools.list_ports.comports()]
        
        # Update the dropdown menu
        menu = self.serial_port_dropdown['menu']
        menu.delete(0, 'end')
        
        if available_ports:
            for port in available_ports:
                menu.add_command(label=port, command=tk._setit(self.serial_port_var, port))
            # Select the first available port by default
            self.serial_port_var.set(available_ports[0])
        else:
            menu.add_command(label="No ports found", command=tk._setit(self.serial_port_var, "No ports found"))
            self.serial_port_var.set("No ports found")

def main():
    root = tk.Tk()
    app = LEDControllerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()