"""
Tests for Configuration Manager
"""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock

from camera.config_manager import config_manager, ConfigManager


class TestConfigManager:
    """Test suite for ConfigManager class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.test_config_dir = "/tmp/test_oncam_config"
        self.test_config_file = os.path.join(self.test_config_dir, "config.json")
        
        # Create test directory
        os.makedirs(self.test_config_dir, exist_ok=True)
        
        # Create a fresh config manager for testing
        self.config_manager = ConfigManager()
        self.config_manager.config_dir = self.test_config_dir
        self.config_manager.config_file = self.test_config_file

    def teardown_method(self):
        """Cleanup after each test"""
        if os.path.exists(self.test_config_file):
            os.remove(self.test_config_file)
        if os.path.exists(self.test_config_dir):
            os.rmdir(self.test_config_dir)

    def test_initialization(self):
        """Test config manager initialization"""
        assert hasattr(self.config_manager, 'config')
        assert isinstance(self.config_manager.config, dict)

    def test_load_default_config(self):
        """Test loading default configuration"""
        # Remove config file if exists
        if os.path.exists(self.test_config_file):
            os.remove(self.test_config_file)
        
        config = self.config_manager.load_config()
        
        assert 'cameras' in config
        assert 'display' in config
        assert 'controls' in config
        assert len(config['cameras']) == 2  # Two cameras by default

    def test_save_and_load_config(self):
        """Test saving and loading configuration"""
        test_config = {
            'cameras': [
                {'name': 'Camera 1', 'ip': '192.168.1.100'},
                {'name': 'Camera 2', 'ip': '192.168.1.101'}
            ],
            'display': {'crosshairs': True},
            'controls': {'speed': 50}
        }
        
        self.config_manager.config = test_config
        result = self.config_manager.save_config(test_config)
        
        assert result is True
        assert os.path.exists(self.test_config_file)
        
        # Load and verify
        loaded_config = self.config_manager.load_config()
        assert loaded_config['cameras'][0]['ip'] == '192.168.1.100'
        assert loaded_config['display']['crosshairs'] is True

    def test_get_camera_config(self):
        """Test getting camera configuration"""
        self.config_manager.config = {
            'cameras': [
                {'name': 'Camera 1', 'ip': '192.168.1.100', 'port': 554},
                {'name': 'Camera 2', 'ip': '192.168.1.101', 'port': 554}
            ]
        }
        
        camera1_config = self.config_manager.get_camera_config(0)
        assert camera1_config['ip'] == '192.168.1.100'
        assert camera1_config['port'] == 554

    def test_update_camera_config(self):
        """Test updating camera configuration"""
        self.config_manager.config = {
            'cameras': [
                {'name': 'Camera 1', 'ip': '192.168.1.100'}
            ]
        }
        
        self.config_manager.update_camera_config(0, {'ip': '192.168.1.200'})
        
        assert self.config_manager.config['cameras'][0]['ip'] == '192.168.1.200'

    def test_get_display_settings(self):
        """Test getting display settings"""
        self.config_manager.config = {
            'display': {
                'crosshairs': True,
                'ptz_panel': False,
                'invert_tilt': True
            }
        }
        
        display_settings = self.config_manager.get_display_settings()
        assert display_settings['crosshairs'] is True
        assert display_settings['ptz_panel'] is False

    def test_invalid_config_file(self):
        """Test handling invalid config file"""
        # Create invalid JSON file
        with open(self.test_config_file, 'w') as f:
            f.write("invalid json content")
        
        # Should load default config without crashing
        config = self.config_manager.load_config()
        assert isinstance(config, dict)
        assert 'cameras' in config

    def test_missing_config_directory(self):
        """Test handling missing config directory"""
        # Remove directory
        os.rmdir(self.test_config_dir)
        
        # Should create directory and load default config
        config = self.config_manager.load_config()
        assert isinstance(config, dict)
        assert os.path.exists(self.test_config_dir)

    def test_config_structure(self):
        """Test default config structure"""
        config = self.config_manager.load_config()
        
        # Verify required sections exist
        assert 'cameras' in config
        assert 'display' in config
        assert 'controls' in config
        
        # Verify camera structure
        assert len(config['cameras']) == 2
        for camera in config['cameras']:
            assert 'name' in camera
            assert 'ip' in camera
            assert 'port' in camera
            assert 'username' in camera
            assert 'password' in camera


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
