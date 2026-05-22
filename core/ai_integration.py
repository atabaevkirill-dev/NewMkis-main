import requests
import json
import platform
import psutil
import socket
import subprocess
import re
from datetime import datetime
from typing import Dict, Optional, List, Any


class OllamaAI:
    """
    Integration with Ollama for AI capabilities.
    Uses the locally downloaded gpt-oss:20b model.
    """
    
    def __init__(self, host: str = "localhost", port: int = 11434):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.model_name = "gpt-oss:20b"
        
    def _make_request(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Make a request to the Ollama API
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)  # Increased timeout
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with Ollama API: {e}")
            return None
    
    def generate_response(self, prompt: str, context: Optional[List[Dict[str, str]]] = None, temperature: float = 0.7) -> Optional[str]:
        """
        Generate a response from the AI model based on the prompt
        """
        # Enhanced context with application-specific information
        enhanced_prompt = self._build_enhanced_prompt(prompt)
        
        payload = {
            "model": self.model_name,
            "prompt": enhanced_prompt,
            "context": context or [],
            "options": {
                "temperature": temperature
            },
            "stream": False  # We want the full response
        }
        
        result = self._make_request("/api/generate", payload)
        
        if result and "response" in result:
            return result["response"]
        return None
    
    def _build_enhanced_prompt(self, user_prompt: str) -> str:
        """
        Build a prompt with application-specific context
        """
        # Gather system information to inject into the context
        system_context = self._get_system_context()
        
        app_context = """
        You are an AI assistant for the OnCam application, a lightweight camera monitoring and PTZ control application.
        
        Application overview:
        - Purpose: Camera monitoring with PTZ (Pan-Tilt-Zoom) control
        - Features: Dual RTSP video streams, ONVIF PTZ control, Pelco-D serial protocol support
        - UI Elements: Crosshairs overlay, fullscreen toggle, PTZ controls, flip/invert controls
        - Keyboard shortcuts: Ctrl+X (crosshairs), Ctrl+P (PTZ controls), Ctrl+I (invert tilt), F11 (fullscreen)
        - Configuration: Stored in OnCamLogs/config.json with camera IPs, credentials, ports, etc.
        
        Device Info Fields:
        - Date, Product Name, Serial Number, IP Address, Port, Login, Password
        
        PTZ Controls:
        - Supports both ONVIF and Pelco-D protocols
        - Manual controls: direction buttons, speed sliders
        - Auto modes: oscillation, scan patterns
        
        Video Streams:
        - Dual RTZ streams displayed side-by-side
        - Support for custom RTSP URLs
        - Adjustable FPS and resolution settings
        
        Network and Camera Expertise:
        - You have deep knowledge of IP cameras, network configurations, and thermal imaging systems
        - You can analyze network issues, suggest optimal configurations, and troubleshoot connectivity
        - You understand RTSP, ONVIF, HTTP/HTTPS protocols in relation to IP cameras
        - You know thermal imaging specifics including sensitivity, temperature ranges, and image processing
        
        ASCII Graph Visualization:
        - You can create simple ASCII graphs to visualize data such as network performance, camera FPS, or other metrics
        - Example of ASCII visualization: 
            Performance Chart:
            100% | ██
             80% | ██████
             60% | ████████
             40% | ██████████
             20% | ████████████
              0% |██████████████
                  Time
        
        Networking Commands:
        - You can provide commands for pinging devices, checking network status, and troubleshooting connections
        - You know how to interpret ping results, network latencies, and bandwidth limitations
        
        Device Information:
        - You can describe how to get detailed information about IP cameras and thermal imaging devices
        - You know vendor-specific implementations and their differences
        
        Your role is to assist users with:
        - Configuration of cameras and PTZ devices
        - Troubleshooting connection issues
        - Understanding application features and controls
        - Providing guidance on best practices
        - Answering questions about device compatibility
        - Creating visualizations of network or performance data
        - Suggesting network optimizations
        - Interpreting device information and logs
        """
        
        return f"{system_context}\n\n{app_context}\n\nUser Question: {user_prompt}\n\nPlease provide a helpful response based on the OnCam application context and your expertise in networking, IP cameras, and thermal imaging systems."
    
    def _get_system_context(self) -> str:
        """Get system context information to inject into AI requests"""
        try:
            # Get computer system information
            uname = platform.uname()
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            
            system_info = f"""
System Information:
OS: {uname.system} {uname.release} ({uname.version})
Machine: {uname.machine}
Processor: {uname.processor}
Boot Time: {boot_time.strftime('%Y-%m-%d %H:%M:%S')}
Hostname: {socket.gethostname()}
Local IP: {self._get_local_ip()}
Total RAM: {round(psutil.virtual_memory().total / (1024**3), 2)} GB
Available RAM: {round(psutil.virtual_memory().available / (1024**3), 2)} GB
CPU Cores (Logical): {psutil.cpu_count(logical=True)}
CPU Cores (Physical): {psutil.cpu_count(logical=False)}
Network Interfaces: {self._get_network_interfaces()}
            """.strip()
            
            return system_info
        except Exception as e:
            print(f"Error getting system info: {e}")
            return "System information unavailable"
    
    def _get_network_interfaces(self) -> str:
        """Get network interfaces information"""
        try:
            interfaces = []
            for interface, addresses in psutil.net_if_addrs().items():
                for addr in addresses:
                    if addr.family == socket.AF_INET:
                        interfaces.append(f"{interface}: {addr.address}")
            return ", ".join(interfaces[:5])  # Return first 5 interfaces
        except Exception:
            return "Unable to retrieve"
    
    def _get_local_ip(self) -> str:
        """Get the local IP address of this machine"""
        try:
            # Connect to a remote server to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "Unable to determine"
    
    def ping_device(self, target: str, count: int = 4) -> str:
        """Ping a device and return the results"""
        try:
            # Determine the ping command based on the OS
            if platform.system().lower() == "windows":
                cmd = ["ping", "-n", str(count), target]
            else:
                cmd = ["ping", "-c", str(count), target]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout
        except subprocess.TimeoutExpired:
            return "Ping command timed out"
        except Exception as e:
            return f"Error executing ping: {str(e)}"
    
    def get_device_info(self, ip_address: str) -> str:
        """Get basic information about a device at the given IP address"""
        try:
            # Try to connect to common ports for IP cameras
            common_ports = [21, 22, 23, 80, 443, 554, 8080, 8000, 9000]
            open_ports = []
            
            for port in common_ports:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)  # 2 second timeout
                result = sock.connect_ex((ip_address, port))
                if result == 0:
                    open_ports.append(port)
                sock.close()
            
            info = f"Device at {ip_address} has the following ports open: {open_ports}\n"
            
            # Attempt to determine if it's a camera by checking common web interfaces
            if 80 in open_ports or 8080 in open_ports:
                info += f"Likely an IP camera or web-enabled device (ports 80/8080 open)\n"
            
            if 554 in open_ports:  # RTSP port
                info += f"Streaming device detected (RTSP port 554 open)\n"
                
            if 21 in open_ports:  # FTP
                info += f"FTP service available\n"
                
            if 22 in open_ports:  # SSH
                info += f"SSH service available\n"
            
            return info
        except Exception as e:
            return f"Error getting device info: {str(e)}"
    
    def create_ascii_graph(self, data: List[float], labels: List[str], title: str = "Graph") -> str:
        """Create an ASCII graph from the provided data"""
        if not data or not labels or len(data) != len(labels):
            return "Invalid data for graph creation"
        
        # Find the maximum value to scale the graph
        max_val = max(data) if data else 1
        if max_val == 0:
            max_val = 1
        
        # Create the graph
        graph_lines = [f"\n{title}:"]
        
        # Calculate the height of the bars
        max_height = 10  # Max height in characters
        for i, value in enumerate(data):
            bar_height = int((value / max_val) * max_height) if max_val > 0 else 0
            bar = "█" * bar_height
            label = labels[i] if i < len(labels) else f"Item {i}"
            graph_lines.append(f"{label:>10}: {bar} ({value})")
        
        # Add a baseline
        graph_lines.append(f"{'':>10} {'─' * max_height} 0-{max_val}")
        
        return "\n".join(graph_lines)
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> Optional[str]:
        """
        Chat with the AI model using a conversation history
        """
        # Enhance the last message with application context
        if messages:
            # Add system context as the first message if not present
            if not messages[0].get('role') == 'system':
                system_message = {
                    "role": "system",
                    "content": self._get_complete_system_context()
                }
                messages = [system_message] + messages
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "options": {
                "temperature": temperature
            },
            "stream": False
        }
        
        result = self._make_request("/api/chat", payload)
        
        if result and "message" in result:
            return result["message"]["content"]
        return None
    
    def _get_complete_system_context(self) -> str:
        """Get complete system and application context"""
        system_info = self._get_system_context()
        
        app_context = (
            "You are an AI assistant for the OnCam application, a lightweight camera monitoring and PTZ control application. "
            "You are a specialist in computer networks, IP cameras, and thermal imaging systems. "
            "Provide helpful responses about configuring cameras, PTZ controls, troubleshooting connections, and using application features. "
            "The application has dual RTSP video streams, ONVIF PTZ control, and Pelco-D serial protocol support. "
            "Key keyboard shortcuts include Ctrl+X (crosshairs), Ctrl+P (PTZ controls), Ctrl+I (invert tilt), and F11 (fullscreen). "
            "You have capabilities to create ASCII graphs, ping devices, and provide detailed device information. "
            "The application is running on the following system:\n\n"
            f"{system_info}"
        )
        
        return app_context
    
    def check_connection(self) -> bool:
        """
        Check if the Ollama service is available
        """
        try:
            # Try to get the list of models to verify connection
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def get_available_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get a list of available models
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
        except requests.exceptions.RequestException as e:
            print(f"Error getting models list: {e}")
            return None