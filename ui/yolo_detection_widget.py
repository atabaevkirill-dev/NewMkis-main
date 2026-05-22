from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox, 
    QPushButton, QLabel, QDial, QSpinBox, QComboBox, QFormLayout, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Dict, Any


class YOLODetectionWidget(QWidget):
    """
    Widget for controlling YOLO detection and tracking functionality
    """
    
    # Signals for controlling detection/tracking
    detection_enabled_changed = pyqtSignal(bool)
    confidence_threshold_changed = pyqtSignal(float)
    iou_threshold_changed = pyqtSignal(float)
    tracking_enabled_changed = pyqtSignal(bool)
    classes_changed = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Title
        title_label = QLabel("YOLO Object Detection & Tracking")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Detection settings
        detection_group = QGroupBox("Detection Settings")
        detection_layout = QFormLayout()
        
        # Enable detection checkbox
        self.enable_detection_cb = QCheckBox("Enable Object Detection")
        self.enable_detection_cb.setChecked(False)
        self.enable_detection_cb.stateChanged.connect(
            lambda state: self.detection_enabled_changed.emit(state == Qt.CheckState.Checked.value)
        )
        detection_layout.addRow(self.enable_detection_cb)
        
        # Confidence threshold
        self.confidence_dial = QDial()
        self.confidence_dial.setRange(0, 100)
        self.confidence_dial.setValue(50)
        self.confidence_dial.setFixedSize(60, 60)
        self.confidence_dial.setNotchesVisible(True)
        self.confidence_dial.setStyleSheet("""
            QDial {
                background-color: #3c3c3c;
            }
        """)
        self.confidence_dial.valueChanged.connect(self.on_confidence_changed)
        
        confidence_layout = QHBoxLayout()
        confidence_layout.addWidget(self.confidence_dial)
        confidence_layout.addStretch()  # Add stretch to align dial
        detection_layout.addRow("Confidence Threshold (%):", confidence_layout)
        
        # IOU threshold
        self.iou_dial = QDial()
        self.iou_dial.setRange(0, 100)
        self.iou_dial.setValue(40)
        self.iou_dial.setFixedSize(60, 60)
        self.iou_dial.setNotchesVisible(True)
        self.iou_dial.setStyleSheet("""
            QDial {
                background-color: #3c3c3c;
            }
        """)
        self.iou_dial.valueChanged.connect(self.on_iou_changed)
        
        iou_layout = QHBoxLayout()
        iou_layout.addWidget(self.iou_dial)
        iou_layout.addStretch()  # Add stretch to align dial
        detection_layout.addRow("IOU Threshold (%):", iou_layout)
        
        detection_group.setLayout(detection_layout)
        layout.addWidget(detection_group)
        
        # Tracking settings
        tracking_group = QGroupBox("Tracking Settings")
        tracking_layout = QFormLayout()
        
        # Enable tracking checkbox
        self.enable_tracking_cb = QCheckBox("Enable Object Tracking")
        self.enable_tracking_cb.setChecked(False)
        self.enable_tracking_cb.stateChanged.connect(
            lambda state: self.tracking_enabled_changed.emit(state == Qt.CheckState.Checked.value)
        )
        tracking_layout.addRow(self.enable_tracking_cb)
        
        tracking_group.setLayout(tracking_layout)
        layout.addWidget(tracking_group)
        
        # Class selection
        class_group = QGroupBox("Object Classes")
        class_layout = QVBoxLayout()
        
        # Create scroll area for class selection
        scroll_area = QScrollArea()
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #3c3c3c;
                border: 1px solid #555555;
            }
            QWidget {
                background-color: #3c3c3c;
                color: #ffffff;
            }
        """)
        scroll_widget = QWidget()
        self.class_selection_layout = QVBoxLayout()
        
        # Define all COCO dataset classes
        self.coco_classes = [
            'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
            'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
            'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
            'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
            'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
            'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
            'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake',
            'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop',
            'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
            'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
        ]
        
        # Create checkboxes for each class
        self.class_checkboxes = {}
        for class_name in self.coco_classes:
            cb = QCheckBox(class_name.title())  # Capitalize for display
            cb.setChecked(True)  # Select all by default
            cb.stateChanged.connect(self.on_class_selection_changed)
            self.class_checkboxes[class_name] = cb
            self.class_selection_layout.addWidget(cb)
        
        # Add select/deselect all buttons
        button_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_classes)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all_classes)
        button_layout.addWidget(self.select_all_btn)
        button_layout.addWidget(self.deselect_all_btn)
        self.class_selection_layout.addLayout(button_layout)
        
        scroll_widget.setLayout(self.class_selection_layout)
        scroll_widget.setStyleSheet("""
            QWidget {
                background-color: #3c3c3c;
                color: #ffffff;
            }
        """)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        
        class_layout.addWidget(scroll_area)
        class_group.setLayout(class_layout)
        layout.addWidget(class_group)
        
        # Stats display
        stats_group = QGroupBox("Detection Statistics")
        stats_layout = QVBoxLayout()
        
        self.stats_label = QLabel("Objects detected: 0\nTracking: 0")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        stats_layout.addWidget(self.stats_label)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Add stretch to push everything up
        layout.addStretch()
        
        self.setLayout(layout)
    
    def on_confidence_changed(self, value):
        """Handle confidence threshold changes"""
        self.confidence_threshold_changed.emit(value / 100.0)
    
    def on_iou_changed(self, value):
        """Handle IOU threshold changes"""
        self.iou_threshold_changed.emit(value / 100.0)
    
    def on_class_selection_changed(self, state):
        """Handle class selection changes"""
        selected_classes = []
        for class_name, checkbox in self.class_checkboxes.items():
            if checkbox.isChecked():
                selected_classes.append(class_name)
        self.classes_changed.emit(selected_classes)
    
    def select_all_classes(self):
        """Select all classes"""
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(True)
        self.on_class_selection_changed(None)
    
    def deselect_all_classes(self):
        """Deselect all classes"""
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(False)
        self.on_class_selection_changed(None)
    
    def update_stats(self, detection_count: int, tracking_count: int):
        """Update the statistics display"""
        stats_text = f"Objects detected: {detection_count}\nTracking: {tracking_count}"
        self.stats_label.setText(stats_text)
    
    def set_detection_enabled(self, enabled: bool):
        """Programmatically set detection enabled state"""
        self.enable_detection_cb.setChecked(enabled)
    
    def set_tracking_enabled(self, enabled: bool):
        """Programmatically set tracking enabled state"""
        self.enable_tracking_cb.setChecked(enabled)
    
    def set_confidence_threshold(self, threshold: float):
        """Programmatically set confidence threshold"""
        value = int(threshold * 100)
        self.confidence_dial.setValue(value)
    
    def set_iou_threshold(self, threshold: float):
        """Programmatically set IOU threshold"""
        value = int(threshold * 100)
        self.iou_dial.setValue(value)