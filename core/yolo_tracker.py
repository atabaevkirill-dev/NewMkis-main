import cv2
import numpy as np
import torch
import logging
from typing import List, Tuple, Dict, Optional
from enum import Enum
from ultralytics import YOLO

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DetectionClass(Enum):
    PERSON = 0
    BICYCLE = 1
    CAR = 2
    MOTORBIKE = 3
    AIRPLANE = 4
    BUS = 5
    TRAIN = 6
    TRUCK = 7
    BOAT = 8
    TRAFFIC_LIGHT = 9
    FIRE_HYDRANT = 10
    STOP_SIGN = 11
    PARKING_METER = 12
    BENCH = 13
    BIRD = 14
    CAT = 15
    DOG = 16
    HORSE = 17
    SHEEP = 18
    COW = 19
    ELEPHANT = 20
    BEAR = 21
    ZEBRA = 22
    GIRAFFE = 23
    BACKPACK = 24
    UMBRELLA = 25
    HANDBAG = 26
    TIE = 27
    SUITCASE = 28
    FRISBEE = 29
    SKIS = 30
    SNOWBOARD = 31
    SPORTS_BALL = 32
    KITE = 33
    BASEBALL_BAT = 34
    BASEBALL_GLOVE = 35
    SKATEBOARD = 36
    SURFBOARD = 37
    TENNIS_RACKET = 38
    BOTTLE = 39
    WINE_GLASS = 40
    CUP = 41
    FORK = 42
    KNIFE = 43
    SPOON = 44
    BOWL = 45
    BANANA = 46
    APPLE = 47
    SANDWICH = 48
    ORANGE = 49
    BROCCOLI = 50
    CARROT = 51
    HOT_DOG = 52
    PIZZA = 53
    DONUT = 54
    CAKE = 55
    CHAIR = 56
    SOFA = 57
    POTTED_PLANT = 58
    BED = 59
    DINING_TABLE = 60
    TOILET = 61
    TV_MONITOR = 62
    LAPTOP = 63
    MOUSE = 64
    REMOTE = 65
    KEYBOARD = 66
    CELL_PHONE = 67
    MICROWAVE = 68
    OVEN = 69
    TOASTER = 70
    SINK = 71
    REFRIGERATOR = 72
    BOOK = 73
    CLOCK = 74
    VASE = 75
    SCISSORS = 76
    TEDDY_BEAR = 77
    HAIR_DRIER = 78
    TOOTHBRUSH = 79


