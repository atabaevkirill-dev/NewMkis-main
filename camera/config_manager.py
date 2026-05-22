import os
import json
from pathlib import Path
from PyQt6.QtCore import QDate

# Configuration management
class ConfigManager:
    def __init__(self):
        self.config_path = os.path.join(os.path.expanduser("~"), "OnCamLogs", "config.json")
        self.default_config = {
            "cameras": {
                "camera1": {
                    "ip": "192.168.1.68",
                    "port": 80,
                    "username": "admin",
                    "password": "12qwaszx",
                    "rtsp_port": 554,
                    "stream_path": "/stream1",
                    "custom_rtsp_url": "",
                    "fps": 15,
                    "encoding": "MJPG",
                    "resolution_width": 640,
                    "resolution_height": 480
                },
                "camera2": {
                    "ip": "192.168.1.108",
                    "port": 80,
                    "username": "admin",
                    "password": "12qwaszx",
                    "rtsp_port": 554,
                    "stream_path": "/stream1",
                    "custom_rtsp_url": "",
                    "fps": 25,  # According to thermal camera specs
                    "encoding": "H264",  # According to thermal camera specs
                    "resolution_width": 1024,  # According to thermal camera specs
                    "resolution_height": 768  # According to thermal camera specs
                },
                "pan_tilt": {
                    "ip": "192.168.1.115",
                    "port": 9761
                }
            },
            "display": {
                "crosshair_enabled": False,
                "ptz_panels_visible": False,
                "invert_tilt": True
            },
            "controls": {
                "speed_change_delay": 0.2,
                "zoom_delay": 0.02
            },
            "device_info": {
                "date": QDate.currentDate().toString("yyyy-MM-dd"),
                "product_name": "",
                "serial_number": "",
                "ip_address": "",
                "port": 80,
                "login": "",
                "password": ""
            },
            "relayx3": {
                "tcp_ip": "192.168.1.115",
                "tcp_port": 9761,
                "device_address": 1,
                "baud_rate": 115200,
                "uart_speed_setting": "115200",
                "channel_states": [False, False, False],
                "channel_names": ["Channel 1", "Channel 2", "Channel 3"],
                "temp_thresholds": [60.0, 60.0, 60.0],
                "voltage_thresholds": [24.0, 24.0, 24.0],
                "polarity_check_enabled": [True, True, True],
                "voltage_check_enabled": [True, True, True],
                "temperature_check_enabled": [True, True, True]
            }
        }
        self.config = self.load_config()
    
    def load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    # Merge with default config to ensure all keys exist
                    merged_config = self.default_config.copy()
                    for key, value in config.items():
                        if isinstance(value, dict) and key in merged_config:
                            merged_config[key].update(value)
                        else:
                            merged_config[key] = value
                    return merged_config
            else:
                self.save_config(self.default_config)
                return self.default_config
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.default_config
    
    def save_config(self, config=None):
        try:
            config_to_save = config or self.config
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(config_to_save, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get_camera_config(self, camera_key):
        return self.config["cameras"].get(camera_key, {})
    
    def get_display_config(self):
        return self.config["display"]
    
    def get_controls_config(self):
        return self.config["controls"]
    
    def get_device_info(self):
        return self.config["device_info"]
    
    def get_relayx3_config(self):
        return self.config.get("relayx3", {})
    
    def update_relayx3_config(self, new_config):
        """Обновить конфигурацию устройства RelayX3"""
        if "relayx3" not in self.config:
            self.config["relayx3"] = {}
        self.config["relayx3"].update(new_config)
        self.save_config()

# Global config manager
config_manager = ConfigManager()