from PyQt6.QtWidgets import QDialog, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QSpinBox, QCheckBox
from PyQt6.QtCore import Qt
from camera.config_manager import config_manager

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera Settings")
        self.setModal(True)
        self.resize(400, 500)  # Increased height to accommodate new fields
        
        # Apply dark theme stylesheet
        self.setStyleSheet("""
            QDialog {
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
            
            QCheckBox {
                spacing: 5px;
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
        self.load_settings()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Camera 1 settings
        cam1_group = QGroupBox("Camera 1")
        cam1_layout = QFormLayout()
        self.cam1_ip = QLineEdit()
        self.cam1_username = QLineEdit()
        self.cam1_password = QLineEdit()
        self.cam1_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.cam1_custom_rtsp = QLineEdit()
        self.cam1_fps = QSpinBox()
        self.cam1_fps.setRange(1, 30)
        self.cam1_fps.setValue(15)
        self.cam1_resolution_width = QSpinBox()
        self.cam1_resolution_width.setRange(160, 1920)
        self.cam1_resolution_width.setValue(640)
        self.cam1_resolution_height = QSpinBox()
        self.cam1_resolution_height.setRange(120, 1080)
        self.cam1_resolution_height.setValue(480)
        cam1_layout.addRow("IP Address:", self.cam1_ip)
        cam1_layout.addRow("Username:", self.cam1_username)
        cam1_layout.addRow("Password:", self.cam1_password)
        cam1_layout.addRow("Custom RTSP URL:", self.cam1_custom_rtsp)
        cam1_layout.addRow("FPS:", self.cam1_fps)
        cam1_layout.addRow("Resolution Width:", self.cam1_resolution_width)
        cam1_layout.addRow("Resolution Height:", self.cam1_resolution_height)
        cam1_group.setLayout(cam1_layout)
        layout.addWidget(cam1_group)
        
        # Camera 2 settings (thermal camera)
        cam2_group = QGroupBox("Camera 2 (Thermal)")
        cam2_layout = QFormLayout()
        self.cam2_ip = QLineEdit()
        self.cam2_username = QLineEdit()
        self.cam2_password = QLineEdit()
        self.cam2_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.cam2_custom_rtsp = QLineEdit()
        self.cam2_custom_rtsp.setToolTip("Leave empty to use auto-generated thermal camera URL format: rtsp://IP:554/live?channel=0&subtype=0&proto=Onvif")
        self.cam2_fps = QSpinBox()
        self.cam2_fps.setRange(1, 30)
        self.cam2_fps.setValue(25)  # Default for thermal camera
        self.cam2_resolution_width = QSpinBox()
        self.cam2_resolution_width.setRange(160, 1920)
        self.cam2_resolution_width.setValue(1024)  # Default for thermal camera
        self.cam2_resolution_height = QSpinBox()
        self.cam2_resolution_height.setRange(120, 1080)
        self.cam2_resolution_height.setValue(768)  # Default for thermal camera
        cam2_layout.addRow("IP Address:", self.cam2_ip)
        cam2_layout.addRow("Username:", self.cam2_username)
        cam2_layout.addRow("Password:", self.cam2_password)
        cam2_layout.addRow("Custom RTSP URL:", self.cam2_custom_rtsp)
        cam2_layout.addRow("FPS:", self.cam2_fps)
        cam2_layout.addRow("Resolution Width:", self.cam2_resolution_width)
        cam2_layout.addRow("Resolution Height:", self.cam2_resolution_height)
        cam2_group.setLayout(cam2_layout)
        layout.addWidget(cam2_group)
        
        # Pan-Tilt settings
        pt_group = QGroupBox("Pan-Tilt Unit")
        pt_layout = QFormLayout()
        self.pt_ip = QLineEdit()
        self.pt_port = QSpinBox()  # Add port spinbox
        self.pt_port.setRange(1, 65535)  # Valid port range
        self.pt_port.setValue(9761)  # Default port value for Pelco-D
        pt_layout.addRow("IP Address:", self.pt_ip)
        pt_layout.addRow("Port:", self.pt_port)  # Add port field to layout
        pt_group.setLayout(pt_layout)
        layout.addWidget(pt_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_settings(self):
        cam1_config = config_manager.get_camera_config("camera1")
        cam2_config = config_manager.get_camera_config("camera2")
        pt_config = config_manager.get_camera_config("pan_tilt")
        
        self.cam1_ip.setText(cam1_config.get("ip", ""))
        self.cam1_username.setText(cam1_config.get("username", ""))
        self.cam1_password.setText(cam1_config.get("password", ""))
        self.cam1_custom_rtsp.setText(cam1_config.get("custom_rtsp_url", ""))
        self.cam1_fps.setValue(cam1_config.get("fps", 15))
        self.cam1_resolution_width.setValue(cam1_config.get("resolution_width", 640))
        self.cam1_resolution_height.setValue(cam1_config.get("resolution_height", 480))
        
        self.cam2_ip.setText(cam2_config.get("ip", ""))
        self.cam2_username.setText(cam2_config.get("username", ""))
        self.cam2_password.setText(cam2_config.get("password", ""))
        self.cam2_custom_rtsp.setText(cam2_config.get("custom_rtsp_url", ""))
        self.cam2_fps.setValue(cam2_config.get("fps", 25))
        self.cam2_resolution_width.setValue(cam2_config.get("resolution_width", 1024))
        self.cam2_resolution_height.setValue(cam2_config.get("resolution_height", 768))
        
        self.pt_ip.setText(pt_config.get("ip", ""))
        self.pt_port.setValue(pt_config.get("port", 9761))  # Load port value with default 9761
    
    def save_settings(self):
        config = config_manager.config.copy()
        config["cameras"]["camera1"]["ip"] = self.cam1_ip.text().strip()
        config["cameras"]["camera1"]["username"] = self.cam1_username.text().strip()
        config["cameras"]["camera1"]["password"] = self.cam1_password.text().strip()
        # Only save custom RTSP URL if it's not empty, otherwise clear it
        custom_url1 = self.cam1_custom_rtsp.text().strip()
        config["cameras"]["camera1"]["custom_rtsp_url"] = custom_url1 if custom_url1 else ""
        config["cameras"]["camera1"]["fps"] = self.cam1_fps.value()
        config["cameras"]["camera1"]["resolution_width"] = self.cam1_resolution_width.value()
        config["cameras"]["camera1"]["resolution_height"] = self.cam1_resolution_height.value()
        
        config["cameras"]["camera2"]["ip"] = self.cam2_ip.text().strip()
        config["cameras"]["camera2"]["username"] = self.cam2_username.text().strip()
        config["cameras"]["camera2"]["password"] = self.cam2_password.text().strip()
        # Only save custom RTSP URL if it's not empty, otherwise clear it
        custom_url2 = self.cam2_custom_rtsp.text().strip()
        config["cameras"]["camera2"]["custom_rtsp_url"] = custom_url2 if custom_url2 else ""
        config["cameras"]["camera2"]["fps"] = self.cam2_fps.value()
        config["cameras"]["camera2"]["resolution_width"] = self.cam2_resolution_width.value()
        config["cameras"]["camera2"]["resolution_height"] = self.cam2_resolution_height.value()
        
        config["cameras"]["pan_tilt"]["ip"] = self.pt_ip.text().strip()
        config["cameras"]["pan_tilt"]["port"] = self.pt_port.value()  # Save port value
        
        # Update the config_manager's config and save to file
        config_manager.config = config
        config_manager.save_config(config)
        return config