class YOLOTracker:
    """
    YOLO-based object detection and tracking for video streams
    """
    
    def __init__(self, model_path: str = "yolov5su.pt", conf_threshold: float = 0.5, iou_threshold: float = 0.4):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Load YOLO model using ultralytics directly
        try:
            import os
            candidates = [
                model_path,
                os.path.join(os.path.dirname(__file__), os.path.basename(model_path)),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), os.path.basename(model_path)),
            ]
            local_path = next((path for path in candidates if os.path.isfile(path)), None)
            if local_path is None:
                raise FileNotFoundError(f"YOLO model not found: {model_path}")
            self.model = YOLO(local_path)
            logger.info("Successfully loaded YOLO model from %s", local_path)
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}", exc_info=True)
            self.model = None
        
        if self.model:
            try:
                self.model.to(self.device)
                self.model.eval()
                logger.debug("YOLO model set to evaluation mode and moved to device")
            except Exception as e:
                logger.error(f"Error setting up YOLO model: {e}", exc_info=True)
                self.model = None
        
        # Initialize tracking variables
        self.trackers = {}  # Dictionary to hold trackers for each object
        self.next_object_id = 0
        self.tracked_objects = {}  # Store tracked object info
        
        # Set to track which classes to detect
        self.allowed_classes = list(range(len(DetectionClass)))  # Allow all classes by default
        
        # Ensure confidence and IOU thresholds are properly set
        if self.model:
            # Update the model's default thresholds if they differ
            if hasattr(self.model, 'conf'):
                try:
                    self.model.conf = conf_threshold
                    logger.debug(f"Set confidence threshold to {conf_threshold}")
                except Exception as e:
                    logger.warning(f"Failed to set confidence threshold: {e}")
            if hasattr(self.model, 'iou'):
                try:
                    self.model.iou = iou_threshold
                    logger.debug(f"Set IOU threshold to {iou_threshold}")
                except Exception as e:
                    logger.warning(f"Failed to set IOU threshold: {e}")
    
    def set_confidence_threshold(self, threshold):
        """
        Set the confidence threshold for detection
        """
        self.conf_threshold = threshold
        if self.model:
            # Update model's threshold if applicable
            if hasattr(self.model, 'conf'):
                self.model.conf = threshold
    
    def set_iou_threshold(self, threshold):
        """
        Set the IOU threshold for detection
        """
        self.iou_threshold = threshold
        if self.model:
            # Update model's threshold if applicable
            if hasattr(self.model, 'iou'):
                self.model.iou = threshold
    
    def set_allowed_classes(self, class_ids: List[int]):
        """
        Set which classes are allowed for detection
        
        Args:
            class_ids: List of class IDs to allow
        """
        self.allowed_classes = class_ids
    
    def detect_and_track(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        """
        Detect objects in the frame and track them
        Returns: annotated frame and list of detected/tracked objects
        """
        # If model is not available, return frame as is with empty detections
        if not self.model:
            logger.warning("Model not available, returning unprocessed frame")
            return frame, []
        
        try:
            if not isinstance(frame, np.ndarray):
                raise ValueError(f"Invalid frame type: {type(frame)}. Expected numpy ndarray")
                
            # Validate frame dimensions
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                raise ValueError(f"Invalid frame dimensions: {frame.shape}. Expected 3-channel image")
                
            # Run YOLO detection using ultralytics
            try:
                results = self.model(frame, conf=self.conf_threshold, iou=self.iou_threshold)
                logger.debug(f"Processed frame with YOLO model, found {len(results)} results")
            except Exception as e:
                logger.error(f"YOLO model inference error: {e}", exc_info=True)
                raise
            
            detections = []
            # Process results
            for result in results:
                if result.boxes is not None:  # Check if any detections exist
                    for box in result.boxes:
                        # Get bounding box coordinates
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # Validate class ID
                        if class_id not in self.allowed_classes:
                            logger.debug(f"Skipping detection with class ID {class_id} - not in allowed classes")
                            continue
                            
                        # Validate bounding box coordinates
                        if any(np.isnan([x1, y1, x2, y2])):
                            logger.warning("Skipping detection with NaN coordinates")
                            continue
                            
                        # Ensure coordinates are within frame bounds
                        height, width = frame.shape[:2]
                        x1 = int(np.clip(x1, 0, width))
                        y1 = int(np.clip(y1, 0, height))
                        x2 = int(np.clip(x2, 0, width))
                        y2 = int(np.clip(y2, 0, height))
                        
                        # Convert to integers and calculate center point
                        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                        center_x = int((x1 + x2) / 2)
                        center_y = int((y1 + y2) / 2)
                        
                        logger.debug(f"Detected {DetectionClass(class_id).name} at ({x1}, {y1}, {x2-x1}, {y2-y1}) with confidence {confidence:.2f}")
                        
                        detection_info = {
                            'bbox': [x1, y1, x2-x1, y2-y1],
                            'center': (center_x, center_y),
                            'score': confidence,
                            'class_id': class_id,
                            'class_name': DetectionClass(class_id).name.lower() if class_id < len(DetectionClass) else 'unknown'
                        }
                        
                        detections.append(detection_info)
            
            # Annotate frame with detections and tracks
            try:
                annotated_frame = self.annotate_frame(frame, detections)
                logger.debug(f"Annotated frame with {len(detections)} detections")
            except Exception as e:
                logger.error(f"Annotation error: {e}", exc_info=True)
                annotated_frame = frame.copy()
            
            return annotated_frame, detections
        except Exception as e:
            print(f"Error during YOLO processing: {e}")
            # Return original frame and empty detections on error
            return frame, []
    
    def annotate_frame(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        Draw bounding boxes and labels on the frame
        """
        annotated_frame = frame.copy()
        
        for det in detections:
            bbox = det['bbox']
            center = det['center']
            score = det['score']
            class_name = det['class_name']
            
            # Extract coordinates
            x, y, w, h = map(int, bbox)
            
            # Draw bounding box
            color = self.get_detection_color(det['class_id'])
            cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), color, 2)
            
            # Draw center point
            cv2.circle(annotated_frame, center, 5, (0, 0, 255), -1)
            
            # Draw label
            label = f"{class_name}: {score:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            label_rect = ((x, y - label_size[1] - 10), (x + label_size[0], y))
            cv2.rectangle(annotated_frame, label_rect[0], label_rect[1], color, -1)
            cv2.putText(
                annotated_frame, 
                label, 
                (x, y - 5), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (255, 255, 255), 
                1
            )
        
        return annotated_frame
    
    def initialize_tracking(self, frame: np.ndarray, roi: Tuple[int, int, int, int]):
        """
        Initialize tracking for a specific region of interest
        ROI format: (x, y, width, height)
        """
        if not self.model:
            return None
            
        # Use the built-in OpenCV tracker
        tracker = cv2.TrackerCSRT_create()  # Using CSRT tracker for high accuracy
        success = tracker.init(frame, roi)
        
        if success:
            obj_id = self.next_object_id
            self.next_object_id += 1
            self.trackers[obj_id] = tracker
            return obj_id
        return None
    
    def update_tracking(self, frame: np.ndarray) -> Dict:
        """
        Update all active trackers
        """
        if not self.model:
            logger.warning("Model not available, returning empty tracks")
            return {}
            
        updated_tracks = {}
        
        for obj_id, tracker in list(self.trackers.items()):
            success, bbox = tracker.update(frame)
            
            if success:
                # Calculate center point
                x, y, w, h = map(int, bbox)
                center_x = int(x + w / 2)
                center_y = int(y + h / 2)
                
                updated_tracks[obj_id] = {
                    'bbox': bbox,
                    'center': (center_x, center_y),
                    'status': 'tracked'
                }
            else:
                # Remove failed tracker
                del self.trackers[obj_id]
        
        return updated_tracks
    
    def get_detection_color(self, class_id: int) -> Tuple[int, int, int]:
        """
        Get a distinct color for each detection class
        """
        colors = [
            (255, 0, 0),    # Blue
            (0, 255, 0),    # Green
            (0, 0, 255),    # Red
            (255, 255, 0),  # Cyan
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Yellow
            (128, 0, 128),  # Purple
            (255, 165, 0),  # Orange
            (128, 128, 0),  # Olive
            (0, 128, 128),  # Teal
        ]
        return colors[class_id % len(colors)]
    
    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Dict]]:
        """
        Process a single frame for detection and tracking
        """
        return self.detect_and_track(frame)
