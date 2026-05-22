import os
import sys
import tempfile
import shutil
import atexit
import time
import threading

try:
    from onvif import ONVIFCamera
    from onvif.exceptions import ONVIFError
except ImportError:
    print("ONVIF library not found. PTZ functions will be disabled.")
    ONVIFCamera = None
    ONVIFError = Exception

# Handle paths correctly for both script and executable modes
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# Initialize ONVIF schema directory
def setup_onvif_schema_dir():
    """Setup ONVIF schema directory to ensure XSD files are accessible"""
    # Create a temporary directory for ONVIF schemas
    temp_schema_dir = os.path.join(tempfile.gettempdir(), "onvif_schema")
    
    # If we're in PyInstaller environment, copy the schemas from the bundled resources
    if getattr(sys, 'frozen', False):
        # Check if schemas exist in the PyInstaller bundle
        bundled_schema_path = get_resource_path('schema')
        if os.path.exists(bundled_schema_path):
            # Copy bundled schemas to temp directory
            if os.path.exists(temp_schema_dir):
                shutil.rmtree(temp_schema_dir)
            shutil.copytree(bundled_schema_path, temp_schema_dir)
        else:
            # If bundled schemas don't exist, we'll create a basic structure
            os.makedirs(temp_schema_dir, exist_ok=True)
            ver10_dir = os.path.join(temp_schema_dir, 'ver10')
            os.makedirs(ver10_dir, exist_ok=True)
            schema_dir = os.path.join(ver10_dir, 'ver10', 'schema')
            os.makedirs(schema_dir, exist_ok=True)
    else:
        # In development mode, use the schema directory from the project
        project_schema_path = os.path.join(os.path.dirname(__file__), 'schema')
        if os.path.exists(project_schema_path):
            if os.path.exists(temp_schema_dir):
                shutil.rmtree(temp_schema_dir)
            shutil.copytree(project_schema_path, temp_schema_dir)
        else:
            # Create basic structure if not exists
            os.makedirs(temp_schema_dir, exist_ok=True)
            ver10_dir = os.path.join(temp_schema_dir, 'ver10')
            os.makedirs(ver10_dir, exist_ok=True)
            schema_dir = os.path.join(ver10_dir, 'schema')
            os.makedirs(schema_dir, exist_ok=True)
    
    # Set environment variable that ONVIF/zeep might use
    os.environ['XSD_PATH'] = temp_schema_dir
    
    # Register cleanup function to remove temp directory on exit
    def cleanup():
        try:
            if os.path.exists(temp_schema_dir):
                shutil.rmtree(temp_schema_dir, ignore_errors=True)
        except Exception as e:
            print(f"Error cleaning up temp schema directory: {e}")
    
    atexit.register(cleanup)
    
    return temp_schema_dir

# WSDL files path
WSDL_PATH = get_resource_path('wsdl')

def resolve_wsdl_path():
    """Return valid wsdl path if exists, else None."""
    candidates = [
        WSDL_PATH,
        os.path.join(os.path.abspath("."), "wsdl"),
        os.path.join(os.path.dirname(__file__), "wsdl"),
        os.path.join(os.path.abspath("."), "wsdl_pkg"),  # packaged full wsdl schemas
        os.path.join(os.path.dirname(__file__), "wsdl_pkg"),
    ]
    for p in candidates:
        try:
            if p and os.path.exists(p) and os.path.isdir(p):
                # ensure required files present
                needed = {"devicemgmt.wsdl", "media.wsdl", "ptz.wsdl"}
                existing = set(os.listdir(p))
                if needed.issubset(existing):
                    return p
        except Exception:
            continue
    return None

