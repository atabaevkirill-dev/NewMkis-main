"""
Tests for TechLazer Service Protocol
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import socket

from ptz.techlazer_service_protocol import TechLazerServiceProtocol


class TestTechLazerServiceProtocol:
    """Test suite for TechLazerServiceProtocol class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.protocol = TechLazerServiceProtocol(ip="192.168.1.100", port=9760)

    def teardown_method(self):
        """Cleanup after each test"""
        if self.protocol.socket:
            self.protocol.close()

    def test_initialization(self):
        """Test protocol initialization"""
        assert self.protocol.ip == "192.168.1.100"
        assert self.protocol.port == 9760
        assert self.protocol.connected is False
        assert self.protocol.socket is None

    @patch('socket.socket')
    def test_connect_success(self, mock_socket_class):
        """Test successful connection"""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        result = self.protocol.connect()
        
        assert result is True
        assert self.protocol.connected is True
        mock_socket.connect.assert_called_once_with(("192.168.1.100", 9760))

    @patch('socket.socket')
    def test_connect_failure(self, mock_socket_class):
        """Test connection failure"""
        mock_socket_class.side_effect = socket.error("Connection refused")
        
        result = self.protocol.connect()
        
        assert result is False
        assert self.protocol.connected is False

    def test_disconnect(self):
        """Test disconnect method"""
        mock_socket = Mock()
        self.protocol.socket = mock_socket
        self.protocol.connected = True
        
        self.protocol.disconnect()
        
        mock_socket.close.assert_called_once()
        assert self.protocol.socket is None

    def test_send_command_not_connected(self):
        """Test sending command when not connected"""
        result = self.protocol._send_command("$S#")
        assert result is None

    @patch('socket.socket')
    def test_get_pan_position_success(self, mock_socket_class):
        """Test getting pan position successfully"""
        mock_socket = Mock()
        mock_socket.recv.return_value = b"$S,123.45#\n"
        mock_socket_class.return_value = mock_socket
        
        self.protocol.connect()
        
        with patch.object(self.protocol, '_send_command', return_value="$S,123.45#"):
            result = self.protocol.get_pan_position()
            assert result == 123.45

    @patch('socket.socket')
    def test_get_pan_position_invalid_response(self, mock_socket_class):
        """Test getting pan position with invalid response"""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        self.protocol.connect()
        
        with patch.object(self.protocol, '_send_command', return_value="INVALID"):
            result = self.protocol.get_pan_position()
            assert result is None

    def test_move_to_pan_position_valid(self):
        """Test moving to valid pan position"""
        with patch.object(self.protocol, '_send_command', return_value="$S,OK#"):
            result = self.protocol.move_to_pan_position(180.0, 50.0)
            assert result is True

    def test_move_to_pan_position_invalid_angle(self):
        """Test moving to invalid pan angle"""
        result = self.protocol.move_to_pan_position(400.0, 50.0)
        assert result is False

    def test_move_to_pan_position_negative_speed(self):
        """Test moving with negative speed"""
        result = self.protocol.move_to_pan_position(180.0, -10.0)
        assert result is False

    def test_get_tilt_position_success(self):
        """Test getting tilt position successfully"""
        with patch.object(self.protocol, '_send_command', return_value="$X,45.67#"):
            result = self.protocol.get_tilt_position()
            assert result == 45.67

    def test_move_to_tilt_position_valid(self):
        """Test moving to valid tilt position"""
        with patch.object(self.protocol, '_send_command', return_value="$X,OK#"):
            result = self.protocol.move_to_tilt_position(90.0, 30.0)
            assert result is True

    def test_move_to_tilt_position_invalid_angle(self):
        """Test moving to invalid tilt angle"""
        result = self.protocol.move_to_tilt_position(-10.0, 30.0)
        assert result is False

    def test_get_supply_voltage_success(self):
        """Test getting supply voltage successfully"""
        with patch.object(self.protocol, '_send_command', return_value="$0,24.5#"):
            result = self.protocol.get_supply_voltage()
            assert result == 24.5

    def test_get_supply_voltage_invalid_response(self):
        """Test getting supply voltage with invalid response"""
        with patch.object(self.protocol, '_send_command', return_value="INVALID"):
            result = self.protocol.get_supply_voltage()
            assert result is None

    def test_thread_safety(self):
        """Test thread safety with lock"""
        assert hasattr(self.protocol, 'lock')
        assert self.protocol.lock is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
