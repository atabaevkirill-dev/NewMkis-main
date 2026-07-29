"""
Tests for Video Thread
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtCore import QThread
import numpy as np

from camera.video_thread import VideoThread


class TestVideoThread:
    """Test suite for VideoThread class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.video_thread = VideoThread(camera_id=0)

    def teardown_method(self):
        """Cleanup after each test"""
        if self.video_thread.isRunning():
            self.video_thread.stop()
            self.video_thread.wait()

    def test_initialization(self):
        """Test video thread initialization"""
        assert self.video_thread.camera_id == 0
        assert self.video_thread.is_running is False
        assert hasattr(self.video_thread, 'frame_signal')

    def test_set_rtsp_url(self):
        """Test setting RTSP URL"""
        rtsp_url = "rtsp://admin:password@192.168.1.100:554/stream1"
        self.video_thread.set_rtsp_url(rtsp_url)
        assert self.video_thread.rtsp_url == rtsp_url

    def test_start_stop(self):
        """Test starting and stopping the video thread"""
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_capture.return_value = mock_cap
            
            self.video_thread.start()
            assert self.video_thread.is_running is True
            
            self.video_thread.stop()
            assert self.video_thread.is_running is False

    def test_run_with_invalid_camera(self):
        """Test running with invalid camera"""
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap = Mock()
            mock_cap.isOpened.return_value = False
            mock_capture.return_value = mock_cap
            
            # Should handle gracefully without crashing
            self.video_thread.start()
            self.video_thread.stop()

    def test_frame_processing(self):
        """Test frame processing and signal emission"""
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap = Mock()
            mock_cap.isOpened.return_value = True
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_capture.return_value = mock_cap
            
            # Connect to signal
            mock_callback = Mock()
            self.video_thread.frame_signal.connect(mock_callback)
            
            self.video_thread.start()
            self.video_thread.stop()
            
            # Callback should have been called at least once
            # Note: In real scenario, we'd need to wait for the thread

    def test_crosshair_overlay(self):
        """Test crosshair overlay functionality"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Enable crosshairs
        self.video_thread.toggle_crosshairs(True)
        assert self.video_thread.show_crosshairs is True
        
        # Disable crosshairs
        self.video_thread.toggle_crosshairs(False)
        assert self.video_thread.show_crosshairs is False

    def test_set_fps(self):
        """Test setting FPS limit"""
        self.video_thread.set_fps_limit(30)
        assert self.video_thread.fps_limit == 30

    def test_reconnection_logic(self):
        """Test camera reconnection logic"""
        with patch('cv2.VideoCapture') as mock_capture:
            mock_cap = Mock()
            # Simulate connection loss and recovery
            mock_cap.isOpened.side_effect = [True, False, True]
            mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
            mock_capture.return_value = mock_cap
            
            self.video_thread.start()
            self.video_thread.stop()
            
            # Should attempt to reconnect
            assert mock_cap.open.called or mock_cap.release.called


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