class PTZController:
    def __init__(self, ip, port=80, username="", password=""):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.cam = None
        self.media_service = None
        self.ptz_service = None
        self.media_profile = None
        self.profiles = None
        self.initialized = False
        self.connected = False
        self.speed = 10  # Default speed
        
        # Setup ONVIF schema directory
        self.schema_dir = setup_onvif_schema_dir()
        
    def init_ptz_services(self):
        """Initialize PTZ services with proper schema handling"""
        try:
            from onvif import ONVIFCamera
            from onvif.exceptions import ONVIFError
            
            # Resolve WSDL path
            actual_wsdl_path = resolve_wsdl_path()
            
            # Initialize ONVIF camera
            if actual_wsdl_path:
                self.cam = ONVIFCamera(self.ip, self.port, self.username, self.password, actual_wsdl_path)
            else:
                print("WSDL not found, using default ONVIF init")
                self.cam = ONVIFCamera(self.ip, self.port, self.username, self.password)
        
            # Create media service
            self.media_service = self.cam.create_media_service()
            profiles = self.media_service.GetProfiles()
            if profiles:
                self.media_profile = profiles[0]  # Use first profile
                
                # Create PTZ service
                self.ptz_service = self.cam.create_ptz_service()
                
                self.connected = True
                self.initialized = True
                print(f"ONVIF services initialized for {self.ip}")
            else:
                print(f"No media profiles found for {self.ip}")
                self.initialized = False
                
        except ONVIFError as e:
            error_msg = f"ONVIF error initializing services for {self.ip}: {str(e)}"
            print(error_msg)
            self.initialized = False
        except Exception as e:
            error_msg = f"Failed to initialize ONVIF services for {self.ip}: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            self.initialized = False

    def init_ptz(self):
        """Initialize PTZ with proper schema handling"""
        try:
            # Run initialization in separate thread to prevent blocking UI
            init_thread = threading.Thread(target=self._init_ptz_thread, daemon=True)
            init_thread.start()
            
        except Exception as e:
            error_msg = f"Failed to initialize PTZ for {self.ip}: {str(e)}"
            print(error_msg)
    
    def _init_ptz_thread(self):
        """Thread for initializing PTZ services"""
        try:
            # Call the actual initialization method
            self.init_ptz_services()
        except Exception as e:
            error_msg = f"Failed to initialize PTZ for {self.ip} in thread: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            self.initialized = False

    def move(self, direction):
        """Move camera using either existing PTZ connection or direct ONVIF control"""
        if not self.initialized or not self.cam:
            msg = f"PTZ not initialized for camera {self.ip}"
            print(msg)
            
            # Try to use direct ONVIF control
            try:
                move_thread = threading.Thread(target=self._direct_move_thread, args=(direction,), daemon=True)
                move_thread.start()
                print(f"Direct ONVIF move thread started for direction: {direction}")
            except Exception as e:
                error_msg = f"Error starting direct move thread: {str(e)}"
                print(error_msg)
        else:
            # Use existing PTZ connection
            try:
                # Run movement in separate thread to prevent blocking UI
                move_thread = threading.Thread(target=self._move_thread, args=(direction,), daemon=True)
                move_thread.start()
                print(f"Move thread started for direction: {direction}")
            except Exception as e:
                error_msg = f"Error starting move thread: {str(e)}"
                print(error_msg)

    def _move_thread(self, direction):
        """Handle movement with existing PTZ connection"""
        try:
            # Check if services are properly initialized before using them
            if not self.initialized or not self.ptz_service or not self.media_profile or not self.cam:
                raise Exception("PTZ service or media profile not properly initialized")
                
            # Create PTZ movement request
            request = self.ptz_service.create_type('ContinuousMove')
            request.ProfileToken = self.media_profile.token
            
            # Set velocity based on direction
            velocity = {
                'PanTilt': {'x': 0.0, 'y': 0.0},
                'Zoom': {'x': 0.0}
            }
            speed = 0.5
            
            if direction == 'up':
                velocity['PanTilt']['y'] = speed
            elif direction == 'down':
                velocity['PanTilt']['y'] = -speed
            elif direction == 'left':
                velocity['PanTilt']['x'] = -speed
            elif direction == 'right':
                velocity['PanTilt']['x'] = speed
            else:
                raise Exception(f"Invalid movement direction: {direction}")
                
            request.Velocity = velocity
            self.ptz_service.ContinuousMove(request)
            
            msg = f"Moving {direction} on camera {self.ip}"
            print(msg)
            
        except Exception as e:
            error_msg = f"Error moving {direction}: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()

    def _direct_move_thread(self, direction):
        """Handle movement via direct ONVIF connection when no existing PTZ connection is available"""
        try:
            # Import required modules
            from onvif import ONVIFCamera
            from onvif.exceptions import ONVIFError
            
            # Setup schema directory again if needed
            schema_dir = setup_onvif_schema_dir()
            
            wsdl_path = resolve_wsdl_path()
            
            # Create camera instance (with wsdl if found, else default)
            if wsdl_path:
                cam = ONVIFCamera(self.ip, self.port, self.username, self.password, wsdl_path)
            else:
                print("WSDL not found, using default ONVIF init for movement")
                cam = ONVIFCamera(self.ip, self.port, self.username, self.password)
            
            # Create media service
            media_service = cam.create_media_service()
            profiles = media_service.GetProfiles()
            if not profiles:
                print(f"No media profiles found for camera {self.ip}")
                return
            media_profile = profiles[0]  # Use first profile
            
            # Create PTZ service
            ptz_service = cam.create_ptz_service()
            
            # Create PTZ movement request
            request = ptz_service.create_type('ContinuousMove')
            request.ProfileToken = media_profile.token
            
            # Set velocity based on direction
            velocity = {
                'PanTilt': {'x': 0.0, 'y': 0.0},
                'Zoom': {'x': 0.0}
            }
            speed = 0.5
            
            if direction == 'up':
                velocity['PanTilt']['y'] = speed
            elif direction == 'down':
                velocity['PanTilt']['y'] = -speed
            elif direction == 'left':
                velocity['PanTilt']['x'] = -speed
            elif direction == 'right':
                velocity['PanTilt']['x'] = speed
            
            request.Velocity = velocity
            ptz_service.ContinuousMove(request)
            
            msg = f"Moving {direction} on camera {self.ip} directly"
            print(msg)
            
        except ONVIFError as e:
            error_msg = f"ONVIF error moving {direction} on {self.ip}: {str(e)}"
            print(error_msg)
        except Exception as e:
            error_msg = f"Error moving {direction} on {self.ip}: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
    
    def stop_move(self):
        # Run stop in separate thread to prevent blocking UI
        stop_thread = threading.Thread(target=self._stop_thread, daemon=True)
        stop_thread.start()
    
    def _stop_thread(self):
        try:
            # Check if services are properly initialized before using them
            if not self.initialized or not self.ptz_service or not self.media_profile or not self.cam:
                print("PTZ service or media profile not properly initialized, skipping stop")
                return
                
            request = self.ptz_service.create_type('Stop')
            request.ProfileToken = self.media_profile.token
            request.PanTilt = True
            request.Zoom = True
            self.ptz_service.Stop(request)
            
            msg = f"Movement stopped on camera {self.ip}"
            print(msg)
        except Exception as e:
            error_msg = f"Error stopping movement on {self.ip}: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
    
    def zoom(self, direction):
        """Start zooming camera in specified direction"""
        print(f"Zoom method called with direction: {direction}")
        
        # Start continuous zoom; stop will be triggered explicitly
        try:
            print(f"Starting direct ONVIF zoom for {direction}")
            zoom_thread = threading.Thread(target=self._start_direct_zoom_thread, args=(direction,), daemon=True)
            zoom_thread.start()
            print(f"Direct ONVIF zoom thread started for direction: {direction}")
        except Exception as e:
            error_msg = f"Error starting direct zoom thread: {str(e)}"
            print(error_msg)
    
    def _start_direct_zoom_thread(self, direction):
        """Start zooming using direct ONVIF control in a separate thread"""
        try:
            # Import required modules
            from onvif import ONVIFCamera
            from onvif.exceptions import ONVIFError
            
            # Try to reuse initialized services first
            ptz_service = self.ptz_service
            media_profile = self.media_profile
            
            if not self.initialized or not ptz_service or not media_profile:
                # Setup schema directory again if needed
                schema_dir = setup_onvif_schema_dir()
                
                wsdl_path = resolve_wsdl_path()
                if wsdl_path:
                    cam = ONVIFCamera(self.ip, self.port, self.username, self.password, wsdl_path)
                else:
                    print("WSDL not found, using default ONVIF init for zoom")
                    try:
                        cam = ONVIFCamera(self.ip, self.port, self.username, self.password)
                    except Exception as e:
                        print(f"Failed to create ONVIF camera without WSDL: {str(e)}")
                        return
                media_service = cam.create_media_service()
                profiles = media_service.GetProfiles()
                if not profiles:
                    print(f"No media profiles found for camera {self.ip}")
                    return
                media_profile = profiles[0]
                ptz_service = cam.create_ptz_service()
            
            # Create PTZ movement request
            request = ptz_service.create_type('ContinuousMove')
            if media_profile:
                request.ProfileToken = media_profile.token
            else:
                print("No media profile available for zoom command")
                return
            
            velocity = {
                'PanTilt': {'x': 0.0, 'y': 0.0},
                'Zoom': {'x': 0.0}
            }
            # Maximum zoom speed for best responsiveness
            speed = 1.0
            
            if direction == 'in':
                velocity['Zoom']['x'] = speed
            elif direction == 'out':
                velocity['Zoom']['x'] = -speed
            else:
                raise Exception(f"Invalid zoom direction: {direction}")
                
            request.Velocity = velocity
            ptz_service.ContinuousMove(request)
            
            msg = f"Zoom {direction} command sent to camera {self.ip}"
            print(msg)
                
        except ONVIFError as e:
            error_msg = f"ONVIF error controlling zoom for {self.ip}: {str(e)}"
            print(error_msg)
        except Exception as e:
            error_msg = f"Failed to control camera {self.ip} directly: {str(e)}"
            print(error_msg)

    def stop_zoom(self):
        """Stop zooming operation"""
        stop_thread = threading.Thread(target=self._stop_zoom_thread, daemon=True)
        stop_thread.start()
    
    def _stop_zoom_thread(self):
        """Stop zooming operation in a separate thread"""
        try:
            from onvif import ONVIFCamera
            from onvif.exceptions import ONVIFError
            
            ptz_service = self.ptz_service
            media_profile = self.media_profile
            
            if not self.initialized or not ptz_service or not media_profile:
                # Setup schema directory again if needed
                schema_dir = setup_onvif_schema_dir()
                
                wsdl_path = resolve_wsdl_path()
                if wsdl_path:
                    cam = ONVIFCamera(self.ip, self.port, self.username, self.password, wsdl_path)
                else:
                    print("WSDL not found, using default ONVIF init for stop_zoom")
                    try:
                        cam = ONVIFCamera(self.ip, self.port, self.username, self.password)
                    except Exception as e:
                        print(f"Failed to create ONVIF camera without WSDL for stop_zoom: {str(e)}")
                        return
                media_service = cam.create_media_service()
                profiles = media_service.GetProfiles()
                if not profiles:
                    print(f"No media profiles found for camera {self.ip} during stop_zoom")
                    return
                media_profile = profiles[0]
                ptz_service = cam.create_ptz_service()
            
            if ptz_service and media_profile:
                stop_request = ptz_service.create_type('Stop')
                stop_request.ProfileToken = media_profile.token
                stop_request.PanTilt = False
                stop_request.Zoom = True
                ptz_service.Stop(stop_request)
                msg = f"Stop zoom command sent to camera {self.ip}"
                print(msg)
            else:
                print("PTZ service not available for stop_zoom")
        except ONVIFError as e:
            error_msg = f"ONVIF error stopping zoom for {self.ip}: {str(e)}"
            print(error_msg)
        except Exception as e:
            error_msg = f"Error stopping zoom: {str(e)}"
            print(error_msg)
    
    def close(self):
        """Clean up resources"""
        try:
            if self.cam:
                # ONVIFCamera doesn't have explicit close method, but we can clean up references
                self.ptz_service = None
                self.media_service = None
                self.cam = None
                self.media_profile = None
                self.profiles = None
            self.initialized = False
        except Exception as e:
            print(f"Error closing PTZ controller: {str(e)}")