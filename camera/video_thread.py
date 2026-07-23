import cv2
import time
import numpy as np
import traceback
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

# Import config manager to access camera settings
from camera.config_manager import config_manager
from core.yolo_tracker import YOLOTracker

class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(object, int)  # Signal with frame and camera id
    connection_status_signal = pyqtSignal(str)  # Signal for connection status updates
    detection_stats_signal = pyqtSignal(int, int)  # Signal for detection stats (detected objects, tracked objects)

    def __init__(self, rtsp_url, camera_id):
        super().__init__()
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self._run_flag = True
        self.cap = None
        
        # YOLO detection settings
        self.detection_enabled = False
        self.tracking_enabled = False
        self.confidence_threshold = 0.5
        self.iou_threshold = 0.4
        self.selected_classes = []  # Track selected classes
        
        # Initialize YOLO tracker
        try:
            self.yolo_tracker = YOLOTracker(conf_threshold=self.confidence_threshold, iou_threshold=self.iou_threshold)
        except Exception as e:
            print(f"[ERROR] Error initializing YOLO tracker: {e}")
            self.yolo_tracker = None

    def run(self):
        # Check if we have a valid URL to connect to
        if not self.rtsp_url or "dummy" in self.rtsp_url or not self.rtsp_url.startswith(('rtsp://', 'rtmp://', 'http://', 'https://')):
            error_msg = f"Invalid or dummy URL for Camera {self.camera_id}: {self.rtsp_url}"
            print(f"[ERROR] {error_msg}")
            self.connection_status_signal.emit(f"Error: Invalid or missing URL for Camera {self.camera_id}")
            # Wait for the flag to stop if we don't have a valid URL
            while self._run_flag:
                time.sleep(0.1)
            return
        
        print(f"[LOG] Starting VideoThread for Camera {self.camera_id} with URL: {self.rtsp_url}")
        self.connection_status_signal.emit(f"Initializing connection for Camera {self.camera_id}...")
        
        # Get camera configuration from config manager
        camera_config = config_manager.get_camera_config(f"camera{self.camera_id}")
        fps = camera_config.get("fps", 15 if self.camera_id != 2 else 25)  # Default fps
        encoding = camera_config.get("encoding", "H264" if self.camera_id == 2 else "MJPG")  # Default encoding
        resolution_width = camera_config.get("resolution_width", 1024 if self.camera_id == 2 else 640)  # Default width
        resolution_height = camera_config.get("resolution_height", 768 if self.camera_id == 2 else 480)  # Default height
        
        # Determine if this is a thermal camera based on the URL or config
        is_thermal_camera = self.camera_id == 2 or "thermal" in self.rtsp_url.lower() or "therm" in self.rtsp_url.lower()
        print(f"[LOG] Camera {self.camera_id} identified as thermal: {is_thermal_camera}")
        print(f"[LOG] Using settings - FPS: {fps}, Encoding: {encoding}, Resolution: {resolution_width}x{resolution_height}")
        
        # Set thermal camera specific parameters based on config
        if is_thermal_camera:
            initial_timeout = 15  # 15 seconds for thermal camera initial connection
            buffer_size = 1  # Minimal buffering
            print(f"[LOG] Using thermal camera settings - timeout: {initial_timeout}s, buffer: {buffer_size}")
        else:
            initial_timeout = 10  # 10 seconds for regular cameras
            buffer_size = 1  # Minimal buffering
            print(f"[LOG] Using regular camera settings - timeout: {initial_timeout}s, buffer: {buffer_size}")
            
        reconnect_delay = 0.1  # Start with minimal delay for faster initial connection
        
        while self._run_flag:
            try:
                print(f"[LOG] Attempting to connect to Camera {self.camera_id}")
                
                # Attempt to disable OpenCL to prevent certain backend issues, but safely check if function exists
                if hasattr(cv2, 'ocl_setUseOpenCL'):
                    cv2.ocl_setUseOpenCL(False)  # Disable OpenCL to avoid some issues
                    print(f"[LOG] OpenCL disabled for Camera {self.camera_id}")
                
                # For thermal cameras, we need special handling based on the provided specs
                if is_thermal_camera:
                    print(f"[LOG] Initializing thermal camera {self.camera_id} with settings from config")
                    
                    # Set environment variables that can help with thermal camera RTSP streams
                    import os
                    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|timeout;15000000'  # Use TCP transport for RTSP and set timeout to 15s
                    print(f"[LOG] Set OpenCV FFMPEG capture options for thermal camera")
                    
                    # Create VideoCapture with camera-specific optimized settings
                    self.cap = cv2.VideoCapture()
                    
                    # Prepare list of codecs to try based on config
                    preferred_codec = encoding
                    codecs_to_try = []
                    
                    # Put the preferred codec first
                    codecs_to_try.append(cv2.VideoWriter_fourcc(*preferred_codec))
                    
                    # Add fallback codecs
                    if preferred_codec != 'H264':
                        codecs_to_try.append(cv2.VideoWriter_fourcc(*'H264'))
                    if preferred_codec != 'MJPG':
                        codecs_to_try.append(cv2.VideoWriter_fourcc(*'MJPG'))
                    if preferred_codec != 'MP4V':
                        codecs_to_try.append(cv2.VideoWriter_fourcc(*'MP4V'))
                    if preferred_codec != 'X264':
                        codecs_to_try.append(cv2.VideoWriter_fourcc(*'X264'))
                    
                    connected = False
                    for i, codec in enumerate(codecs_to_try):
                        try:
                            print(f"[LOG] Trying codec {i+1}/{len(codecs_to_try)} for thermal camera {self.camera_id}: {codec}")
                            
                            # Set the codec
                            self.cap.set(cv2.CAP_PROP_FOURCC, codec)
                            self.cap.set(cv2.CAP_PROP_FPS, fps)
                            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution_width)
                            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution_height)
                            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)
                            
                            print(f"[LOG] Codec settings applied, attempting to open RTSP stream: {self.rtsp_url}")
                            
                            # Attempt to open the RTSP stream
                            self.cap.open(self.rtsp_url)
                            
                            # Wait a bit for the connection to establish
                            time.sleep(2)
                            
                            # Test if we can read a frame
                            print(f"[LOG] Testing frame read for thermal camera {self.camera_id}")
                            # Check if self.cap is valid before trying to read
                            if self.cap is not None:
                                ret, test_frame = self.cap.read()
                                print(f"[LOG] Frame read result for thermal camera {self.camera_id}: ret={ret}, frame_valid={test_frame is not None and test_frame.size > 0 if test_frame is not None else 'None'}")
                            else:
                                print(f"[LOG] FAILED: self.cap is None for thermal camera {self.camera_id}")
                                ret = False
                                test_frame = None

                            if ret and test_frame is not None and test_frame.size > 0:
                                print(f"[LOG] SUCCESS: Connected to thermal camera {self.camera_id} with codec {codec}")
                                connected = True
                                break
                            else:
                                print(f"[LOG] FAILED: Codec {codec} didn't return valid frames for thermal camera {self.camera_id}")
                                if self.cap is not None:
                                    self.cap.release()
                                
                        except Exception as e:
                            print(f"[LOG] ERROR: Exception trying codec {codec} for thermal camera {self.camera_id}: {str(e)}")
                            # Check if self.cap exists before calling isOpened
                            if self.cap is not None and self.cap.isOpened():
                                self.cap.release()
                    
                    if not connected:
                        # If codec-specific attempts failed, try generic connection
                        print(f"[LOG] Falling back to generic connection for thermal camera {self.camera_id}")
                        self.cap = cv2.VideoCapture(self.rtsp_url)
                        
                        # Set the config values after opening
                        self.cap.set(cv2.CAP_PROP_FPS, fps)
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution_width)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution_height)
                        
                        # Test connection
                        time.sleep(2)  # Wait for connection to establish
                        # Check if self.cap is valid before trying to read
                        if self.cap is not None:
                            ret, test_frame = self.cap.read()
                            print(f"[LOG] Generic connection test result: ret={ret}, frame_valid={test_frame is not None and test_frame.size > 0 if test_frame is not None else 'None'}")
                        else:
                            print(f"[LOG] FAILED: self.cap is None for thermal camera {self.camera_id}")
                            ret = False
                            test_frame = None
                        if not (ret and test_frame is not None and test_frame.size > 0):
                            raise Exception(f"Could not establish connection to thermal camera {self.camera_id}")
                
                else:
                    # For regular cameras, use the standard approach
                    print(f"[LOG] Initializing regular camera {self.camera_id}")
                    
                    # Attempt to create VideoCapture with different backends for compatibility
                    backends_to_try = [
                        cv2.CAP_FFMPEG,  # Primary choice for RTSP
                        cv2.CAP_GSTREAMER,  # Alternative for RTSP
                        cv2.CAP_ANY  # Generic fallback
                    ]
                    
                    connected = False
                    for i, backend in enumerate(backends_to_try):
                        try:
                            print(f"[LOG] Trying backend {i+1}/{len(backends_to_try)} for camera {self.camera_id}: {backend}")
                            self.cap = cv2.VideoCapture(self.rtsp_url, backend)
                            
                            # Set connection timeouts (if supported by backend)
                            self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, initial_timeout * 1000)  # Dynamic timeout based on camera type
                            self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, initial_timeout * 1000)  # Dynamic timeout
                            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, buffer_size)  # Reduce buffer to minimize latency
                            
                            # Set camera-specific properties
                            self.cap.set(cv2.CAP_PROP_FPS, fps)
                            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution_width)
                            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution_height)
                            
                            print(f"[LOG] Backend settings applied, testing connection for camera {self.camera_id}")
                            
                            # Verify connection by trying to read a frame
                            ret, test_frame = self.cap.read()
                            print(f"[LOG] Backend {backend} connection test result: ret={ret}, frame_valid={test_frame is not None and test_frame.size > 0 if test_frame is not None else 'None'}")
                            
                            if ret:
                                print(f"[LOG] SUCCESS: Connected to Camera {self.camera_id} using backend {backend}")
                                connected = True
                                break
                            else:
                                print(f"[LOG] FAILED: Backend {backend} failed to read frame for camera {self.camera_id}")
                                self.cap.release()
                                self.cap = None
                        except Exception as e:
                            print(f"[LOG] ERROR: Backend {backend} failed for camera {self.camera_id}: {str(e)}")
                            self.cap = None
                    
                    if not connected:
                        raise Exception(f"Could not open video stream for Camera {self.camera_id}")
                
                # At this point, we should have a working connection
                print(f"[LOG] VideoCapture initialization completed for Camera {self.camera_id}. isOpened: {self.cap.isOpened() if self.cap and hasattr(self.cap, 'isOpened') else False}")
                
                if not self.cap or not (self.cap and hasattr(self.cap, 'isOpened')) or not self.cap.isOpened():
                    raise Exception(f"VideoCapture not properly initialized for Camera {self.camera_id}")
                
                # Successfully opened, send first frame
                print(f"[LOG] Attempting to read first frame from Camera {self.camera_id}")
                # Check if self.cap is valid before attempting to read first frame
                if self.cap is not None:
                    ret, first_frame = self.cap.read()
                    print(f"[LOG] First frame read result for Camera {self.camera_id}: ret={ret}, frame_valid={first_frame is not None and first_frame.size > 0 if first_frame is not None else 'None'}")
                else:
                    ret = False
                    first_frame = None
                    print(f"[LOG] FAILED: self.cap is None when attempting first frame read for Camera {self.camera_id}")
                
                if ret and first_frame is not None and first_frame.size > 0:
                    print(f"[LOG] SUCCESS: First frame received from Camera {self.camera_id}, emitting signal")
                    self.change_pixmap_signal.emit(first_frame, self.camera_id)
                    self.connection_status_signal.emit(f"Successfully connected to Camera {self.camera_id} - Video feed established")
                    print(f"[LOG] Video feed from Camera {self.camera_id} is working!")
                else:
                    # If first frame read fails, try a few more times before giving up
                    print(f"[LOG] First frame read failed for Camera {self.camera_id}, trying {5} more times")
                    for attempt in range(5):
                        if not self._run_flag:
                            break
                        time.sleep(0.2)
                        # Check if self.cap is valid before attempting to read
                        if self.cap is not None:
                            ret, first_frame = self.cap.read()
                        else:
                            ret = False
                            first_frame = None
                        print(f"[LOG] Retry {attempt+1}/5 for Camera {self.camera_id}: ret={ret}, frame_valid={first_frame is not None and first_frame.size > 0 if first_frame is not None else 'None'}")
                        
                        if ret and first_frame is not None and first_frame.size > 0:
                            print(f"[LOG] SUCCESS: Frame received from Camera {self.camera_id} on attempt {attempt+1}")
                            self.change_pixmap_signal.emit(first_frame, self.camera_id)
                            self.connection_status_signal.emit(f"Successfully connected to Camera {self.camera_id} - Video feed established")
                            print(f"[LOG] Video feed from Camera {self.camera_id} is working after {attempt+1} attempts!")
                            break
                    else:
                        # If all attempts failed, raise exception to reconnect
                        error_msg = f"FAILURE: Could not read any frames from Camera {self.camera_id} after 5 attempts"
                        print(f"[ERROR] {error_msg}")
                        self.connection_status_signal.emit(f"Error: Camera {self.camera_id} - Failed to read initial frame")
                        error_details = {
                            'camera_id': self.camera_id,
                            'rtsp_url': self.rtsp_url,
                            'attempt': 'initial_frame_read',
                            'error': 'Failed to read initial frame',
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        self._show_error_message(error_details)
                        raise Exception(error_msg)
                
                # Main reading loop
                print(f"[LOG] Starting main reading loop for Camera {self.camera_id}")
                frame_read_failure_count = 0  # Counter for consecutive frame read failures
                last_successful_frame_time = time.time()  # Track when we last got a frame
                
                while self._run_flag:
                    try:
                        # Check if self.cap exists before attempting to read
                        if self.cap is not None:
                            ret, cv_img = self.cap.read()
                        else:
                            ret = False
                            cv_img = None
                            print(f"[LOG] self.cap is None in main reading loop for Camera {self.camera_id}")
                        
                        if ret and cv_img is not None and cv_img.size > 0:
                            # Reset failure counter on success
                            frame_read_failure_count = 0
                            last_successful_frame_time = time.time()
                            
                            # Process frame if detection is enabled
                            if self.detection_enabled and self.yolo_tracker:
                                try:
                                    # Update class filters if needed
                                    if self.selected_classes:
                                        self.yolo_tracker.set_allowed_classes(self.selected_classes)
                                    
                                    processed_frame, detections = self.yolo_tracker.process_frame(cv_img)
                                    detection_count = len(detections)
                                    tracking_count = len([d for d in detections if d.get('track_id')])
                                    self.detection_stats_signal.emit(detection_count, tracking_count)
                                    cv_img = processed_frame
                                except Exception as e:
                                    print(f"[ERROR] Error during YOLO processing: {e}")
                            
                            # Emit frame only if it's valid
                            self.change_pixmap_signal.emit(cv_img, self.camera_id)
                        else:
                            # Increment failure counter
                            frame_read_failure_count += 1
                            
                            # Calculate time since last successful frame
                            time_since_last_frame = time.time() - last_successful_frame_time
                            
                            # Log error but continue trying to read
                            print(f"[LOG] Failed to read frame from Camera {self.camera_id} (attempt #{frame_read_failure_count}), time since last frame: {time_since_last_frame:.1f}s")
                            
                            # If too many consecutive failures or too much time has passed, break to trigger reconnection
                            max_failures = 15 if is_thermal_camera else 8  # Increased failure tolerance
                            max_time_without_frame = 45  # Increased timeout to 45 seconds
                            
                            if frame_read_failure_count >= max_failures or time_since_last_frame > max_time_without_frame:
                                print(f"[LOG] RECONNECTING: Too many consecutive failures ({frame_read_failure_count}) or timeout ({time_since_last_frame:.1f}s) for Camera {self.camera_id}, triggering reconnection...")
                                break
                            
                    except Exception as e:
                        frame_read_failure_count += 1
                        print(f"[LOG] EXCEPTION: Error reading frame from Camera {self.camera_id}: {str(e)} (attempt #{frame_read_failure_count})")
                        
                        # If too many consecutive failures, break to trigger reconnection
                        if frame_read_failure_count >= 15:  # Increased threshold for error tolerance
                            error_msg = f"RECONNECTING: Too many consecutive errors for Camera {self.camera_id}, triggering reconnection..."
                            print(f"[ERROR] {error_msg}")
                            error_details = {
                                'camera_id': self.camera_id,
                                'rtsp_url': self.rtsp_url,
                                'attempt': 'frame_read',
                                'error': f'Consecutive read errors ({frame_read_failure_count})',
                                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                            }
                            self._show_error_message(error_details)
                            break
                        
            except Exception as e:
                error_msg = f"ERROR: Unhandled exception in Camera {self.camera_id}: {str(e)}"
                print(f"[ERROR] {error_msg}")
                print(f"[DEBUG] Exception traceback:\n{traceback.format_exc()}")
                
                error_details = {
                    'camera_id': self.camera_id,
                    'rtsp_url': self.rtsp_url,
                    'attempt': 'execution',
                    'error': str(e),
                    'traceback': traceback.format_exc(),
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                
                self.connection_status_signal.emit(f"Error: Camera {self.camera_id} - {str(e)[:50]}...")
                self._show_error_message(error_details)
                
            finally:
                if self.cap is not None:
                    try:
                        print(f"[LOG] Releasing capture for Camera {self.camera_id}")
                        self.cap.release()
                        self.cap = None
                    except Exception as e:
                        error_msg = f"ERROR: Error releasing capture for Camera {self.camera_id}: {str(e)}"
                        print(f"[ERROR] {error_msg}")
                        error_details = {
                            'camera_id': self.camera_id,
                            'rtsp_url': self.rtsp_url,
                            'attempt': 'release',
                            'error': str(e),
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        self._show_error_message(error_details)
                        
            # Wait before attempting to reconnect, but check _run_flag regularly
            if self._run_flag:
                self.connection_status_signal.emit(f"Reconnecting to Camera {self.camera_id} in {reconnect_delay} seconds...")
                print(f"[LOG] Attempting to reconnect to Camera {self.camera_id} in {reconnect_delay}s...")
                
                # Sleep in small steps so we can still react quickly to stop flag
                slept = 0.0
                step = 0.05  # Reduce step for more responsive stop
                while self._run_flag and slept < reconnect_delay:
                    time.sleep(step)
                    slept += step
                # Increase delay gradually to avoid excessive resource usage
                reconnect_delay = min(reconnect_delay * 1.5, 5.0)  # Max 5 seconds between retries
                
        self.connection_status_signal.emit(f"Disconnected from Camera {self.camera_id}")
        print(f"[LOG] Final disconnection from Camera {self.camera_id} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

    def stop(self):
        print(f"[LOG] Stopping VideoThread for Camera {self.camera_id} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._run_flag = False
        # Release the capture if it exists to stop any blocking operations
        if self.cap is not None:
            try:
                print(f"[LOG] Force releasing capture in stop() for Camera {self.camera_id}")
                self.cap.release()
                self.cap = None
            except Exception as e:
                print(f"[ERROR] Error releasing capture in stop(): {str(e)}")
                
        # Clean up YOLO tracker
        if self.yolo_tracker:
            try:
                print("[LOG] Cleaning up YOLO tracker resources")
                self.yolo_tracker.cleanup()
                self.yolo_tracker = None
            except Exception as e:
                print(f"[ERROR] Error cleaning up YOLO tracker: {str(e)}")
                
    def _show_error_message(self, error_details):
        """Display an error message to the user and log details"""
        try:
            # Emit error signal for logging or UI display
            self.error_signal.emit(error_details)
            
            # Create a detailed error message
            error_title = f"Camera {error_details['camera_id']} Error"
            base_message = f"An error occurred with camera {error_details['camera_id']}:\n{error_details.get('error', 'Unknown error')}"
            
            # Only show message box if we're not shutting down
            if self._run_flag:
                msg_box = QMessageBox()
                msg_box.setWindowTitle(error_title)
                msg_box.setText(base_message)
                msg_box.setDetailedText(f"RTSP URL: {error_details['rtsp_url']}\nAttempt: {error_details['attempt']}\nTimestamp: {error_details['timestamp']}")
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.exec()
        except Exception as e:
            print(f"[ERROR] Failed to display error message: {str(e)}")
            # As a last resort, just print the error details
            print(f"[ERROR DETAILS] {error_details}")
            
        # Don't wait synchronously to avoid blocking UI, let the thread finish naturally
        # Just signal it to stop and return immediately
            
    def set_detection_enabled(self, enabled):
        """Enable or disable YOLO detection"""
        self.detection_enabled = enabled
            
    def set_confidence_threshold(self, threshold):
        """Set confidence threshold for YOLO detection"""
        self.confidence_threshold = threshold
        if self.yolo_tracker:
            self.yolo_tracker.set_confidence_threshold(threshold)
                
    def set_iou_threshold(self, threshold):
        """Set IOU threshold for YOLO detection"""
        self.iou_threshold = threshold
        if self.yolo_tracker:
            self.yolo_tracker.set_iou_threshold(threshold)
                
    def set_tracking_enabled(self, enabled):
        """Enable or disable object tracking"""
        self.tracking_enabled = enabled
    
    def set_selected_classes(self, classes):
        """Set the list of class names or IDs to detect"""
        self.selected_classes = classes