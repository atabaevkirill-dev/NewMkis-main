from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QSpinBox, QDateEdit, QFileDialog, QMessageBox, QCheckBox
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QAction
from camera.config_manager import config_manager


class DeviceInfoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Device Information")
        self.resize(400, 350)
        
        # Apply dark theme stylesheet
        self.setStyleSheet("""
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
            
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QSpinBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QDateEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QLineEdit:focus {
                border: 1px solid #777777;
            }
            
            QPushButton {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 6px;
                min-width: 70px;
                color: #ffffff;
            }
            
            QPushButton:hover {
                background-color: #555555;
            }
            
            QPushButton:pressed {
                background-color: #666666;
            }
        """)
        
        self.setup_ui()
        self.load_device_info()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Device info group
        device_group = QGroupBox("Device Information")
        device_layout = QFormLayout()
        
        # Date field
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        
        # Product name field
        self.product_name = QLineEdit()
        
        # Serial number field
        self.serial_number = QLineEdit()
        
        # IP address field
        self.ip_address = QLineEdit()
        
        # Port field
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(80)
        
        # Login field
        self.login = QLineEdit()
        
        # Password field - now visible, not masked
        self.password = QLineEdit()
        
        device_layout.addRow("Date:", self.date_edit)
        device_layout.addRow("Product Name:", self.product_name)
        device_layout.addRow("Serial Number:", self.serial_number)
        device_layout.addRow("IP Address:", self.ip_address)
        device_layout.addRow("Port:", self.port)
        device_layout.addRow("Login:", self.login)
        device_layout.addRow("Password:", self.password)
        
        device_group.setLayout(device_layout)
        layout.addWidget(device_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.select_folder_btn = QPushButton("Select Folder")
        self.save_btn.clicked.connect(self.on_save_clicked)
        self.select_folder_btn.clicked.connect(self.select_screenshot_folder)
        button_layout.addWidget(self.select_folder_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)

    def select_screenshot_folder(self):
        """Allow user to select a folder for saving screenshots"""
        folder = QFileDialog.getExistingDirectory(self, "Select Screenshot Folder", "")
        if folder:
            # Store the selected folder in the config
            config = config_manager.config.copy()
            if "device_info" not in config:
                config["device_info"] = {}
            config["device_info"]["screenshot_folder"] = folder
            config_manager.config = config
            config_manager.save_config(config)
            
            QMessageBox.information(self, "Folder Selected", f"Screenshot folder set to:\n{folder}")

    def load_device_info(self):
        """Load existing device info from config manager"""
        device_config = config_manager.get_device_info()
        
        # Convert date string to QDate if it exists in config
        date_str = device_config.get("date", "")
        if date_str:
            loaded_date = QDate.fromString(date_str, "yyyy-MM-dd")
            if loaded_date.isValid():
                self.date_edit.setDate(loaded_date)
            else:
                self.date_edit.setDate(QDate.currentDate())
        else:
            self.date_edit.setDate(QDate.currentDate())
            
        self.product_name.setText(device_config.get("product_name", ""))
        self.serial_number.setText(device_config.get("serial_number", ""))
        self.ip_address.setText(device_config.get("ip_address", ""))
        self.port.setValue(device_config.get("port", 80))
        self.login.setText(device_config.get("login", ""))
        self.password.setText(device_config.get("password", ""))

    def take_screenshot(self):
        """Take a screenshot and save it to the selected folder"""
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QPixmap, QScreen
            
            # Get the application instance
            app = QApplication.instance()
            if app is None:
                app = QApplication([])
                
            # Get the primary screen
            screen = app.primaryScreen()
            screenshot = screen.grabWindow(0)  # 0 captures the entire screen
            
            # Get the screenshot folder from config
            device_config = config_manager.get_device_info()
            screenshot_folder = device_config.get("screenshot_folder", "")
            
            if not screenshot_folder:
                QMessageBox.warning(self, "No Folder Selected", 
                                   "Please select a folder for screenshots first.")
                return
            
            # Generate filename with timestamp and device info
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            product_name = self.product_name.text().replace(" ", "_").replace("/", "_").replace("\\", "_")
            if not product_name:
                product_name = "unknown_device"
            
            filename = f"{timestamp}_{product_name}_DeviceInfo.png"
            filepath = f"{screenshot_folder}/{filename}"
            
            # Save the screenshot
            screenshot.save(filepath, "PNG")
            
            return filepath
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            QMessageBox.critical(self, "Screenshot Error", 
                               f"Could not take screenshot:\n{str(e)}")
            return None

    def on_save_clicked(self):
        """Handle save button click - save info and take screenshot"""
        # Save the device info
        self.save_device_info()
        
        # Take a screenshot
        screenshot_path = self.take_screenshot()
        
        if screenshot_path:
            QMessageBox.information(self, "Success", 
                                  f"Device info saved and screenshot captured!\nSaved to:\n{screenshot_path}")
        else:
            # Still consider save successful even if screenshot failed
            QMessageBox.information(self, "Info Saved", 
                                  "Device info saved successfully!")

    def save_device_info(self):
        """Save device info to config manager"""
        config = config_manager.config.copy()
        
        # Ensure the device_info section exists
        if "device_info" not in config:
            config["device_info"] = {}
        
        # Save the values - convert date to string for JSON serialization
        config["device_info"]["date"] = self.date_edit.date().toString("yyyy-MM-dd")
        config["device_info"]["product_name"] = self.product_name.text().strip()
        config["device_info"]["serial_number"] = self.serial_number.text().strip()
        config["device_info"]["ip_address"] = self.ip_address.text().strip()
        config["device_info"]["port"] = self.port.value()
        config["device_info"]["login"] = self.login.text().strip()
        config["device_info"]["password"] = self.password.text().strip()
        
        # Update the config_manager's config and save to file
        config_manager.config = config
        config_manager.save_config(config)
        return config