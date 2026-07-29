"""
Tests for AI Integration (Ollama)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from core.ai_integration import OllamaAI


class TestOllamaAI:
    """Test suite for OllamaAI class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.ai = OllamaAI(model="test-model")

    def teardown_method(self):
        """Cleanup after each test"""
        if hasattr(self.ai, 'session') and self.ai.session:
            self.ai.session.close()

    def test_initialization(self):
        """Test AI initialization"""
        assert self.ai.model == "test-model"
        assert self.ai.base_url == "http://localhost:11434"
        assert hasattr(self.ai, 'session')

    def test_set_model(self):
        """Test setting model"""
        self.ai.set_model("gpt-oss:20b")
        assert self.ai.model == "gpt-oss:20b"

    @patch('requests.post')
    def test_chat_success(self, mock_post):
        """Test successful chat response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message': {'content': 'Hello! How can I help you?'}
        }
        mock_post.return_value = mock_response
        
        result = self.ai.chat("Hello")
        
        assert result is not None
        assert 'Hello' in result or 'help' in result.lower()
        mock_post.assert_called_once()

    @patch('requests.post')
    def test_chat_failure(self, mock_post):
        """Test chat failure handling"""
        mock_post.side_effect = Exception("Connection error")
        
        result = self.ai.chat("Hello")
        
        assert result is None or "error" in result.lower()

    @patch('requests.post')
    def test_chat_timeout(self, mock_post):
        """Test chat timeout handling"""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()
        
        result = self.ai.chat("Hello")
        
        assert result is None or "timeout" in result.lower()

    @patch('requests.get')
    def test_check_connection_success(self, mock_get):
        """Test successful connection check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = self.ai.check_connection()
        
        assert result is True
        mock_get.assert_called_with(f"{self.ai.base_url}/api/tags", timeout=5)

    @patch('requests.get')
    def test_check_connection_failure(self, mock_get):
        """Test failed connection check"""
        mock_get.side_effect = Exception("Connection refused")
        
        result = self.ai.check_connection()
        
        assert result is False

    @patch('requests.get')
    def test_get_available_models(self, mock_get):
        """Test getting available models"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'models': [
                {'name': 'gpt-oss:20b'},
                {'name': 'llama2:7b'}
            ]
        }
        mock_get.return_value = mock_response
        
        models = self.ai.get_available_models()
        
        assert len(models) == 2
        assert 'gpt-oss:20b' in models
        assert 'llama2:7b' in models

    @patch('requests.get')
    def test_get_available_models_empty(self, mock_get):
        """Test getting empty models list"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'models': []}
        mock_get.return_value = mock_response
        
        models = self.ai.get_available_models()
        
        assert len(models) == 0

    def test_chat_history(self):
        """Test chat history management"""
        # Add messages to history
        self.ai.add_to_history("user", "Hello")
        self.ai.add_to_history("assistant", "Hi there!")
        
        history = self.ai.get_history()
        
        assert len(history) == 2
        assert history[0]['role'] == 'user'
        assert history[1]['role'] == 'assistant'

    def test_clear_history(self):
        """Test clearing chat history"""
        self.ai.add_to_history("user", "Hello")
        self.ai.add_to_history("assistant", "Hi")
        
        self.ai.clear_history()
        
        history = self.ai.get_history()
        assert len(history) == 0

    def test_context_window_limit(self):
        """Test context window limit"""
        # Add many messages
        for i in range(20):
            self.ai.add_to_history("user", f"Message {i}")
        
        history = self.ai.get_history()
        
        # Should be limited to max_context_length (typically 10)
        assert len(history) <= self.ai.max_context_length

    @patch('requests.post')
    def test_chat_with_context(self, mock_post):
        """Test chat with conversation context"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message': {'content': 'Response with context'}
        }
        mock_post.return_value = mock_response
        
        # Add context
        self.ai.add_to_history("user", "Previous question")
        self.ai.add_to_history("assistant", "Previous answer")
        
        result = self.ai.chat("Follow-up question")
        
        # Should include context in request
        assert result is not None
        call_args = mock_post.call_args
        request_data = call_args[1]['json']
        assert 'messages' in request_data
        assert len(request_data['messages']) > 1

    def test_invalid_base_url(self):
        """Test handling invalid base URL"""
        ai = OllamaAI(base_url="invalid-url")
        result = ai.check_connection()
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
