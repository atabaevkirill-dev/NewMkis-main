from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton, 
    QHBoxLayout, QLabel, QFrame, QScrollArea, QGroupBox, QComboBox, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
import json
import os
from datetime import datetime
from core.ai_integration import OllamaAI
from camera.config_manager import config_manager


class AIAssistantWidget(QWidget):
    """
    Widget for AI assistant functionality integrated with Ollama
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.ai_client = OllamaAI()
        
        # Initialize conversation history with system context
        self.conversation_history = [{
            "role": "system",
            "content": self._get_system_context()
        }]
        
        # Set larger size for the widget
        self.resize(600, 500)
        
        self.setup_ui()
        self.check_ai_connection()
        
    def _get_system_context(self):
        """Get the system context for the AI"""
        return (
            "You are an AI assistant for the OnCam application, a lightweight camera monitoring and PTZ control application. "
            "You are a specialist in computer networks, IP cameras, and thermal imaging systems. "
            "Provide helpful responses about configuring cameras, PTZ controls, troubleshooting connections, and using application features. "
            "The application has dual RTSP video streams, ONVIF PTZ control, and Pelco-D serial protocol support. "
            "Key keyboard shortcuts include Ctrl+X (crosshairs), Ctrl+P (PTZ controls), Ctrl+I (invert tilt), and F11 (fullscreen). "
            "You have capabilities to create ASCII graphs, ping devices, and provide detailed device information."
        )
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Title
        title_label = QLabel("AI Assistant (Ollama)")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Connection status
        self.connection_status = QLabel("Connecting to Ollama...")
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.connection_status)
        
        # Conversation display area - increased size
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setMinimumHeight(250)  # Increase minimum height
        # Set proper colors for dark theme
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 5px;
            }
        """)
        layout.addWidget(self.chat_display)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask a question about the device or system...")
        self.input_field.returnPressed.connect(self.send_message)
        # Set proper colors for dark theme
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QLineEdit:focus {
                border: 1px solid #777777;
            }
        """)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        # Set proper colors for dark theme
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 60px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 1px solid #777777;
            }
            
            QPushButton:pressed {
                background-color: #3a3a3a;
                border: 1px solid #555555;
            }
        """)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        
        layout.addLayout(input_layout)
        
        # History and file management layout
        history_layout = QHBoxLayout()
        
        # Save chat button
        self.save_chat_btn = QPushButton("Save Chat")
        self.save_chat_btn.clicked.connect(self.save_chat_history)
        self.save_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 60px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 1px solid #777777;
            }
        """)
        
        # Load chat button
        self.load_chat_btn = QPushButton("Load Chat")
        self.load_chat_btn.clicked.connect(self.load_chat_history)
        self.load_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 60px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 1px solid #777777;
            }
        """)
        
        # Clear chat button
        self.clear_chat_btn = QPushButton("Clear Chat")
        self.clear_chat_btn.clicked.connect(self.clear_chat_history)
        self.clear_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 60px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 1px solid #777777;
            }
        """)
        
        history_layout.addWidget(self.save_chat_btn)
        history_layout.addWidget(self.load_chat_btn)
        history_layout.addWidget(self.clear_chat_btn)
        
        layout.addLayout(history_layout)
        
        # Advanced commands layout
        advanced_layout = QHBoxLayout()
        
        # Device info button
        self.device_info_btn = QPushButton("Get Device Info")
        self.device_info_btn.clicked.connect(self.get_device_info)
        self.device_info_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 60px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 1px solid #777777;
            }
        """)
        
        # Ping button
        self.ping_btn = QPushButton("Ping Device")
        self.ping_btn.clicked.connect(self.ping_device)
        self.ping_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666666;
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                min-width: 60px;
                font-size: 10pt;
            }
            
            QPushButton:hover {
                background-color: #5a5a5a;
                border: 1px solid #777777;
            }
        """)
        
        # IP address input for device commands
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Enter IP address...")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                padding: 5px;
                color: #ffffff;
            }
            
            QLineEdit:focus {
                border: 1px solid #777777;
            }
        """)
        
        advanced_layout.addWidget(self.ip_input)
        advanced_layout.addWidget(self.device_info_btn)
        advanced_layout.addWidget(self.ping_btn)
        
        layout.addLayout(advanced_layout)
        
        self.setLayout(layout)
        
    def check_ai_connection(self):
        """Check if Ollama is available and update status"""
        if self.ai_client.check_connection():
            self.connection_status.setText("✓ Connected to Ollama (gpt-oss:20b)")
            self.connection_status.setStyleSheet("color: green;")
            
            # Show available models
            models = self.ai_client.get_available_models()
            if models:
                model_names = [model['name'] for model in models]
                self.append_to_chat(f"Available models: {', '.join(model_names)}")
        else:
            self.connection_status.setText("✗ Ollama not connected. Please start Ollama service.")
            self.connection_status.setStyleSheet("color: red;")
    
    def save_chat_history(self):
        """Save the current chat history to a file"""
        try:
            # Ask user for a file location to save
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "Save Chat History", 
                os.path.join(os.path.expanduser("~"), "OnCamLogs", "chat_history.json"),
                "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                # Prepare chat data to save
                chat_data = {
                    "timestamp": str(datetime.now()),
                    "conversation": self.conversation_history[1:],  # Exclude system message
                    "chat_display_text": self.chat_display.toPlainText()
                }
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # Write to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(chat_data, f, indent=2, ensure_ascii=False)
                
                self.append_to_chat(f"Chat history saved to: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save chat history: {str(e)}")
    
    def load_chat_history(self):
        """Load chat history from a file"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Load Chat History", 
                os.path.join(os.path.expanduser("~"), "OnCamLogs"),
                "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
            )
            
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    chat_data = json.load(f)
                
                # Reset conversation history with system context
                self.conversation_history = [self.conversation_history[0]]  # Keep system message
                
                # Add loaded messages to conversation history (if available)
                if "conversation" in chat_data:
                    self.conversation_history.extend(chat_data["conversation"])
                
                # Display the chat text
                if "chat_display_text" in chat_data:
                    self.chat_display.setPlainText(chat_data["chat_display_text"])
                else:
                    # Fallback: reconstruct from conversation if chat text not saved
                    self.chat_display.clear()
                    for msg in chat_data.get("conversation", []):
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        self.append_to_chat(f"{role.capitalize()}: {content}")
                
                self.append_to_chat(f"Chat history loaded from: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load chat history: {str(e)}")
    
    def clear_chat_history(self):
        """Clear the current chat history"""
        reply = QMessageBox.question(
            self, 
            "Confirm Clear", 
            "Are you sure you want to clear the chat history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_display.clear()
            # Preserve system context in conversation history
            system_context = self.conversation_history[0]
            self.conversation_history = [system_context]
            self.append_to_chat("Chat history cleared. Ready for new conversation.")
    
    def get_device_info(self):
        """Get device information for the entered IP address"""
        ip_address = self.ip_input.text().strip()
        if not ip_address:
            self.append_to_chat("AI: Please enter an IP address to get device information.")
            return
        
        # Show progress
        self.append_to_chat(f"AI: Getting information for device at {ip_address}...")
        
        # Start background thread for device info
        self.device_info_thread = DeviceInfoWorker(self.ai_client, ip_address)
        self.device_info_thread.finished.connect(self.on_device_info_result)
        self.device_info_thread.start()
    
    def ping_device(self):
        """Ping the entered IP address"""
        ip_address = self.ip_input.text().strip()
        if not ip_address:
            self.append_to_chat("AI: Please enter an IP address to ping.")
            return
        
        # Show progress
        self.append_to_chat(f"AI: Pinging {ip_address}...")
        
        # Start background thread for ping
        self.ping_thread = PingWorker(self.ai_client, ip_address)
        self.ping_thread.finished.connect(self.on_ping_result)
        self.ping_thread.start()
    
    def on_device_info_result(self, result):
        """Handle device info result"""
        self.append_to_chat(f"AI: Device info for {self.ip_input.text()}:\n{result}")
    
    def on_ping_result(self, result):
        """Handle ping result"""
        self.append_to_chat(f"AI: Ping result for {self.ip_input.text()}:\n{result}")
    
    def send_message(self):
        """Send message to AI and get response"""
        user_input = self.input_field.text().strip()
        if not user_input:
            return
            
        # Add user message to conversation
        self.append_to_chat(f"You: {user_input}")
        
        # Update conversation history
        self.conversation_history.append({"role": "user", "content": user_input})
        
        self.input_field.clear()
        
        # Disable input while processing
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        
        # Start background thread for AI processing with current conversation history
        self.ai_thread = AIWorker(self.ai_client, user_input, self.conversation_history)
        self.ai_thread.finished.connect(self.on_ai_response)
        self.ai_thread.start()
    
    def on_ai_response(self, response):
        """Handle response from AI"""
        if response:
            self.append_to_chat(f"AI: {response}")
            # Update conversation history
            self.conversation_history.append({"role": "assistant", "content": response})
        else:
            self.append_to_chat("AI: Sorry, I couldn't process that request.")
        
        # Re-enable input
        self.input_field.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_field.setFocus()
    
    def append_to_chat(self, text):
        """Append text to the chat display"""
        current_text = self.chat_display.toPlainText()
        if current_text:
            self.chat_display.setPlainText(current_text + "\n\n" + text)
        else:
            self.chat_display.setPlainText(text)
        
        # Auto-scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class AIWorker(QThread):
    """Background worker for AI processing to prevent UI freezing"""
    finished = pyqtSignal(str)
    
    def __init__(self, ai_client, user_input, conversation_history):
        super().__init__()
        self.ai_client = ai_client
        self.user_input = user_input
        self.conversation_history = conversation_history
        
    def run(self):
        """Process the AI request in background"""
        try:
            # Use the chat method which is better for conversation context
            response = self.ai_client.chat(self.conversation_history)
            self.finished.emit(response or "Sorry, I couldn't process that request.")
        except Exception as e:
            print(f"Error in AI worker: {e}")
            self.finished.emit("An error occurred while processing your request.")


class DeviceInfoWorker(QThread):
    """Background worker for device info to prevent UI freezing"""
    finished = pyqtSignal(str)
    
    def __init__(self, ai_client, ip_address):
        super().__init__()
        self.ai_client = ai_client
        self.ip_address = ip_address
        
    def run(self):
        """Get device info in background"""
        try:
            result = self.ai_client.get_device_info(self.ip_address)
            self.finished.emit(result)
        except Exception as e:
            print(f"Error in device info worker: {e}")
            self.finished.emit(f"Error getting device info: {str(e)}")


class PingWorker(QThread):
    """Background worker for ping to prevent UI freezing"""
    finished = pyqtSignal(str)
    
    def __init__(self, ai_client, ip_address):
        super().__init__()
        self.ai_client = ai_client
        self.ip_address = ip_address
        
    def run(self):
        """Ping in background"""
        try:
            result = self.ai_client.ping_device(self.ip_address)
            self.finished.emit(result)
        except Exception as e:
            print(f"Error in ping worker: {e}")
            self.finished.emit(f"Error pinging device: {str(e)}")