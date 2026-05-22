import sys
import os
import time
import threading
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, 
                             QSplitter, QLabel, QMenuBar, QMenu, QDockWidget, 
                             QVBoxLayout, QPushButton, QGroupBox, QGridLayout, QSlider, QLCDNumber, QMessageBox,
                             QComboBox, QSpinBox, QCheckBox, QDial, QLineEdit, QFormLayout, QDialog)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QAction

from camera.video_widget import VideoWidget
from camera.video_thread import VideoThread
from ptz.pelcod_controller import PelcoDController
from ptz.ptz_controller import PTZController
from ui.settings_dialog import SettingsDialog
from ui.device_info_dialog import DeviceInfoDialog  # New import
from ui.device_info_widget import DeviceInfoWidget  # New import
from ui.ai_assistant_widget import AIAssistantWidget  # New import
from ui.yolo_detection_widget import YOLODetectionWidget  # New import
from core.yolo_tracker import YOLOTracker  # New import
from core.ai_integration import OllamaAI
from camera.config_manager import config_manager
from rangefinder.rangefinder_widget import RangefinderWidget  # Новый импорт
from relayx3.relayx3_widget import RelayX3Widget  # Новый импорт для RelayX3

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OnCam - Two Cameras with Crosshairs and PTZ Control")
        self.setGeometry(100, 100, 1200, 600)
        
        # Apply modern dark theme stylesheet
        self.setStyleSheet("""
            /* Main application styling */
            QMainWindow {
                background-color: #2b2b2b;
            }
            
            QWidget {
                color: #ffffff;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            
            /* Menu styling */
            QMenuBar {
                background-color: #3c3c3c;
                color: white;
                padding: 4px;
            }
            
            QMenuBar::item {
                background: transparent;
                padding: 4px 8px;
                border-radius: 4px;
            }
            
            QMenuBar::item:selected {
                background: #555555;
            }
            
            QMenuBar::item:pressed {
                background: #666666;
            }
            
            QMenu {
                background-color: #3c3c3c;
                color: white;
                border: 1px solid #555555;
            }
            
            QMenu::item {
                padding: 5px 20px;
            }
            
            QMenu::item:selected {
                background-color: #555555;
            }
            
            /* Status bar styling */
            QStatusBar {
                background-color: #3c3c3c;
                color: #aaaaaa;
                border-top: 1px solid #555555;
            }
            
            /* Dock widget styling */
            QDockWidget {
                background-color: #2b2b2b;
                color: white;
                border: none;
            }
            
            QDockWidget::title {
                background-color: #3c3c3c;
                padding: 5px;
                border-bottom: 1px solid #555555;
            }
            
            /* Group box styling */
            QGroupBox {
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 6px;
                margin-top: 1ex;
                padding: 10px;
                font-weight: bold;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
                color: #cccccc;
            }
            
            /* Button styling */
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
            
            QPushButton:disabled {
                background-color: #333333;
                color: #777777;
                border: 1px solid #444444;
            }
            
            /* Slider styling */
            QSlider::groove:horizontal {
                border: 1px solid #555555;
                height: 8px;
                background: #4a4a4a;
                border-radius: 4px;
            }
            
            QSlider::handle:horizontal {
                background: #666666;
                border: 1px solid #888888;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            
            QSlider::sub-page:horizontal {
                background: #5a5a5a;
                border-radius: 4px;
            }
            
            /* LCD number styling */
            QLCDNumber {
                background-color: #333333;
                color: #00ff00;
                border: 1px solid #555555;
                border-radius: 4px;
            }
            
            /* Label styling */
            QLabel {
                color: #dddddd;
            }
            
            /* Video widget styling */
            VideoWidget {
                background-color: #1e1e1e;
                border: 1px solid #555555;
                border-radius: 4px;
            }
        """)
        
        # Keep track of key states for continuous movement
        self.key_states = {}
        self.last_command = None
        self.last_speed_change_time = 0
        self.speed_change_delay = config_manager.get_controls_config().get("speed_change_delay", 0.2)  # 200ms delay between speed changes
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create a splitter for the two video windows
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # First video window
        self.video_widget1 = VideoWidget()
        self.video_widget1.setText("Camera 1 Loading...")
        self.video_widget1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Second video window
        self.video_widget2 = VideoWidget()
        self.video_widget2.setText("Camera 2 Loading...")
        self.video_widget2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add video widgets to the splitter
        splitter.addWidget(self.video_widget1)
        splitter.addWidget(self.video_widget2)
        
        # Set initial sizes
        splitter.setSizes([600, 600])
        
        # Create layout and add splitter to it
        layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter)
        
        # Set focus policy for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create status bar
        self.status_bar = self.statusBar()
        
        # Create PTZ control panels
        self.create_ptz_panels()
        
        # Initialize video streams
        self.init_video_streams()
        
        # Start timer for handling key presses
        self.key_timer = QTimer()
        self.key_timer.timeout.connect(self.handle_key_presses)
        self.key_timer.start(50)  # Check 20 times per second
        
        # Make sure the window can receive key events
        self.activateWindow()
        self.raise_()
        self.setFocus()
        
        # Apply saved settings
        self.apply_saved_settings()
        
    def apply_saved_settings(self):
        """Apply saved settings on startup"""
        display_config = config_manager.get_display_config()
        
        # Apply crosshair settings
        crosshair_enabled = display_config.get("crosshair_enabled", False)
        self.video_widget1.set_crosshair_enabled(crosshair_enabled)
        self.video_widget2.set_crosshair_enabled(crosshair_enabled)
        self.toggle_crosshair_action.setChecked(crosshair_enabled)
        
        # Apply invert tilt setting
        invert_tilt = display_config.get("invert_tilt", True)
        if hasattr(self, 'pan_tilt_controller'):
            self.pan_tilt_controller.invert_tilt_checkbox.setChecked(invert_tilt)
        
        # Update PTZ controllers with saved settings
        self.update_ptz_controllers()
        
        # Update pan-tilt controller with saved settings
        self.update_pan_tilt_controller()
        
    def create_menu_bar(self):
        menu_bar = self.menuBar()
        
        # View menu - now includes device and AI panels
        view_menu = menu_bar.addMenu('&View')
        
        # Toggle crosshair action
        self.toggle_crosshair_action = QAction('Show &Crosshairs', self)
        self.toggle_crosshair_action.setCheckable(True)
        self.toggle_crosshair_action.setShortcut('Ctrl+X')
        self.toggle_crosshair_action.triggered.connect(self.toggle_crosshairs)
        view_menu.addAction(self.toggle_crosshair_action)
        
        # Toggle rangefinder panel
        self.toggle_rangefinder_action = QAction('Show &Rangefinder Control', self)
        self.toggle_rangefinder_action.setCheckable(True)
        self.toggle_rangefinder_action.setChecked(False)
        self.toggle_rangefinder_action.setShortcut('Ctrl+R')
        self.toggle_rangefinder_action.triggered.connect(self.toggle_rangefinder_panel)
        view_menu.addAction(self.toggle_rangefinder_action)
        
        # Toggle PTZ panels
        self.toggle_ptz_action = QAction('Show &PTZ Controls', self)
        self.toggle_ptz_action.setCheckable(True)
        self.toggle_ptz_action.setChecked(config_manager.get_display_config().get("ptz_panels_visible", False))
        self.toggle_ptz_action.setShortcut('Ctrl+P')
        self.toggle_ptz_action.triggered.connect(self.toggle_ptz_panels)
        view_menu.addAction(self.toggle_ptz_action)
        
        # Toggle invert tilt action
        self.toggle_invert_tilt_action = QAction('Toggle &Invert Tilt', self)
        self.toggle_invert_tilt_action.setShortcut('Ctrl+I')
        self.toggle_invert_tilt_action.triggered.connect(self.toggle_invert_tilt)
        view_menu.addAction(self.toggle_invert_tilt_action)
        
        # Toggle fullscreen action
        self.toggle_fullscreen_action = QAction('&Fullscreen', self)
        self.toggle_fullscreen_action.setShortcut('F11')
        self.toggle_fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(self.toggle_fullscreen_action)
        
        # Add toggle action for device info dock
        self.toggle_device_info_dock_action = QAction('Show &Device Panel', self)
        self.toggle_device_info_dock_action.setCheckable(True)
        self.toggle_device_info_dock_action.setChecked(False)
        self.toggle_device_info_dock_action.setShortcut('Ctrl+D')
        self.toggle_device_info_dock_action.triggered.connect(self.toggle_device_info_dock)
        view_menu.addAction(self.toggle_device_info_dock_action)
        
        # Add toggle action for AI assistant dock
        self.toggle_ai_assistant_dock_action = QAction('Show &AI Assistant Panel', self)
        self.toggle_ai_assistant_dock_action.setCheckable(True)
        self.toggle_ai_assistant_dock_action.setChecked(False)
        self.toggle_ai_assistant_dock_action.setShortcut('Ctrl+A')
        self.toggle_ai_assistant_dock_action.triggered.connect(self.toggle_ai_assistant_dock)
        view_menu.addAction(self.toggle_ai_assistant_dock_action)
        
        # Add toggle action for YOLO detection dock
        self.toggle_yolo_dock_action = QAction('Show &YOLO Detection Panel', self)
        self.toggle_yolo_dock_action.setCheckable(True)
        self.toggle_yolo_dock_action.setChecked(False)
        self.toggle_yolo_dock_action.setShortcut('Ctrl+Y')
        self.toggle_yolo_dock_action.triggered.connect(self.toggle_yolo_dock)
        view_menu.addAction(self.toggle_yolo_dock_action)
        
        # Add toggle action for RelayX3 relay control dock
        self.toggle_relayx3_dock_action = QAction('Show &RelayX3 Control Panel', self)
        self.toggle_relayx3_dock_action.setCheckable(True)
        self.toggle_relayx3_dock_action.setChecked(False)
        self.toggle_relayx3_dock_action.setShortcut('Ctrl+L')
        self.toggle_relayx3_dock_action.triggered.connect(self.toggle_relayx3_dock)
        view_menu.addAction(self.toggle_relayx3_dock_action)
        
        # Settings menu
        settings_menu = menu_bar.addMenu('&Settings')
        settings_action = QAction('Camera Settings', self)
        settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(settings_action)
        
        # Device Info menu - now only contains the dialog
        device_info_menu = menu_bar.addMenu('&Device')
        device_info_action = QAction('Device Information', self)
        device_info_action.triggered.connect(self.show_device_info)
        device_info_menu.addAction(device_info_action)
        
        # AI Assistant menu - now only contains the dialog
        ai_menu = menu_bar.addMenu('&AI')
        ai_assistant_action = QAction('AI Assistant', self)
        ai_assistant_action.triggered.connect(self.show_ai_assistant)
        ai_menu.addAction(ai_assistant_action)
        
        # YOLO Detection menu
        yolo_menu = menu_bar.addMenu('&YOLO')
        yolo_detection_action = QAction('YOLO Detection Settings', self)
        yolo_detection_action.triggered.connect(self.show_yolo_detection)
        yolo_menu.addAction(yolo_detection_action)
        
        # Help menu
        help_menu = menu_bar.addMenu('&Help')
        
        # Keyboard shortcuts action
        shortcuts_action = QAction('Keyboard &Shortcuts', self)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.save_settings()
            self.apply_settings_hot_swap()  # Apply settings changes immediately without restart

    def show_device_info(self):
        """Show device information dialog"""
        dialog = DeviceInfoDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.save_device_info()

    def show_ai_assistant(self):
        """Show AI assistant dialog (future enhancement)"""
        # For now, we'll just toggle the dock widget
        self.toggle_ai_assistant_dock()

    def show_yolo_detection(self):
        """Show YOLO detection settings"""
        self.toggle_yolo_dock()

    def toggle_device_info_dock(self):
        """Toggle the visibility of the device info dock widget"""
        if hasattr(self, 'device_info_dock') and self.device_info_dock:
            visible = self.device_info_dock.isVisible()
            self.device_info_dock.setVisible(not visible)
            self.toggle_device_info_dock_action.setChecked(not visible)
        else:
            self.create_device_info_dock()
            self.device_info_dock.setVisible(True)
            self.toggle_device_info_dock_action.setChecked(True)

    def toggle_ai_assistant_dock(self):
        """Toggle the visibility of the AI assistant dock widget"""
        if hasattr(self, 'ai_assistant_dock') and self.ai_assistant_dock:
            visible = self.ai_assistant_dock.isVisible()
            self.ai_assistant_dock.setVisible(not visible)
            self.toggle_ai_assistant_dock_action.setChecked(not visible)
        else:
            self.create_ai_assistant_dock()
            self.ai_assistant_dock.setVisible(True)
            self.toggle_ai_assistant_dock_action.setChecked(True)

    def toggle_yolo_dock(self):
        """Toggle the visibility of the YOLO detection dock widget"""
        if hasattr(self, 'yolo_dock') and self.yolo_dock:
            visible = self.yolo_dock.isVisible()
            self.yolo_dock.setVisible(not visible)
            self.toggle_yolo_dock_action.setChecked(not visible)
        else:
            self.create_yolo_dock()
            self.yolo_dock.setVisible(True)
            self.toggle_yolo_dock_action.setChecked(True)

    def create_device_info_dock(self):
        """Create the device info dock widget"""
        if hasattr(self, 'device_info_dock') and self.device_info_dock:
            return

        # Create dock widget
        self.device_info_dock = QDockWidget("Device Information", self)
        self.device_info_dock.setObjectName("DeviceInfoDock")
        
        # Create the device info widget
        self.device_info_widget = DeviceInfoWidget(self)
        self.device_info_dock.setWidget(self.device_info_widget)
        
        # Set dock properties
        self.device_info_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        
        # Add dock to main window
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.device_info_dock)
        
        # Connect visibility changes to update menu action
        self.device_info_dock.visibilityChanged.connect(self.on_device_info_dock_visibility_changed)

    def create_ai_assistant_dock(self):
        """Create the AI assistant dock widget"""
        if hasattr(self, 'ai_assistant_dock') and self.ai_assistant_dock:
            return

        # Create dock widget
        self.ai_assistant_dock = QDockWidget("AI Assistant", self)
        self.ai_assistant_dock.setObjectName("AIAssistantDock")
        
        # Create the AI assistant widget
        self.ai_assistant_widget = AIAssistantWidget(self)
        self.ai_assistant_dock.setWidget(self.ai_assistant_widget)
        
        # Set dock properties
        self.ai_assistant_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        
        # Add dock to main window
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ai_assistant_dock)
        
        # Connect visibility changes to update menu action
        self.ai_assistant_dock.visibilityChanged.connect(self.on_ai_assistant_dock_visibility_changed)

    def create_yolo_dock(self):
        """Create the YOLO detection dock widget"""
        if hasattr(self, 'yolo_dock') and self.yolo_dock:
            return

        # Create dock widget
        self.yolo_dock = QDockWidget("YOLO Detection & Tracking", self)
        self.yolo_dock.setObjectName("YOLODetectionDock")
        
        # Create the YOLO detection widget
        self.yolo_widget = YOLODetectionWidget(self)
        self.yolo_dock.setWidget(self.yolo_widget)
        
        # Connect signals to slots
        self.yolo_widget.detection_enabled_changed.connect(self.on_detection_enabled_changed)
        self.yolo_widget.confidence_threshold_changed.connect(self.on_confidence_threshold_changed)
        self.yolo_widget.iou_threshold_changed.connect(self.on_iou_threshold_changed)
        self.yolo_widget.tracking_enabled_changed.connect(self.on_tracking_enabled_changed)
        self.yolo_widget.classes_changed.connect(self.on_classes_changed)
        
        # Set dock properties
        self.yolo_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        
        # Add dock to main window
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.yolo_dock)
        
        # Connect visibility changes to update menu action
        self.yolo_dock.visibilityChanged.connect(self.on_yolo_dock_visibility_changed)

    def on_device_info_dock_visibility_changed(self, visible):
        """Update the menu action when dock visibility changes"""
        self.toggle_device_info_dock_action.setChecked(visible)

    def on_ai_assistant_dock_visibility_changed(self, visible):
        """Update the menu action when AI assistant dock visibility changes"""
        self.toggle_ai_assistant_dock_action.setChecked(visible)

    def on_yolo_dock_visibility_changed(self, visible):
        """Update the menu action when YOLO dock visibility changes"""
        self.toggle_yolo_dock_action.setChecked(visible)

    def toggle_relayx3_dock(self):
        """Toggle the visibility of the RelayX3 control dock widget"""
        if hasattr(self, 'relayx3_dock') and self.relayx3_dock:
            visible = self.relayx3_dock.isVisible()
            self.relayx3_dock.setVisible(not visible)
            self.toggle_relayx3_dock_action.setChecked(not visible)
        else:
            self.create_relayx3_dock()
            self.relayx3_dock.setVisible(True)
            self.toggle_relayx3_dock_action.setChecked(True)

    def create_relayx3_dock(self):
        """Create the RelayX3 control dock widget"""
        if hasattr(self, 'relayx3_dock') and self.relayx3_dock:
            return

        # Create dock widget
        self.relayx3_dock = QDockWidget("RelayX3 Control", self)
        self.relayx3_dock.setObjectName("RelayX3Dock")
        
        # Create the RelayX3 widget
        self.relayx3_widget = RelayX3Widget(self)
        self.relayx3_dock.setWidget(self.relayx3_widget)
        
        # Set dock properties
        self.relayx3_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        
        # Add dock to main window
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.relayx3_dock)
        
        # Connect visibility changes to update menu action
        self.relayx3_dock.visibilityChanged.connect(self.on_relayx3_dock_visibility_changed)

    def on_relayx3_dock_visibility_changed(self, visible):
        """Update the menu action when RelayX3 dock visibility changes"""
        self.toggle_relayx3_dock_action.setChecked(visible)

    def on_detection_enabled_changed(self, enabled):
        """Handle detection enabled state change"""
        if hasattr(self, 'thread1') and self.thread1:
            self.thread1.set_detection_enabled(enabled)
        if hasattr(self, 'thread2') and self.thread2:
            self.thread2.set_detection_enabled(enabled)

    def on_confidence_threshold_changed(self, threshold):
        """Handle confidence threshold change"""
        if hasattr(self, 'thread1') and self.thread1:
            self.thread1.set_confidence_threshold(threshold)
        if hasattr(self, 'thread2') and self.thread2:
            self.thread2.set_confidence_threshold(threshold)

    def on_iou_threshold_changed(self, threshold):
        """Handle IOU threshold change"""
        if hasattr(self, 'thread1') and self.thread1:
            self.thread1.set_iou_threshold(threshold)
        if hasattr(self, 'thread2') and self.thread2:
            self.thread2.set_iou_threshold(threshold)

    def on_tracking_enabled_changed(self, enabled):
        """Handle tracking enabled state change"""
        if hasattr(self, 'thread1') and self.thread1:
            self.thread1.set_tracking_enabled(enabled)
        if hasattr(self, 'thread2') and self.thread2:
            self.thread2.set_tracking_enabled(enabled)

    def on_classes_changed(self, classes):
        """Handle class selection change"""
        if hasattr(self, 'thread1') and self.thread1:
            self.thread1.set_selected_classes(classes)
        if hasattr(self, 'thread2') and self.thread2:
            self.thread2.set_selected_classes(classes)

    def apply_settings_hot_swap(self):
        """Apply settings changes without restarting the application"""
        self.status_bar.showMessage("Applying new settings...", 2000)
        
        # Stop current video streams gracefully
        if hasattr(self, 'thread1') and self.thread1:
            try:
                self.thread1.stop()
                # Wait for thread to finish, with timeout
                if not self.thread1.wait(2000):  # Wait 2 seconds max
                    print("Warning: Thread 1 did not stop in time, may cause resource leak")
            except Exception as e:
                print(f"Error stopping thread1: {str(e)}")
        
        if hasattr(self, 'thread2') and self.thread2:
            try:
                self.thread2.stop()
                # Wait for thread to finish, with timeout
                if not self.thread2.wait(2000):  # Wait 2 seconds max
                    print("Warning: Thread 2 did not stop in time, may cause resource leak")
            except Exception as e:
                print(f"Error stopping thread2: {str(e)}")
        
        # Reinitialize video streams with new settings
        try:
            self.init_video_streams()
        except Exception as e:
            print(f"Error initializing video streams: {str(e)}")
            self.status_bar.showMessage("Error initializing video streams", 3000)
        
        # Update PTZ controllers with new settings
        try:
            self.update_ptz_controllers()
        except Exception as e:
            print(f"Error updating PTZ controllers: {str(e)}")
            self.status_bar.showMessage("Error updating PTZ controllers", 3000)
        
        # Update pan-tilt controller if it exists
        try:
            self.update_pan_tilt_controller()
        except Exception as e:
            print(f"Error updating pan-tilt controller: {str(e)}")
            self.status_bar.showMessage("Error updating pan-tilt controller", 3000)
        
        self.status_bar.showMessage("New settings applied successfully!", 3000)
    
    def update_ptz_controllers(self):
        """Update PTZ controllers with new camera settings"""
        try:
            # Get updated camera configurations
            cam1_config = config_manager.get_camera_config("camera1")
            cam2_config = config_manager.get_camera_config("camera2")
            
            # Validate IP before updating
            if not self.is_valid_ip(cam1_config.get("ip", "")):
                warning_msg = f"Warning: Invalid Camera 1 IP detected: {cam1_config.get('ip', '')}"
                print(warning_msg)
                self.status_bar.showMessage(warning_msg, 5000)
                
            if not self.is_valid_ip(cam2_config.get("ip", "")):
                warning_msg = f"Warning: Invalid Camera 2 IP detected: {cam2_config.get('ip', '')}"
                print(warning_msg)
                self.status_bar.showMessage(warning_msg, 5000)
            
            # Update the PTZ controller for camera 1 (used by PelcoDController) - only if it exists
            if hasattr(self, 'pan_tilt_controller') and hasattr(self.pan_tilt_controller, 'camera1_ptz'):
                # Close existing connection if it exists
                try:
                    self.pan_tilt_controller.camera1_ptz.close()
                except Exception as e:
                    print(f"Error closing PTZ controller for camera 1: {str(e)}")
                
                # Create new PTZ controller with updated settings
                try:
                    self.pan_tilt_controller.camera1_ptz = PTZController(
                        cam1_config.get("ip", ""),
                        cam1_config.get("port", 80),
                        cam1_config.get("username", ""),
                        cam1_config.get("password", "")
                    )
                    self.pan_tilt_controller.camera1_ptz.init_ptz()
                except Exception as e:
                    print(f"Error creating PTZ controller for camera 1: {str(e)}")
            
            # Close existing PTZ controller for camera 2 if it exists
            if hasattr(self, 'ptz_controller2'):
                try:
                    self.ptz_controller2.close()
                except Exception as e:
                    print(f"Error closing PTZ controller 2: {str(e)}")
            
            # Create new PTZ controller with updated settings for camera 2
            try:
                self.ptz_controller2 = PTZController(
                    cam2_config.get("ip", ""),
                    cam2_config.get("port", 80),
                    cam2_config.get("username", ""),
                    cam2_config.get("password", "")
                )
                # Initialize ONVIF PTZ in background - errors will be handled internally by PTZController
                self.ptz_controller2.init_ptz()
                
                # Wait briefly to allow initialization to complete and check if it succeeded
                import time
                time.sleep(0.5)  # Give some time for initialization
                
                if not self.ptz_controller2.initialized:
                    print(f"Warning: PTZ controller for camera 2 ({cam2_config.get('ip', '')}) failed to initialize")
                    self.status_bar.showMessage(f"Camera 2 PTZ not connected: {cam2_config.get('ip', '')}", 5000)
            except Exception as e:
                error_msg = f"Error creating PTZ controller 2: {str(e)}"
                print(error_msg)
                self.status_bar.showMessage(error_msg, 5000)
        except Exception as e:
            error_msg = f"Error updating PTZ controllers: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 5000)
    
    def update_pan_tilt_controller(self):
        """Update pan-tilt controller with new settings"""
        try:
            # Get updated pan-tilt configuration
            pt_config = config_manager.get_camera_config("pan_tilt")
            
            # Update the existing controller with new IP if it exists
            if hasattr(self, 'pan_tilt_controller'):
                # Update the IP and reconnect
                self.pan_tilt_controller.update_connection(pt_config.get("ip", ""), pt_config.get("port", 9761))
            else:
                print("Warning: pan_tilt_controller not available for update")
        except Exception as e:
            error_msg = f"Error updating pan-tilt controller: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 5000)
    
    def create_ptz_panels(self):
        try:
            # Create PTZ control panel for camera 2
            cam2_config = config_manager.get_camera_config("camera2")
            self.ptz_controller2 = PTZController(
                cam2_config.get("ip", ""),
                cam2_config.get("port", 80),
                cam2_config.get("username", ""),
                cam2_config.get("password", "")
            )
            self.ptz_controller2.init_ptz()  # Initialize ONVIF PTZ in background
        except Exception as e:
            error_msg = f"Failed to initialize PTZ controller for camera 2: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 5000)
            # Don't let PTZ initialization failure stop the application
            pass
        
        try:
            # Create Pelco-D control panel
            pt_config = config_manager.get_camera_config("pan_tilt")
            self.pan_tilt_dock = QDockWidget("Pan Tilt Unit Control", self)
            self.pan_tilt_controller = PelcoDController(pt_config.get("ip", ""), pt_config.get("port", 9761))
            self.pan_tilt_dock.setWidget(self.pan_tilt_controller)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.pan_tilt_dock)
        except Exception as e:
            error_msg = f"Failed to initialize Pelco-D controller: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 5000)
            # Don't let PTZ initialization failure stop the application
            pass
        
        try:
            # Create rangefinder dock widget
            self.rangefinder_dock = QDockWidget("Laser Rangefinder Control", self)
            self.rangefinder_controller = RangefinderWidget()
            self.rangefinder_dock.setWidget(self.rangefinder_controller)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.rangefinder_dock)
        except Exception as e:
            error_msg = f"Failed to initialize rangefinder: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 5000)
            # Don't let rangefinder initialization failure stop the application
            pass
        
        try:
            # Set initial visibility based on config
            display_config = config_manager.get_display_config()
            self.pan_tilt_dock.setVisible(display_config.get("ptz_panels_visible", False))
            self.rangefinder_dock.setVisible(False)  # Initially hidden
            
            # Connect status update signals
            self.connect_status_signals()
        except Exception as e:
            error_msg = f"Error setting up PTZ panel visibility: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 5000)
    
    def closeEvent(self, event):
        # Stop video threads with timeout
        if hasattr(self, 'thread1'):
            try:
                self.thread1.stop()
                # Force terminate if thread doesn't stop gracefully
                if not self.thread1.wait(1000):  # Wait 1 second
                    self.thread1.terminate()
            except Exception as e:
                print(f"Error stopping thread1: {str(e)}")
        if hasattr(self, 'thread2'):
            try:
                self.thread2.stop()
                # Force terminate if thread doesn't stop gracefully
                if not self.thread2.wait(1000):  # Wait 1 second
                    self.thread2.terminate()
            except Exception as e:
                print(f"Error stopping thread2: {str(e)}")
            
        # Clean up PTZ controllers
        if hasattr(self, 'ptz_controller1'):
            try:
                self.ptz_controller1.close()
            except Exception as e:
                print(f"Error closing ptz_controller1: {str(e)}")
        if hasattr(self, 'ptz_controller2'):
            try:
                self.ptz_controller2.close()
            except Exception as e:
                print(f"Error closing ptz_controller2: {str(e)}")
        if hasattr(self, 'pan_tilt_controller'):
            try:
                self.pan_tilt_controller.close_connection()
            except Exception as e:
                print(f"Error closing pan_tilt_controller: {str(e)}")
                
        # Close rangefinder widget
        if hasattr(self, 'rangefinder_controller'):
            try:
                self.rangefinder_controller.closeEvent(event)
            except Exception as e:
                print(f"Error closing rangefinder controller: {str(e)}")
            
        # Stop key timer
        if hasattr(self, 'key_timer'):
            try:
                self.key_timer.stop()
            except Exception as e:
                print(f"Error stopping key timer: {str(e)}")
            
        event.accept()

    def show_shortcuts(self):
        """Display keyboard shortcuts information"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Keyboard Shortcuts")
        msg_box.setText("Pelco-D Controller Keyboard Shortcuts:")
        msg_box.setInformativeText(
            "Arrow Keys: Pan/Tilt\n"
            "Page Up: Zoom In\n"
            "Page Down: Zoom Out\n"
            "Space: Stop All Movement\n"
            "+ (Plus): Increase Speed\n"
            "- (Minus): Decrease Speed\n\n"
            "Additional Features:\n"
            "- Click anywhere on the video to move the crosshair and control PTZ\n"
            "- Use 'Invert Tilt Control' option if up/down controls work in opposite direction\n"
            "- Ctrl+I: Toggle invert tilt control\n"
            "- F11: Toggle fullscreen mode\n\n"
            "Click on the main window to ensure it has focus before using keyboard controls."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Apply dark theme styling to match the application
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            
            QLabel {
                color: #ffffff;
            }
            
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
        
        msg_box.exec()
        
    def connect_status_signals(self):
        # Connect Pelco-D controller signal to status bar if it exists
        if hasattr(self, 'pan_tilt_controller') and hasattr(self.pan_tilt_controller, 'command_sent_signal'):
            self.pan_tilt_controller.command_sent_signal.connect(self.update_status_message)
        else:
            print("Warning: Could not connect PTZ controller signals - controller not available")
    
    def update_status_message(self, message):
        """Update status bar with message"""
        self.status_bar.showMessage(message, 0)  # 0 means message won't timeout)
        
    def toggle_rangefinder_panel(self, checked):
        self.rangefinder_dock.setVisible(checked)
        
        # Update action text based on current state
        self.toggle_rangefinder_action.setChecked(checked)
        if checked:
            self.toggle_rangefinder_action.setText('Hide Rangefinder Control')
        else:
            self.toggle_rangefinder_action.setText('Show Rangefinder Control')

    def toggle_ptz_panels(self, checked):
        # Show or hide all PTZ panels based on checked state
        self.pan_tilt_dock.setVisible(checked)
        
        # Update action text based on current state
        self.toggle_ptz_action.setChecked(checked)
        if checked:
            self.toggle_ptz_action.setText('Hide PTZ Controls')
        else:
            self.toggle_ptz_action.setText('Show PTZ Controls')
            
        # Save to config
        config = config_manager.config.copy()
        config["display"]["ptz_panels_visible"] = checked
        config_manager.save_config(config)
        
    def toggle_crosshairs(self, checked):
        self.video_widget1.set_crosshair_enabled(checked)
        self.video_widget2.set_crosshair_enabled(checked)
        
        # Update action text
        if checked:
            self.toggle_crosshair_action.setText('Hide Crosshairs')
        else:
            self.toggle_crosshair_action.setText('Show Crosshairs')
            
        # Save to config
        config = config_manager.config.copy()
        config["display"]["crosshair_enabled"] = checked
        config_manager.save_config(config)
            
    def init_video_streams(self):
        # Get camera configurations
        cam1_config = config_manager.get_camera_config("camera1")
        cam2_config = config_manager.get_camera_config("camera2")
        
        # Validate camera configs before creating streams
        # Check if IPs are provided (not necessarily valid, but present)
        cam1_ip = cam1_config.get("ip", "").strip()
        cam2_ip = cam2_config.get("ip", "").strip()
        
        # Check if custom URLs are provided and not empty
        cam1_custom_url = cam1_config.get("custom_rtsp_url", "").strip()
        cam2_custom_url = cam2_config.get("custom_rtsp_url", "").strip()
        
        # Determine RTSP URL format based on configuration
        # If custom_rtsp_url is provided and not empty, use it directly, otherwise construct standard format
        if cam1_custom_url:
            rtsp_url1 = cam1_custom_url
        elif cam1_ip:
            rtsp_url1 = f"rtsp://{cam1_config.get('username', '')}:{cam1_config.get('password', '')}@{cam1_ip}:{cam1_config.get('rtsp_port', 554)}{cam1_config.get('stream_path', '/stream1')}"
        else:
            # Use a dummy URL if no IP and no custom URL
            rtsp_url1 = "http://0.0.0.0/dummy"
        
        if cam2_custom_url:
            rtsp_url2 = cam2_custom_url
        elif cam2_ip:
            # For thermal camera (camera 2), construct the special URL format if no custom URL provided
            # Using the format that worked: rtsp://IP:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif
            rtsp_url2 = f"rtsp://{cam2_config.get('username', '')}:{cam2_config.get('password', '')}@{cam2_ip}:554/cam/realmonitor?channel=1&subtype=0&unicast=true&proto=Onvif"
        else:
            # Use a dummy URL if no IP and no custom URL
            rtsp_url2 = "http://0.0.0.0/dummy"
        
        # Display connection attempt info to status bar
        self.status_bar.showMessage(f"Connecting to Camera 1: {cam1_ip or 'N/A'}, Camera 2 (Thermal): {cam2_ip or 'N/A'}", 3000)
        
        try:
            # Create threads for video capture
            self.thread1 = VideoThread(rtsp_url1, 1)
            self.thread2 = VideoThread(rtsp_url2, 2)
            
            # Connect signals
            self.thread1.change_pixmap_signal.connect(self.update_image)
            self.thread2.change_pixmap_signal.connect(self.update_image)
            self.thread1.connection_status_signal.connect(self.update_status_message)
            self.thread2.connection_status_signal.connect(self.update_status_message)
            
            # Connect detection stats signals to update YOLO widget
            if hasattr(self.thread1, 'detection_stats_signal'):
                self.thread1.detection_stats_signal.connect(lambda det, track: self.update_detection_stats(det, track, 1))
            if hasattr(self.thread2, 'detection_stats_signal'):
                self.thread2.detection_stats_signal.connect(lambda det, track: self.update_detection_stats(det, track, 2))
            
            # Start threads
            self.thread1.start()
            self.thread2.start()
            
            print(f"Video threads started for Camera 1: {cam1_ip or 'N/A'} and Camera 2: {cam2_ip or 'N/A'}")
        except Exception as e:
            error_msg = f"Error initializing video streams: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 5000)
    
    def update_detection_stats(self, detection_count, tracking_count, camera_id):
        """Update the detection statistics in the YOLO widget"""
        if hasattr(self, 'yolo_widget') and self.yolo_widget:
            # For now, just update the stats - in the future, we could differentiate by camera
            self.yolo_widget.update_stats(detection_count, tracking_count)
    
    def update_image(self, frame, camera_id):
        """Updates the appropriate video widget with a new frame"""
        try:
            if camera_id == 1:
                self.video_widget1.update_frame(frame)
                # Update status to show active connection
                if hasattr(self.video_widget1, 'text') and self.video_widget1.text() and "Loading" in self.video_widget1.text():
                    self.video_widget1.setText("")  # Clear loading text when first frame arrives
            elif camera_id == 2:
                self.video_widget2.update_frame(frame)
                # Update status to show active connection
                if hasattr(self.video_widget2, 'text') and self.video_widget2.text() and "Loading" in self.video_widget2.text():
                    self.video_widget2.setText("")  # Clear loading text when first frame arrives
        except Exception as e:
            error_msg = f"Error updating image for camera {camera_id}: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 3000)
        
    def keyPressEvent(self, event):
        """Handle key press events"""
        # Map keys to commands
        key_map = {
            Qt.Key.Key_Up: 'up',
            Qt.Key.Key_Down: 'down',
            Qt.Key.Key_Left: 'left',
            Qt.Key.Key_Right: 'right',
            Qt.Key.Key_PageUp: 'zoom_in',
            Qt.Key.Key_PageDown: 'zoom_out',
            Qt.Key.Key_Space: 'stop'
        }
        
        key = event.key()
        if key in key_map:
            self.key_states[key_map[key]] = True
            event.accept()  # Accept the event for these keys
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            # Increase speed with smooth control
            self.increase_speed()
            event.accept()
        elif key == Qt.Key.Key_Minus:
            # Decrease speed with smooth control
            self.decrease_speed()
            event.accept()
        else:
            super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """Handle key release events"""
        # Map keys to commands
        key_map = {
            Qt.Key.Key_Up: 'up',
            Qt.Key.Key_Down: 'down',
            Qt.Key.Key_Left: 'left',
            Qt.Key.Key_Right: 'right',
            Qt.Key.Key_PageUp: 'zoom_in',
            Qt.Key.Key_PageDown: 'zoom_out',
            Qt.Key.Key_Space: 'stop'
        }
        
        key = event.key()
        if key in key_map:
            self.key_states[key_map[key]] = False
            event.accept()  # Accept the event for these keys
        else:
            super().keyReleaseEvent(event)
    
    def handle_key_presses(self):
        """Handle continuous key press actions"""
        try:
            current_command = None
            
            # Determine which command to execute based on key states
            if self.key_states.get('up', False) and self.key_states.get('left', False):
                current_command = 'up_left'
            elif self.key_states.get('up', False) and self.key_states.get('right', False):
                current_command = 'up_right'
            elif self.key_states.get('down', False) and self.key_states.get('left', False):
                current_command = 'down_left'
            elif self.key_states.get('down', False) and self.key_states.get('right', False):
                current_command = 'down_right'
            elif self.key_states.get('up', False):
                current_command = 'up'
            elif self.key_states.get('down', False):
                current_command = 'down'
            elif self.key_states.get('left', False):
                current_command = 'left'
            elif self.key_states.get('right', False):
                current_command = 'right'
            elif self.key_states.get('zoom_in', False):
                current_command = 'zoom_in'
            elif self.key_states.get('zoom_out', False):
                current_command = 'zoom_out'
            elif self.key_states.get('stop', False):
                current_command = 'stop'
                
            # Execute command if different from last command
            if current_command != self.last_command:
                if self.last_command in ['up_left', 'up_right', 'down_left', 'down_right', 
                                       'up', 'down', 'left', 'right', 'zoom_in', 'zoom_out']:
                    # Stop previous movement before starting new one
                    self.pan_tilt_controller.send_command('stop')
                    # Prefer primary camera1 PTZ controller (buttons use it)
                    zoom_ctrl = getattr(self.pan_tilt_controller, "camera1_ptz", None)
                    if not zoom_ctrl and hasattr(self, 'ptz_controller2'):
                        zoom_ctrl = self.ptz_controller2
                    if zoom_ctrl:
                        zoom_ctrl.stop_zoom()
                
                if current_command:
                    if current_command in ['zoom_in', 'zoom_out']:
                        zoom_ctrl = getattr(self.pan_tilt_controller, "camera1_ptz", None)
                        if not zoom_ctrl and hasattr(self, 'ptz_controller2'):
                            zoom_ctrl = self.ptz_controller2
                        if zoom_ctrl:
                            if current_command == 'zoom_in':
                                zoom_ctrl.zoom('in')
                            else:
                                zoom_ctrl.zoom('out')
                    elif current_command == 'stop':
                        self.pan_tilt_controller.send_command('stop')
                        zoom_ctrl = getattr(self.pan_tilt_controller, "camera1_ptz", None)
                        if not zoom_ctrl and hasattr(self, 'ptz_controller2'):
                            zoom_ctrl = self.ptz_controller2
                        if zoom_ctrl:
                            zoom_ctrl.stop_zoom()
                    else:
                        self.pan_tilt_controller.send_command(current_command)
                        
                self.last_command = current_command
                
        except Exception as e:
            error_msg = f"Error in key handling: {str(e)}"
            print(error_msg)
            QTimer.singleShot(0, lambda: self.status_bar.showMessage(error_msg, 3000))
    
    def increase_speed(self):
        """Increase the speed of the Pelco-D controller with smoother control"""
        try:
            # Check if enough time has passed since last speed change
            current_time = time.time()
            if current_time - self.last_speed_change_time < self.speed_change_delay:
                return
            
            if hasattr(self, 'pan_tilt_controller'):
                # Use smaller increments for more precise control
                new_speed = min(63, self.pan_tilt_controller.speed + 2)
                self.pan_tilt_controller.speed = new_speed
                
                # Update UI and status bar
                if hasattr(self.pan_tilt_controller, 'speed_slider'):
                    # Use a direct update if possible to avoid threading issues
                    self.pan_tilt_controller.speed_slider.setValue(new_speed)
                
                # Show more informative message
                percentage = new_speed / 63 * 100
                self.status_bar.showMessage(f"Speed increased to {new_speed} ({percentage:.0f}%)", 2000)
                
                self.last_speed_change_time = current_time
        except Exception as e:
            error_msg = f"Error increasing speed: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 3000)
    
    def decrease_speed(self):
        """Decrease the speed of the Pelco-D controller with smoother control"""
        try:
            # Check if enough time has passed since last speed change
            current_time = time.time()
            if current_time - self.last_speed_change_time < self.speed_change_delay:
                return
            
            if hasattr(self, 'pan_tilt_controller'):
                # Use smaller increments for more precise control
                new_speed = max(1, self.pan_tilt_controller.speed - 2)
                self.pan_tilt_controller.speed = new_speed
                
                # Update UI and status bar
                if hasattr(self.pan_tilt_controller, 'speed_slider'):
                    # Use a direct update if possible to avoid threading issues
                    self.pan_tilt_controller.speed_slider.setValue(new_speed)
                
                # Show more informative message
                percentage = new_speed / 63 * 100
                self.status_bar.showMessage(f"Speed decreased to {new_speed} ({percentage:.0f}%)", 2000)
                
                self.last_speed_change_time = current_time
        except Exception as e:
            error_msg = f"Error decreasing speed: {str(e)}"
            print(error_msg)
            self.status_bar.showMessage(error_msg, 3000)
    
    def toggle_invert_tilt(self):
        """Toggle invert tilt control for Pelco-D device"""
        if hasattr(self, 'pan_tilt_controller'):
            current_state = self.pan_tilt_controller.invert_tilt_checkbox.isChecked()
            self.pan_tilt_controller.invert_tilt_checkbox.setChecked(not current_state)
            state = "enabled" if not current_state else "disabled"
            self.status_bar.showMessage(f"Invert Tilt Control {state}", 2000)
            
            # Save to config
            config = config_manager.config.copy()
            config["display"]["invert_tilt"] = not current_state
            config_manager.save_config(config)
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
            self.status_bar.showMessage("Exited fullscreen mode", 2000)
        else:
            self.showFullScreen()
            self.status_bar.showMessage("Entered fullscreen mode", 2000)
    
    def is_valid_ip(self, ip):
        """Validate if IP address is in correct format"""
        if not ip:
            return False
        
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        
        for part in parts:
            try:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            except ValueError:
                return False
        
        return True
