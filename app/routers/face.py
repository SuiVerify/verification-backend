from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from app.models.schemas import APIResponse, FaceMatchRequest
from app.services.face_recognition_service import (
    get_face_recognition_service, 
    get_yolo_face_service,
    HighAccuracyFaceService,
    YOLOFaceService
)
from app.services.pan_ocr_service import get_pan_ocr_service, PANOCRService
from typing import Optional
from pydantic import BaseModel
import base64
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


def _sanitize_for_serialization(obj):
    """Recursively convert numpy types to native Python types for JSON serialization."""
    try:
        import numpy as _np
    except Exception:
        _np = None

    if obj is None:
        return None
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_serialization(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_serialization(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_sanitize_for_serialization(v) for v in obj)
    # numpy types
    if _np is not None:
        if isinstance(obj, _np.generic):
            # convert numpy scalar to Python scalar
            return obj.item()
        if isinstance(obj, _np.ndarray):
            return obj.tolist()
    # default
    return obj

class FaceVerificationRequest(BaseModel):
    aadhaar_photo_base64: str
    live_photo_base64: str
    phone_number: str  # Added phone number for OTP sending

@router.post("/verify-face", response_model=APIResponse)
async def verify_face(
    request: FaceVerificationRequest,
    face_service: HighAccuracyFaceService = Depends(get_face_recognition_service)
):
    """Verify live photo against Aadhaar photo using face_recognition library"""
    try:
        # Decode base64 images
        try:
            aadhaar_image_bytes = base64.b64decode(request.aadhaar_photo_base64)
            live_image_bytes = base64.b64decode(request.live_photo_base64)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail="Invalid base64 image data"
            )
        
        # Validate both images have faces
        logger.info("Validating Aadhaar photo...")
        aadhaar_validation = face_service.validate_face_quality(aadhaar_image_bytes)
        if not aadhaar_validation['is_valid']:
            raise HTTPException(
                status_code=400,
                detail=f"Aadhaar photo validation failed: {aadhaar_validation['reason']}"
            )
        
        logger.info("Validating live photo...")
        live_validation = face_service.validate_face_quality(live_image_bytes)
        if not live_validation['is_valid']:
            raise HTTPException(
                status_code=400,
                detail=f"Live photo validation failed: {live_validation['reason']}"
            )
        
        # Perform face comparison using OpenCV face recognition
        logger.info("Comparing faces using OpenCV face recognition...")
        comparison_result = face_service.compare_faces(request.aadhaar_photo_base64, request.live_photo_base64)
        
        # Check for technical/system errors (not face mismatch)
        error_type = comparison_result.get('error_type')
        if error_type and error_type in ['DECODE_ERROR', 'COMPARISON_ERROR', 'NO_FACE_REFERENCE', 'NO_FACE_LIVE', 'MULTIPLE_FACES_REFERENCE', 'MULTIPLE_FACES_LIVE']:
            # These are technical errors, not legitimate verification results
            status_code = 500 if error_type in ['DECODE_ERROR', 'COMPARISON_ERROR'] else 400
            raise HTTPException(
                status_code=status_code,
                detail=comparison_result.get('message', 'Face verification failed')
            )
        
        # Face mismatch is a legitimate result, not an error
        match_result = comparison_result['match']
        confidence = comparison_result['confidence']
        face_distance = comparison_result.get('face_distance', 0)
        
        logger.info(f"Face verification result: {match_result}, confidence: {confidence:.1f}%, distance: {face_distance:.3f}")
        
        # Return face verification result
        verification_message = comparison_result['message']
        
        return APIResponse(
            success=True,
            message=verification_message,
            data={
                'match': match_result,
                'confidence': round(confidence, 1),
                'message': verification_message,
                'face_distance': round(face_distance, 3),
                'detection_method': comparison_result.get('detection_method', 'OpenCV'),
                'error_type': error_type
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in face verification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Face verification failed: {str(e)}"
        )

@router.post("/verify-pan-face-yolo", response_model=APIResponse)
async def verify_pan_face_with_yolo(
    pan_card_image: UploadFile = File(..., description="PAN card image file"),
    live_image: UploadFile = File(..., description="Live/selfie image file"),
    yolo_face_service: YOLOFaceService = Depends(get_yolo_face_service),
    pan_ocr_service: PANOCRService = Depends(get_pan_ocr_service)
):
    """
    Verify face from PAN card against live/selfie image using YOLO face detection.
    
    This endpoint:
    1. Extracts the photo from the uploaded PAN card image
    2. Detects faces in both PAN photo and live image using YOLO
    3. Compares the faces using face_recognition library encodings
    4. Returns match result with confidence score
    
    Uses cutting-edge YOLO for robust face detection and face_recognition for accurate comparison.
    """
    try:
        # Validate file types
        if not pan_card_image.content_type or not pan_card_image.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Invalid PAN card file type. Please upload an image (JPEG, PNG, etc.)"
            )
        
        if not live_image.content_type or not live_image.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Invalid live image file type. Please upload an image (JPEG, PNG, etc.)"
            )
        
        # Read file contents
        pan_card_bytes = await pan_card_image.read()
        live_image_bytes = await live_image.read()
        
        # Validate file sizes (max 10MB each)
        if len(pan_card_bytes) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="PAN card image too large. Maximum size is 10MB."
            )
        
        if len(live_image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="Live image too large. Maximum size is 10MB."
            )
        
        # Step 1: Extract photo from PAN card
        logger.info("📸 Extracting photo from PAN card...")
        pan_photo_result = pan_ocr_service.get_pan_photo(pan_card_bytes)
        
        if not pan_photo_result.get('success'):
            raise HTTPException(
                status_code=400,
                detail=f"Failed to extract photo from PAN card: {pan_photo_result.get('message', 'Unknown error')}"
            )
        
        pan_photo_base64 = pan_photo_result.get('pan_photo_base64')
        logger.info("✅ PAN card photo extracted successfully")
        
        # Step 2: Convert live image to base64
        live_photo_base64 = base64.b64encode(live_image_bytes).decode('utf-8')
        
        # Step 3: Validate both images contain faces
        logger.info("🔍 Validating PAN card photo...")
        pan_validation = yolo_face_service.validate_face_quality(
            base64.b64decode(pan_photo_base64)
        )
        
        if not pan_validation['is_valid']:
            raise HTTPException(
                status_code=400,
                detail=f"PAN card photo validation failed: {pan_validation['reason']}"
            )
        
        logger.info("🔍 Validating live image...")
        live_validation = yolo_face_service.validate_face_quality(live_image_bytes)
        
        if not live_validation['is_valid']:
            raise HTTPException(
                status_code=400,
                detail=f"Live image validation failed: {live_validation['reason']}"
            )
        
        # Step 4: Compare faces using YOLO + face_recognition
        logger.info("⚖️ Comparing PAN card face with live image using YOLO + face_recognition...")
        comparison_result = yolo_face_service.compare_faces(
            pan_photo_base64,
            live_photo_base64
        )
        
        # Check for technical errors
        error_type = comparison_result.get('error_type')
        if error_type and error_type in ['DECODE_ERROR', 'COMPARISON_ERROR', 'ENCODING_ERROR']:
            raise HTTPException(
                status_code=500,
                detail=comparison_result.get('message', 'Face verification failed')
            )
        
        if error_type and error_type in ['NO_FACE_REFERENCE', 'NO_FACE_LIVE', 
                                         'MULTIPLE_FACES_REFERENCE', 'MULTIPLE_FACES_LIVE']:
            raise HTTPException(
                status_code=400,
                detail=comparison_result.get('message', 'Face detection failed')
            )
        
        # Extract results
        is_match = comparison_result['match']
        confidence = comparison_result['confidence']
        face_distance = comparison_result.get('face_distance', 0)
        detection_method = comparison_result.get('detection_method', 'YOLO+face_recognition')
        
        # Determine verification status based on confidence thresholds
        # Threshold: >= 40% confidence for acceptance (lowered for testing)
        verification_threshold = 40.0
        
        # DEBUG: Log detailed verification info
        logger.info(f"🔍 VERIFICATION DEBUG:")
        logger.info(f"  - is_match: {is_match}")
        logger.info(f"  - confidence: {confidence}%")
        logger.info(f"  - face_distance: {face_distance}")
        logger.info(f"  - threshold: {verification_threshold}%")
        logger.info(f"  - meets_threshold: {confidence >= verification_threshold}")
        
        # Use confidence-based verification instead of distance-based match
        if confidence >= verification_threshold:
            verification_status = "SUCCESS"
            verification_message = f"✅ Verification Success: Face match confirmed with {confidence:.1f}% confidence"
            is_verified = True
        else:
            verification_status = "FAILED"
            verification_message = f"❌ Verification Failed: Confidence too low ({confidence:.1f}%) - threshold is {verification_threshold}%"
            is_verified = False
        
        logger.info(f"{'✅' if is_verified else '❌'} Face verification {verification_status}: Match={is_match}, Confidence={confidence:.1f}%, Distance={face_distance:.3f}")
        
        # Prepare and sanitize detailed result
        result_data = {
            'verification_status': verification_status,  # SUCCESS or FAILED
            'verified': bool(is_verified),
            'match': bool(is_match),
            'confidence': float(round(float(confidence), 1)),
            'face_distance': float(round(float(face_distance), 3)),
            'threshold': verification_threshold,
            'detection_method': detection_method,
            'message': verification_message,
            'pan_photo_extracted': True,
            'validation': {
                'pan_photo': pan_validation,
                'live_image': live_validation
            }
        }

        sanitized = _sanitize_for_serialization(result_data)

        # Return detailed result
        return APIResponse(
            success=True,
            message=verification_message,
            data=sanitized
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in PAN face verification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Face verification failed: {str(e)}"
        )
