"""
Tests for YOLO Tracker
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from core.yolo_tracker import YOLOTracker


class TestYOLOTracker:
    """Test suite for YOLOTracker class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.tracker = YOLOTracker()

    def teardown_method(self):
        """Cleanup after each test"""
        if hasattr(self.tracker, 'model') and self.tracker.model is not None:
            del self.tracker.model

    def test_initialization(self):
        """Test tracker initialization"""
        assert hasattr(self.tracker, 'model')
        assert hasattr(self.tracker, 'track_history')
        assert isinstance(self.tracker.track_history, dict)

    def test_detect_objects(self):
        """Test object detection"""
        # Create a test frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Mock the model prediction
        mock_result = Mock()
        mock_result.boxes = Mock()
        mock_result.boxes.xyxy = np.array([[100, 100, 200, 200]])
        mock_result.boxes.conf = np.array([0.95])
        mock_result.boxes.cls = np.array([0])  # person class
        mock_result.names = {0: 'person'}
        
        with patch.object(self.tracker, 'model') as mock_model:
            mock_model.return_value = [mock_result]
            
            results = self.tracker.detect_objects(frame)
            
            assert results is not None
            assert len(results) > 0

    def test_track_objects(self):
        """Test object tracking"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Mock the model prediction with tracking
        mock_result = Mock()
        mock_result.boxes = Mock()
        mock_result.boxes.xyxy = np.array([[100, 100, 200, 200]])
        mock_result.boxes.id = np.array([1])  # Track ID
        mock_result.boxes.conf = np.array([0.95])
        mock_result.boxes.cls = np.array([0])
        mock_result.names = {0: 'person'}
        
        with patch.object(self.tracker, 'model') as mock_model:
            mock_model.return_value = [mock_result]
            
            results = self.tracker.track_objects(frame)
            
            assert results is not None

    def test_draw_detections(self):
        """Test drawing detections on frame"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Create mock detections
        detections = [
            {'bbox': [100, 100, 200, 200], 'conf': 0.95, 'class': 'person'},
            {'bbox': [300, 300, 400, 400], 'conf': 0.87, 'class': 'car'}
        ]
        
        result_frame = self.tracker.draw_detections(frame, detections)
        
        assert result_frame.shape == frame.shape
        assert result_frame.dtype == frame.dtype

    def test_filter_by_confidence(self):
        """Test filtering detections by confidence threshold"""
        detections = [
            {'bbox': [100, 100, 200, 200], 'conf': 0.95, 'class': 'person'},
            {'bbox': [300, 300, 400, 400], 'conf': 0.45, 'class': 'car'},
            {'bbox': [50, 50, 150, 150], 'conf': 0.78, 'class': 'dog'}
        ]
        
        filtered = self.tracker.filter_by_confidence(detections, threshold=0.5)
        
        assert len(filtered) == 2
        assert all(d['conf'] >= 0.5 for d in filtered)

    def test_update_track_history(self):
        """Test updating track history"""
        track_id = 1
        bbox = [100, 100, 200, 200]
        
        self.tracker.update_track_history(track_id, bbox)
        
        assert track_id in self.tracker.track_history
        assert len(self.tracker.track_history[track_id]) > 0

    def test_get_track_path(self):
        """Test getting track path"""
        track_id = 1
        
        # Add some history
        for i in range(5):
            self.tracker.update_track_history(track_id, [i*10, i*10, i*10+100, i*10+100])
        
        path = self.tracker.get_track_path(track_id)
        
        assert len(path) > 0
        assert len(path) <= 5  # Should be limited

    def test_clear_track_history(self):
        """Test clearing track history"""
        # Add some tracks
        self.tracker.update_track_history(1, [100, 100, 200, 200])
        self.tracker.update_track_history(2, [300, 300, 400, 400])
        
        self.tracker.clear_track_history()
        
        assert len(self.tracker.track_history) == 0

    def test_count_objects_by_class(self):
        """Test counting objects by class"""
        detections = [
            {'bbox': [100, 100, 200, 200], 'conf': 0.95, 'class': 'person'},
            {'bbox': [300, 300, 400, 400], 'conf': 0.87, 'class': 'person'},
            {'bbox': [50, 50, 150, 150], 'conf': 0.78, 'class': 'car'}
        ]
        
        counts = self.tracker.count_objects_by_class(detections)
        
        assert counts['person'] == 2
        assert counts['car'] == 1

    def test_empty_frame_handling(self):
        """Test handling empty or None frames"""
        result = self.tracker.detect_objects(None)
        assert result == [] or result is None

    def test_model_loading_error(self):
        """Test handling model loading errors"""
        with patch('core.yolo_tracker.YOLO') as mock_yolo:
            mock_yolo.side_effect = Exception("Model loading failed")
            
            # Should handle gracefully
            tracker = YOLOTracker()
            # The tracker should still be created, but model might be None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
