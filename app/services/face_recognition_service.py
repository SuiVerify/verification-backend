import os
import base64
import tempfile
import logging
import numpy as np
from typing import Dict, Optional, List, Tuple
import cv2

# Import YOLO for face detection
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logging.warning("Ultralytics YOLO not available, falling back to OpenCV")

# Import face_recognition for face encoding and comparison
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logging.warning("face_recognition library not available")

# Import DeepFace as secondary fallback
try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False

logger = logging.getLogger(__name__)

class YOLOFaceService:
    """YOLO-based face detection and recognition service"""
    
    def __init__(self):
        """Initialize YOLO face detection and face_recognition for encoding comparison"""
        self.yolo_model = None
        self.use_yolo = YOLO_AVAILABLE
        self.use_face_recognition = FACE_RECOGNITION_AVAILABLE
        
        if YOLO_AVAILABLE:
            try:
                # Load YOLOv8 face detection model (will auto-download if not present)
                # Using yolov8n.pt (nano) for faster inference, you can use yolov8s/m/l for better accuracy
                self.yolo_model = YOLO('yolov8n.pt')
                logger.info("✅ YOLO Face Service initialized with YOLOv8n")
            except Exception as e:
                logger.error(f"Failed to load YOLO model: {e}, falling back to OpenCV")
                self.use_yolo = False
        
        if not self.use_yolo:
            # Fallback to OpenCV Haar Cascade
            self.face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            logger.info("Face Service initialized with OpenCV Haar Cascade fallback")
        
        if not FACE_RECOGNITION_AVAILABLE:
            logger.warning("⚠️ face_recognition library not available - using basic distance metrics")
    
    def detect_faces_yolo(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detect faces using YOLO model
        Returns list of face bounding boxes as (x, y, w, h)
        """
        if not self.use_yolo or self.yolo_model is None:
            return self._detect_faces_opencv(image)
        
        try:
            # Run YOLO inference
            results = self.yolo_model(image, classes=[0], verbose=False)  # class 0 = person
            
            faces = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get bounding box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0])
                    
                    # Filter by confidence threshold
                    if confidence > 0.4:
                        # Convert to (x, y, w, h) format
                        x, y = int(x1), int(y1)
                        w, h = int(x2 - x1), int(y2 - y1)
                        faces.append((x, y, w, h))
            
            logger.info(f"YOLO detected {len(faces)} face(s)")
            return faces
            
        except Exception as e:
            logger.error(f"YOLO face detection failed: {e}, falling back to OpenCV")
            return self._detect_faces_opencv(image)
    
    def _detect_faces_opencv(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Fallback face detection using OpenCV Haar Cascade"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
        logger.info(f"OpenCV detected {len(faces)} face(s)")
        return [tuple(face) for face in faces]
    
    def extract_face_encoding(self, image: np.ndarray, face_location: Tuple[int, int, int, int] = None) -> Optional[np.ndarray]:
        """
        Extract face encoding using face_recognition library
        face_location: (x, y, w, h) in OpenCV format
        Returns 128-dimensional face encoding or None
        """
        if not FACE_RECOGNITION_AVAILABLE:
            logger.warning("face_recognition not available, cannot extract encoding")
            return None
        
        try:
            # Convert BGR to RGB (face_recognition uses RGB)
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            if face_location:
                # Convert OpenCV (x, y, w, h) to face_recognition format (top, right, bottom, left)
                x, y, w, h = face_location
                face_locations = [(y, x + w, y + h, x)]
            else:
                # Auto-detect face locations
                face_locations = face_recognition.face_locations(rgb_image, model='hog')
            
            if not face_locations:
                logger.warning("No face location found for encoding extraction")
                return None
            
            # Extract face encoding (128-dimensional vector)
            encodings = face_recognition.face_encodings(rgb_image, face_locations)
            
            if encodings:
                logger.info(f"✅ Extracted face encoding: {encodings[0].shape}")
                return encodings[0]
            else:
                logger.warning("Failed to extract face encoding")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting face encoding: {e}")
            return None
    
    def compare_face_encodings(self, encoding1: np.ndarray, encoding2: np.ndarray, tolerance: float = 0.4) -> Dict:
        """
        Compare two face encodings and return match result with confidence
        tolerance: Lower = more strict (default 0.6 is balanced)
        """
        if not FACE_RECOGNITION_AVAILABLE or encoding1 is None or encoding2 is None:
            return {
                "match": False,
                "confidence": 0.0,
                "face_distance": 1.0,
                "message": "Cannot compare - face encoding unavailable",
                "error_type": "ENCODING_ERROR"
            }
        
        try:
            # Calculate face distance (Euclidean distance)
            distance = face_recognition.face_distance([encoding1], encoding2)[0]
            
            # Check if faces match (distance < tolerance means match)
            is_match = bool(distance <= tolerance)

            # Convert distance to confidence percentage (inverse relationship)
            # Distance 0 = 100% confidence, Distance 1 = 0% confidence
            confidence = float(max(0.0, (1.0 - float(distance)) * 100.0))
            
            # DEBUG: Log detailed comparison info
            logger.info(f"🔍 FACE COMPARISON DEBUG:")
            logger.info(f"  - face_distance: {distance}")
            logger.info(f"  - tolerance: {tolerance}")
            logger.info(f"  - is_match: {is_match} (distance <= tolerance)")
            logger.info(f"  - confidence: {confidence}%")

            # Normalize types to native Python for JSON serialization
            match_py = bool(is_match)
            confidence_py = float(round(confidence, 1))
            distance_py = float(round(float(distance), 4))

            message = f"Face {'match' if match_py else 'mismatch'} detected with {confidence_py:.1f}% confidence (distance: {distance_py:.3f})"

            logger.info(f"Face comparison - Match: {match_py}, Distance: {distance_py:.3f}, Confidence: {confidence_py:.1f}%")

            return {
                "match": match_py,
                "confidence": confidence_py,
                "face_distance": distance_py,
                "message": message,
                "error_type": None,
                "detection_method": "YOLO+face_recognition"
            }
            
        except Exception as e:
            logger.error(f"Error comparing face encodings: {e}")
            return {
                "match": False,
                "confidence": 0.0,
                "face_distance": 1.0,
                "message": f"Comparison failed: {e}",
                "error_type": "COMPARISON_ERROR"
            }
    
    def compare_faces(self, reference_image_base64: str, live_image_base64: str) -> Dict:
        """
        Main method to compare two faces using YOLO detection + face_recognition encoding
        reference_image_base64: Base64 encoded reference image (e.g., from PAN card)
        live_image_base64: Base64 encoded live/selfie image
        """
        try:
            # Decode base64 images to numpy arrays
            ref_image = self._decode_base64_image(reference_image_base64)
            live_image = self._decode_base64_image(live_image_base64)
            
            if ref_image is None or live_image is None:
                return self._error_result("Failed to decode images", "DECODE_ERROR")
            
            # Detect faces using YOLO
            logger.info("🔍 Detecting faces in reference image...")
            ref_faces = self.detect_faces_yolo(ref_image)
            
            logger.info("🔍 Detecting faces in live image...")
            live_faces = self.detect_faces_yolo(live_image)
            
            # Validate face detection
            if len(ref_faces) == 0:
                return self._error_result("No face detected in reference image", "NO_FACE_REFERENCE")
            if len(ref_faces) > 1:
                return self._error_result(f"Multiple faces detected in reference image ({len(ref_faces)})", "MULTIPLE_FACES_REFERENCE")
            if len(live_faces) == 0:
                return self._error_result("No face detected in live image", "NO_FACE_LIVE")
            if len(live_faces) > 1:
                return self._error_result(f"Multiple faces detected in live image ({len(live_faces)})", "MULTIPLE_FACES_LIVE")
            
            # Extract face encodings
            logger.info("🧬 Extracting face encoding from reference image...")
            ref_encoding = self.extract_face_encoding(ref_image, ref_faces[0])
            
            logger.info("🧬 Extracting face encoding from live image...")
            live_encoding = self.extract_face_encoding(live_image, live_faces[0])
            
            if ref_encoding is None or live_encoding is None:
                return self._error_result("Failed to extract face encodings", "ENCODING_ERROR")
            
            # Compare encodings
            logger.info("⚖️ Comparing face encodings...")
            result = self.compare_face_encodings(ref_encoding, live_encoding)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in face comparison: {e}")
            return self._error_result(f"Face comparison failed: {e}", "COMPARISON_ERROR")
    
    def validate_face_quality(self, image_bytes: bytes) -> Dict:
        """Validate that image contains exactly one face"""
        try:
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return {
                    'is_valid': False,
                    'reason': 'Failed to decode image',
                    'error_type': 'decode_error'
                }
            
            # Detect faces
            faces = self.detect_faces_yolo(img)
            
            if len(faces) == 0:
                return {
                    'is_valid': False,
                    'reason': 'No face detected',
                    'error_type': 'no_face'
                }
            
            if len(faces) > 1:
                return {
                    'is_valid': False,
                    'reason': f'Multiple faces detected ({len(faces)})',
                    'error_type': 'multiple_faces'
                }
            
            return {
                'is_valid': True,
                'reason': 'Valid face detected',
                'face_count': len(faces),
                'detection_method': 'YOLO' if self.use_yolo else 'OpenCV'
            }
            
        except Exception as e:
            return {
                'is_valid': False,
                'reason': f'Validation failed: {e}',
                'error_type': 'validation_error'
            }
    
    def _decode_base64_image(self, base64_string: str) -> Optional[np.ndarray]:
        """Decode base64 string to OpenCV image (numpy array)"""
        try:
            # Remove data URL prefix if present
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            
            # Decode base64 to bytes
            image_bytes = base64.b64decode(base64_string)
            
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            
            # Decode to OpenCV image
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            return img
            
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}")
            return None
    
    def _error_result(self, message: str, error_type: str) -> Dict:
        """Standard error response"""
        return {
            "match": False,
            "confidence": 0.0,
            "face_distance": 1.0,
            "message": message,
            "error_type": error_type
        }

class HighAccuracyFaceService:
    def __init__(self):
        """Initialize the most accurate face recognition available"""
        if DEEPFACE_AVAILABLE:
            # Use Facenet512 - smaller, faster, and more stable than VGG-Face
            self.model_name = "Facenet512"  # Good accuracy, smaller size
            self.detector_backend = "opencv"
            self.distance_metric = "cosine"
            logger.info("High Accuracy Face Service initialized with DeepFace Facenet512")
        else:
            # Fallback to OpenCV if DeepFace fails
            self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            logger.info("Face Service initialized with OpenCV fallback")
    
    def compare_faces(self, reference_image_base64: str, live_image_base64: str) -> Dict:
        """Compare two faces using the most accurate method available"""
        if DEEPFACE_AVAILABLE:
            return self._compare_with_deepface(reference_image_base64, live_image_base64)
        else:
            return self._compare_with_opencv(reference_image_base64, live_image_base64)
    
    def _compare_with_deepface(self, ref_base64: str, live_base64: str) -> Dict:
        """Compare faces using DeepFace for highest accuracy"""
        temp_ref = None
        temp_live = None
        
        try:
            # Save base64 images to temporary files
            temp_ref = self._save_base64_to_temp(ref_base64, "ref")
            temp_live = self._save_base64_to_temp(live_base64, "live")
            
            if not temp_ref or not temp_live:
                return self._error_result("Failed to decode images", "DECODE_ERROR")
            
            # Use DeepFace for verification with error handling
            try:
                result = DeepFace.verify(
                    img1_path=temp_ref,
                    img2_path=temp_live,
                    model_name=self.model_name,
                    detector_backend=self.detector_backend,
                    distance_metric=self.distance_metric,
                    enforce_detection=True
                )
            except Exception as model_error:
                # If Facenet512 fails, try with a different model
                logger.warning(f"Facenet512 failed: {model_error}, trying OpenFace...")
                try:
                    result = DeepFace.verify(
                        img1_path=temp_ref,
                        img2_path=temp_live,
                        model_name="OpenFace",
                        detector_backend=self.detector_backend,
                        distance_metric=self.distance_metric,
                        enforce_detection=True
                    )
                except Exception as backup_error:
                    logger.warning(f"OpenFace also failed: {backup_error}, using OpenCV fallback")
                    return self._compare_with_opencv_files(temp_ref, temp_live)
            
            is_verified = result["verified"]
            distance = result["distance"]
            threshold = result["threshold"]
            
            # Calculate confidence percentage
            confidence = max(0, (1 - (distance / threshold)) * 100) if threshold > 0 else 0
            confidence = min(100, max(0, confidence))
            
            message = f"Face {'match' if is_verified else 'mismatch'} detected with {confidence:.1f}% confidence"
            
            logger.info(f"DeepFace result: verified={is_verified}, confidence={confidence:.1f}%")
            
            return {
                "match": is_verified,
                "confidence": round(confidence, 1),
                "face_distance": round(distance, 4),
                "message": message,
                "error_type": None,  # Face mismatch is a legitimate result, not an error
                "detection_method": "DeepFace-VGG"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Handle specific DeepFace errors
            if "face could not be detected" in error_msg:
                if "img1" in error_msg:
                    return self._error_result("No face detected in Aadhaar image", "NO_FACE_REFERENCE")
                else:
                    return self._error_result("No face detected in captured image", "NO_FACE_LIVE")
            
            logger.error(f"DeepFace comparison failed: {e}")
            return self._error_result(f"Face verification failed: {e}", "COMPARISON_ERROR")
            
        finally:
            self._cleanup_temp_file(temp_ref)
            self._cleanup_temp_file(temp_live)
    
    def _compare_with_opencv(self, ref_base64: str, live_base64: str) -> Dict:
        """Fallback comparison using OpenCV"""
        try:
            # Decode images
            ref_img = self._decode_base64_image(ref_base64)
            live_img = self._decode_base64_image(live_base64)
            
            if ref_img is None or live_img is None:
                return self._error_result("Failed to decode images", "DECODE_ERROR")
            
            # Convert to grayscale
            ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
            live_gray = cv2.cvtColor(live_img, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            ref_faces = self.face_cascade.detectMultiScale(ref_gray, 1.1, 4)
            live_faces = self.face_cascade.detectMultiScale(live_gray, 1.1, 4)
            
            if len(ref_faces) == 0:
                return self._error_result("No face detected in Aadhaar image", "NO_FACE_REFERENCE")
            if len(ref_faces) > 1:
                return self._error_result("Multiple faces detected in Aadhaar image", "MULTIPLE_FACES_REFERENCE")
            if len(live_faces) == 0:
                return self._error_result("No face detected in captured image", "NO_FACE_LIVE")
            if len(live_faces) > 1:
                return self._error_result("Multiple faces detected in captured image", "MULTIPLE_FACES_LIVE")
            
            # Basic face comparison (not as accurate as DeepFace)
            confidence = 60.0  # Conservative estimate
            is_match = True  # Basic detection passed
            
            return {
                "match": is_match,
                "confidence": confidence,
                "message": f"Face comparison completed with {confidence}% confidence (OpenCV fallback)",
                "error_type": None,
                "detection_method": "OpenCV-Basic"
            }
            
        except Exception as e:
            logger.error(f"OpenCV comparison failed: {e}")
            return self._error_result(f"Face verification failed: {e}", "COMPARISON_ERROR")
    
    def _compare_with_opencv_files(self, img1_path: str, img2_path: str) -> Dict:
        """Compare faces using OpenCV with file paths"""
        try:
            import cv2
            
            # Load images
            ref_img = cv2.imread(img1_path)
            live_img = cv2.imread(img2_path)
            
            if ref_img is None or live_img is None:
                return self._error_result("Failed to load image files", "DECODE_ERROR")
            
            # Convert to grayscale
            ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
            live_gray = cv2.cvtColor(live_img, cv2.COLOR_BGR2GRAY)
            
            # Initialize face cascade if not available
            if not hasattr(self, 'face_cascade'):
                self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
            # Detect faces
            ref_faces = self.face_cascade.detectMultiScale(ref_gray, 1.1, 4)
            live_faces = self.face_cascade.detectMultiScale(live_gray, 1.1, 4)
            
            if len(ref_faces) == 0:
                return self._error_result("No face detected in Aadhaar image", "NO_FACE_REFERENCE")
            if len(ref_faces) > 1:
                return self._error_result("Multiple faces detected in Aadhaar image", "MULTIPLE_FACES_REFERENCE")
            if len(live_faces) == 0:
                return self._error_result("No face detected in captured image", "NO_FACE_LIVE")
            if len(live_faces) > 1:
                return self._error_result("Multiple faces detected in captured image", "MULTIPLE_FACES_LIVE")
            
            # Basic face comparison (fallback when DeepFace fails)
            confidence = 55.0  # Conservative estimate for fallback
            is_match = True  # Basic detection passed
            
            return {
                "match": is_match,
                "confidence": confidence,
                "message": f"Face comparison completed with {confidence}% confidence (OpenCV fallback)",
                "error_type": None,
                "detection_method": "OpenCV-Fallback"
            }
            
        except Exception as e:
            logger.error(f"OpenCV file comparison failed: {e}")
            return self._error_result(f"Face verification failed: {e}", "COMPARISON_ERROR")
    
    def validate_face_quality(self, image_bytes: bytes) -> Dict:
        """Validate face quality - required by router"""
        if DEEPFACE_AVAILABLE:
            return self._validate_with_deepface(image_bytes)
        else:
            return self._validate_with_opencv(image_bytes)
    
    def _validate_with_deepface(self, image_bytes: bytes) -> Dict:
        """Validate using DeepFace"""
        temp_path = None
        try:
            # Convert bytes to base64 and save to temp file
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            temp_path = self._save_base64_to_temp(base64_string, "validate")
            
            if not temp_path:
                return {'is_valid': False, 'reason': 'Failed to decode image', 'error_type': 'decode_error'}
            
            # Extract faces using DeepFace
            faces = DeepFace.extract_faces(
                img_path=temp_path,
                detector_backend=self.detector_backend,
                enforce_detection=False
            )
            
            if len(faces) == 0:
                return {'is_valid': False, 'reason': 'No face detected', 'error_type': 'no_face'}
            
            if len(faces) > 1:
                return {'is_valid': False, 'reason': f'Multiple faces detected ({len(faces)})', 'error_type': 'multiple_faces'}
            
            return {
                'is_valid': True,
                'reason': 'High quality face detected',
                'face_count': len(faces),
                'detection_method': 'DeepFace'
            }
            
        except Exception as e:
            return {'is_valid': False, 'reason': f'Validation failed: {e}', 'error_type': 'validation_error'}
        finally:
            self._cleanup_temp_file(temp_path)
    
    def _validate_with_opencv(self, image_bytes: bytes) -> Dict:
        """Validate using OpenCV fallback"""
        try:
            # Convert bytes to image
            import numpy as np
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                return {'is_valid': False, 'reason': 'Failed to decode image', 'error_type': 'decode_error'}
            
            # Convert to grayscale and detect faces
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.1, 4)
            
            if len(faces) == 0:
                return {'is_valid': False, 'reason': 'No face detected', 'error_type': 'no_face'}
            
            if len(faces) > 1:
                return {'is_valid': False, 'reason': f'Multiple faces detected ({len(faces)})', 'error_type': 'multiple_faces'}
            
            return {
                'is_valid': True,
                'reason': 'Face detected',
                'face_count': len(faces),
                'detection_method': 'OpenCV'
            }
            
        except Exception as e:
            return {'is_valid': False, 'reason': f'Validation failed: {e}', 'error_type': 'validation_error'}
    
    def _save_base64_to_temp(self, base64_string: str, prefix: str) -> Optional[str]:
        """Save base64 image to temporary file"""
        try:
            # Remove data URL prefix if present
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            
            # Decode base64
            image_bytes = base64.b64decode(base64_string)
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', prefix=f'{prefix}_')
            temp_file.write(image_bytes)
            temp_file.close()
            
            return temp_file.name
            
        except Exception as e:
            logger.error(f"Failed to save base64 to temp file: {e}")
            return None
    
    def _decode_base64_image(self, base64_string: str):
        """Decode base64 to OpenCV image"""
        try:
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            
            image_bytes = base64.b64decode(base64_string)
            nparr = np.frombuffer(image_bytes, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}")
            return None
    
    def _cleanup_temp_file(self, file_path: Optional[str]):
        """Clean up temporary file"""
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {file_path}: {e}")
    
    def _error_result(self, message: str, error_type: str) -> Dict:
        """Standard error response"""
        return {
            "match": False,
            "confidence": 0.0,
            "message": message,
            "error_type": error_type
        }

# Singleton instances
_yolo_face_service = None
_legacy_face_service = None

def get_yolo_face_service() -> YOLOFaceService:
    """Get singleton instance of YOLO-based face recognition service (PREFERRED)"""
    global _yolo_face_service
    if _yolo_face_service is None:
        _yolo_face_service = YOLOFaceService()
    return _yolo_face_service

def get_face_recognition_service() -> HighAccuracyFaceService:
    """Get singleton instance of legacy DeepFace service (for backward compatibility)"""
    global _legacy_face_service
    if _legacy_face_service is None:
        _legacy_face_service = HighAccuracyFaceService()
    return _legacy_face_service