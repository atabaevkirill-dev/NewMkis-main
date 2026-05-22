import cv2
import time
import threading
import struct  # Added missing import
from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor
import numpy as np


class VideoWidget(QLabel):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: black; border: 1px solid gray;")
        self.setMinimumSize(320, 240)
        self.crosshair_enabled = False
        self.crosshair_x = 0.5  # Normalized coordinates (0.0 to 1.0)
        self.crosshair_y = 0.5
        self.frame = None
        self.setMouseTracking(True)  # Enable mouse tracking
        self.last_zoom_time = 0  # Track last zoom time
        from camera.config_manager import config_manager
        self.zoom_delay = config_manager.get_controls_config().get("zoom_delay", 0.02)  # Minimum delay between zoom commands

    def resizeEvent(self, event):
        """Handle resize events to maintain crosshair position"""
        super().resizeEvent(event)
        # Repaint to maintain crosshair position
        self.update()

    def set_crosshair_enabled(self, enabled):
        self.crosshair_enabled = enabled
        if enabled:
            # Always set crosshair to center when enabling
            self.crosshair_x = 0.5
            self.crosshair_y = 0.5
        self.update()  # Trigger repaint

    def update_frame(self, frame):
        try:
            if frame is not None and frame.size > 0:
                # Store a copy of the frame to prevent access issues
                self.frame = frame.copy()
                self.update()  # Trigger repaint
            else:
                print(f"Received empty frame for camera")
        except Exception as e:
            print(f"Error updating frame: {str(e)}")

    def mousePressEvent(self, event):
        """Handle mouse click events to move crosshair and control PTZ"""
        if event.button() == Qt.MouseButton.LeftButton and self.crosshair_enabled:
            # Get click position
            click_x = event.position().x()
            click_y = event.position().y()
            
            # Calculate normalized coordinates (0.0 to 1.0)
            if self.width() > 0 and self.height() > 0:
                x_norm = click_x / self.width()
                y_norm = click_y / self.height()
                
                # Move crosshair to clicked position temporarily
                self.set_crosshair_position(x_norm, y_norm)
                
                # Send PTZ command to move to position
                self.move_to_position(x_norm, y_norm)
                
                # Move crosshair back to center after a brief moment
                def center_crosshair():
                    time.sleep(0.1)  # Brief delay to show the click position
                    self.set_crosshair_position(0.5, 0.5)
                
                threading.Thread(target=center_crosshair, daemon=True).start()
        
        super().mousePressEvent(event)

    def move_to_position(self, x_norm, y_norm):
        """Send PTZ command to move to normalized position"""
        # Run PTZ movement in separate thread to prevent blocking UI
        move_thread = threading.Thread(target=self._move_to_position_thread, args=(x_norm, y_norm), daemon=True)
        move_thread.start()
    
    def _move_to_position_thread(self, x_norm, y_norm):
        """Send PTZ command to move to normalized position in a separate thread"""
        # Get main window to access PTZ controllers
        main_window = self.window()
        
        # Always use Pelco-D controller if available
        if hasattr(main_window, 'pan_tilt_controller') and main_window.pan_tilt_controller.connected:
            ptz_controller = main_window.pan_tilt_controller
            is_pelco_device = True
        else:
            # Since we removed camera 1 PTZ panel, only camera 2 is available
            if self == main_window.video_widget2 and hasattr(main_window, 'ptz_controller2'):
                ptz_controller = main_window.ptz_controller2
                is_pelco_device = False
            else:
                QTimer.singleShot(0, lambda: main_window.status_bar.showMessage("No PTZ controller available", 3000))
                return
        
        # Convert normalized coordinates to PTZ movements
        # Center is (0.5, 0.5), so calculate offset from center
        x_offset = x_norm - 0.5
        y_offset = 0.5 - y_norm  # Invert Y axis (screen Y increases downward)
        
        if is_pelco_device:
            # Check if tilt inversion is enabled
            invert_tilt = ptz_controller.invert_tilt_checkbox.isChecked() if hasattr(ptz_controller, 'invert_tilt_checkbox') else False
            
            # Calculate distance from center
            distance = (x_offset**2 + y_offset**2)**0.5
            
            # For Pelco-D, we'll send proportional speed commands based on offset
            if abs(x_offset) > 0.01 or abs(y_offset) > 0.01:  # More sensitive detection
                # Calculate proportional speeds based on offsets
                # Scale factor to convert normalized offset to speed (0 to max speed)
                max_speed = ptz_controller.speed  # Use current speed setting as max
                pan_speed = int(abs(x_offset) * max_speed * 2)  # Multiply by 2 to increase sensitivity
                tilt_speed = int(abs(y_offset) * max_speed * 2)  # Multiply by 2 to increase sensitivity
                
                # Limit speed to max possible value (0x3F = 63 for Pelco-D)
                pan_speed = min(pan_speed, 0x3F)
                tilt_speed = min(tilt_speed, 0x3F)
                
                # Determine direction and send command with speed
                # Build command based on direction
                command1 = 0x00
                command2 = 0x00
                
                # Set pan direction and speed
                if x_offset > 0:  # Move right
                    command2 |= 0x02  # Pan right
                elif x_offset < 0:  # Move left
                    command2 |= 0x04  # Pan left
                
                # Set tilt direction and speed
                if y_offset > 0:  # Move up or down based on invert setting
                    if invert_tilt:
                        command2 |= 0x10  # Tilt down (inverted)
                    else:
                        command2 |= 0x08  # Tilt up
                else:  # Move down or up based on invert setting
                    if invert_tilt:
                        command2 |= 0x08  # Tilt up (inverted)
                    else:
                        command2 |= 0x10  # Tilt down
                
                # Calculate data bytes based on speeds
                data1 = pan_speed  # Speed for pan
                data2 = tilt_speed  # Speed for tilt
                
                # Calculate checksum
                address = ptz_controller.address_spin.value() if hasattr(ptz_controller, 'address_spin') else 0x01
                checksum = (address + command1 + command2 + data1 + data2) & 0xFF
                
                # Create and send packet directly
                packet = struct.pack('BBBBBBB', 0xFF, address, command1, command2, data1, data2, checksum)
                try:
                    ptz_controller.socket.send(packet)
                    print(f"Sent precise PTZ command: pan_speed={data1}, tilt_speed={data2}")
                except Exception as e:
                    print(f"Error sending precise PTZ command: {str(e)}")
                
                # Calculate movement time based on distance for more precise positioning
                # Longer distances need more time to reach target
                move_time = distance * 3.0  # Increased multiplier for better precision
                
                # Automatically stop after calculated time to reach target position
                def auto_stop():
                    time.sleep(move_time)
                    
                    # Stop movement after delay
                    ptz_controller._send_command_thread('stop')
                
                # Run auto-stop in separate thread so it doesn't block UI
                stop_thread = threading.Thread(target=auto_stop, daemon=True)
                stop_thread.start()
        else:
            # For ONVIF PTZ control - use AbsoluteMove for precise positioning
            if hasattr(ptz_controller, 'ptz_service') and ptz_controller.ptz_service and hasattr(ptz_controller, 'media_profile') and ptz_controller.media_profile:
                try:
                    # Get the current PTZ status to use as a baseline
                    status = ptz_controller.ptz_service.GetStatus({'ProfileToken': ptz_controller.media_profile.token})
                    
                    # Calculate absolute pan and tilt positions
                    # Assuming the current position is the center (0.5, 0.5) in the normalized coordinate system
                    current_position = getattr(status, 'Position', None)
                    
                    # Create absolute movement request
                    absolute_request = ptz_controller.ptz_service.create_type('AbsoluteMove')
                    absolute_request.ProfileToken = ptz_controller.media_profile.token
                    
                    # Set pan and tilt to absolute positions based on click coordinates
                    # Map normalized coordinates (0.0 to 1.0) to camera limits (typically -1.0 to 1.0)
                    pan_position = max(-1.0, min(1.0, (x_norm - 0.5) * 2))  # Convert 0-1 to -1 to 1
                    tilt_position = max(-1.0, min(1.0, (y_norm - 0.5) * 2))  # Convert 0-1 to -1 to 1
                    
                    # Create position space
                    absolute_request.Position = {
                        'PanTilt': {
                            'x': pan_position,
                            'y': tilt_position,
                            'space': 'http://www.onvif.org/ver10/tptz/PanTiltSpaces/PositionGenericSpace'
                        },
                        'Zoom': {'x': 0.0}
                    }
                    
                    # Send absolute move command
                    ptz_controller.ptz_service.AbsoluteMove(absolute_request)
                    
                    msg = f"Absolute move to position ({pan_position:.3f}, {tilt_position:.3f})"
                    print(msg)
                    QTimer.singleShot(0, lambda: main_window.status_bar.showMessage(msg, 3000))
                    
                except Exception as e:
                    # If AbsoluteMove is not supported, fallback to ContinuousMove
                    error_msg = f"AbsoluteMove failed: {str(e)}, falling back to ContinuousMove"
                    print(error_msg)
                    
                    # Calculate relative movement based on offset from center
                    pan_speed = x_offset * 0.5  # Scale factor for pan
                    tilt_speed = y_offset * 0.5  # Scale factor for tilt (already adjusted for screen coordinates)
                    
                    # Create movement request
                    request = ptz_controller.ptz_service.create_type('ContinuousMove')
                    request.ProfileToken = ptz_controller.media_profile.token
                    
                    # Set velocity based on calculated speeds
                    velocity = {
                        'PanTilt': {'x': pan_speed, 'y': tilt_speed},
                        'Zoom': {'x': 0.0}
                    }
                    request.Velocity = velocity
                    
                    # Send move command
                    ptz_controller.ptz_service.ContinuousMove(request)
                    
                    # Calculate movement time based on distance
                    move_time = abs(x_offset) * 4.0  # Adjust multiplier as needed
                    
                    # Automatically stop after calculated time
                    def auto_stop():
                        time.sleep(move_time)
                        
                        # Create stop request
                        stop_request = ptz_controller.ptz_service.create_type('Stop')
                        stop_request.ProfileToken = ptz_controller.media_profile.token
                        stop_request.PanTilt = True
                        stop_request.Zoom = False
                        
                        # Send stop command
                        ptz_controller.ptz_service.Stop(stop_request)
                    
                    # Run auto-stop in separate thread so it doesn't block UI
                    stop_thread = threading.Thread(target=auto_stop, daemon=True)
                    stop_thread.start()
            else:
                # If no PTZ service is available
                QTimer.singleShot(0, lambda: main_window.status_bar.showMessage("PTZ controller not initialized", 3000))
    
    def wheelEvent(self, event):
        """Handle mouse wheel events for zoom control"""
        try:
            print("Wheel event received")
            # Get current time
            current_time = time.time()
            
            # Check if enough time has passed since last zoom
            if current_time - self.last_zoom_time < self.zoom_delay:
                print("Too soon since last zoom, ignoring event")
                event.accept()
                return
            
            # Get the main window to access PTZ controllers
            main_window = self.window()
            
            # Prefer the primary ONVIF controller used by UI buttons (camera1)
            ptz_controller = getattr(getattr(main_window, "pan_tilt_controller", None), "camera1_ptz", None)
            if not ptz_controller:
                # Fallback to secondary controller if available
                ptz_controller = getattr(main_window, "ptz_controller2", None)
            
            if not ptz_controller:
                print("No PTZ controller available for wheel zoom")
                super().wheelEvent(event)
                return
            
            # Check if PTZ is initialized
            if not hasattr(ptz_controller, 'ptz_service') or not ptz_controller.ptz_service or not hasattr(ptz_controller, 'media_profile') or not ptz_controller.media_profile:
                print("PTZ controller not initialized")
                super().wheelEvent(event)
                return
            
            # Handle zoom based on wheel rotation
            delta = event.angleDelta().y()
            print(f"Wheel delta: {delta}")
            if delta > 0:
                print("Calling zoom('in')")
                ptz_controller.zoom('in')
                # Short controlled zoom burst, then stop
                def stop_zoom():
                    time.sleep(0.25)
                    print("Calling stop_zoom() after zoom in")
                    ptz_controller.stop_zoom()
                threading.Thread(target=stop_zoom, daemon=True).start()
                self.last_zoom_time = current_time
            elif delta < 0:
                print("Calling zoom('out')")
                ptz_controller.zoom('out')
                # Short controlled zoom burst, then stop
                def stop_zoom():
                    time.sleep(0.25)
                    print("Calling stop_zoom() after zoom out")
                    ptz_controller.stop_zoom()
                threading.Thread(target=stop_zoom, daemon=True).start()
                self.last_zoom_time = current_time
            
            event.accept()
        except Exception as e:
            error_msg = f"Error in wheel event: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            # Show error in status bar for better diagnostics in compiled version
            try:
                main_window = self.window()
                QTimer.singleShot(0, lambda: main_window.status_bar.showMessage(error_msg, 5000))
            except:
                pass
            # We don't show this in status bar as it would be too frequent
    
    def paintEvent(self, event):
        try:
            if self.frame is not None and self.frame.size > 0:
                # Convert frame to QImage
                try:
                    rgb_image = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_image.shape
                    bytes_per_line = ch * w
                    qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(qt_image)
                    
                    # Scale pixmap to fit label while maintaining aspect ratio
                    scaled_pixmap = pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                  Qt.TransformationMode.SmoothTransformation)
                    
                    # Draw on a painter
                    painter = QPainter(self)
                    # Center the image
                    x = max(0, (self.width() - scaled_pixmap.width()) // 2)
                    y = max(0, (self.height() - scaled_pixmap.height()) // 2)
                    painter.drawPixmap(x, y, scaled_pixmap)
                except Exception as e:
                    print(f"Error converting frame to image: {str(e)}")
                    # Draw a placeholder with error message
                    painter = QPainter(self)
                    painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"Error displaying video: {str(e)}")
                    return
                    
                # Draw crosshair if enabled
                if self.crosshair_enabled:
                    painter.setPen(QPen(QColor(255, 0, 0), 1))  # Thinner red crosshair (1 pixel instead of 2)
                    
                    # Calculate crosshair position in widget coordinates
                    crosshair_screen_x = int(self.crosshair_x * self.width())
                    crosshair_screen_y = int(self.crosshair_y * self.height())
                    
                    # Horizontal line
                    painter.drawLine(0, crosshair_screen_y, self.width(), crosshair_screen_y)
                    
                    # Vertical line
                    painter.drawLine(crosshair_screen_x, 0, crosshair_screen_x, self.height())
                    
                    # Draw diagonal lines instead of square
                    painter.drawLine(crosshair_screen_x - 10, crosshair_screen_y - 10, crosshair_screen_x - 5, crosshair_screen_y - 5)
                    painter.drawLine(crosshair_screen_x + 10, crosshair_screen_y - 10, crosshair_screen_x + 5, crosshair_screen_y - 5)
                    painter.drawLine(crosshair_screen_x - 10, crosshair_screen_y + 10, crosshair_screen_x - 5, crosshair_screen_y + 5)
                    painter.drawLine(crosshair_screen_x + 10, crosshair_screen_y + 10, crosshair_screen_x + 5, crosshair_screen_y + 5)
            else:
                # If no frame, just call base class paintEvent
                super().paintEvent(event)
        except Exception as e:
            print(f"Error in paintEvent: {str(e)}")
            # Draw error message
            painter = QPainter(self)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"Paint error: {str(e)}")

    def set_crosshair_position(self, x_norm, y_norm):
        """Set crosshair position programmatically"""
        if 0.0 <= x_norm <= 1.0 and 0.0 <= y_norm <= 1.0:
            self.crosshair_x = x_norm
            self.crosshair_y = y_norm
            self.update()
            
    def closeEvent(self, event):
        """Handle widget closing"""
        # Clean up any resources if needed
        self.frame = None
        event.accept()
