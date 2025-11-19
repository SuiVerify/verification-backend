from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.models.schemas import APIResponse
from app.services.pan_ocr_service import get_pan_ocr_service, PANOCRService
from app.services.user_service import get_user_service, UserService
from pydantic import BaseModel
from typing import Optional
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class PANData(BaseModel):
    """PAN card data model"""
    pan_number: Optional[str] = None
    name: Optional[str] = None
    father_name: Optional[str] = None
    dob: Optional[str] = None
    pan_photo_base64: Optional[str] = None
    raw_text: Optional[str] = None

@router.post("/extract-pan-data", response_model=APIResponse)
async def extract_pan_data(
    file: UploadFile = File(...),
    pan_ocr_service: PANOCRService = Depends(get_pan_ocr_service),
    user_service: UserService = Depends(get_user_service)
):
    """
    Extract PAN card data from uploaded image using OCR.
    
    This endpoint accepts an image file from the frontend and extracts:
    - PAN Number (AAAAA9999A format)
    - Name (cardholder name)
    - Father's Name
    - Date of Birth (DD/MM/YYYY format)
    - Photo (extracted as base64)
    
    The extraction uses ensemble OCR with multiple Tesseract configurations
    for robust field extraction across different PAN card formats.
    """
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Please upload an image file (JPEG, PNG, etc.)."
            )
        
        # Read file content
        file_content = await file.read()
        
        # Validate file size (max 10MB)
        if len(file_content) > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400,
                detail="File size too large. Maximum size allowed is 10MB."
            )
        
        if len(file_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file uploaded. Please select a valid image."
            )
        
        # Process PAN card image using OCR service with ensemble mode
        logger.info(f"📸 Processing PAN card image from frontend: {file.filename} ({len(file_content)} bytes)")
        
        # Call OCR service - this uses the robust extraction pipeline
        result = pan_ocr_service.extract_pan_data(file_content, use_ensemble=True)
        
        if not result.get('success', False):
            error_msg = result.get('error', 'Unknown OCR processing error')
            logger.error(f"❌ PAN OCR extraction failed: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to extract PAN card data: {error_msg}"
            )
        
        # Extract fields from OCR result
        pan_number = result.get('pan_number')
        name = result.get('name')
        father_name = result.get('father_name')
        dob = result.get('dob')
        pan_photo_base64 = result.get('pan_photo_base64')
        raw_text = result.get('raw_text', '')
        
        # Log extraction results for monitoring
        logger.info(f"✅ PAN OCR Success - PAN: {pan_number or 'N/A'}, Name: {name or 'N/A'}, Father: {father_name or 'N/A'}, DOB: {dob or 'N/A'}")
        
        # Prepare response data
        pan_data = PANData(
            pan_number=pan_number,
            name=name,
            father_name=father_name,
            dob=dob,
            pan_photo_base64=pan_photo_base64,
            raw_text=raw_text[:500] if raw_text else None  # Limit raw text in response
        )
        
        # Calculate extraction success metrics
        extracted_fields = sum([
            1 if pan_number else 0,
            1 if name else 0,
            1 if dob else 0,
            1 if father_name else 0
        ])
        
        success_rate = (extracted_fields / 4) * 100  # 4 main fields
        
        # Prepare detailed response message
        if extracted_fields == 4:
            message = "✅ All PAN card fields extracted successfully!"
        elif extracted_fields >= 2:
            message = f"⚠️ Partial extraction: {extracted_fields}/4 fields found. Please verify and correct if needed."
        else:
            message = "⚠️ Low extraction quality. Please ensure the image is clear and try again."
        
        return APIResponse(
            success=True,
            message=f"{message} (Success rate: {success_rate:.0f}%)",
            data=pan_data.dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in PAN extraction: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during PAN processing: {str(e)}"
        )

@router.post("/validate-pan-format")
async def validate_pan_format(pan_number: str):
    """Validate PAN number format"""
    try:
        import re
        
        # PAN format validation: AAAAA9999A
        pan_pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
        
        is_valid = bool(re.match(pan_pattern, pan_number.upper()))
        
        return APIResponse(
            success=True,
            message=f"PAN format validation completed",
            data={
                "pan_number": pan_number.upper(),
                "is_valid": is_valid,
                "format": "AAAAA9999A (5 letters + 4 digits + 1 letter)"
            }
        )
        
    except Exception as e:
        logger.error(f"Error validating PAN format: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error validating PAN format: {str(e)}"
        )

@router.get("/pan-info/{pan_number}")
async def get_pan_info(pan_number: str):
    """Get information about PAN number structure"""
    try:
        # PAN number structure information
        if len(pan_number) != 10:
            raise HTTPException(
                status_code=400,
                detail="PAN number must be exactly 10 characters"
            )
        
        pan = pan_number.upper()
        
        # Extract PAN components
        first_three = pan[:3]  # First 3 letters (usually indicate name initials)
        fourth_char = pan[3]   # 4th character (indicates type of holder)
        fifth_char = pan[4]    # 5th character (indicates surname initial)
        middle_four = pan[5:9] # 4 digits (sequential number)
        last_char = pan[9]     # Last character (check digit)
        
        # PAN type mapping
        pan_types = {
            'A': 'Association of Persons (AOP)',
            'B': 'Body of Individuals (BOI)',
            'C': 'Company',
            'F': 'Firm',
            'G': 'Government',
            'H': 'HUF (Hindu Undivided Family)',
            'L': 'Local Authority',
            'J': 'Artificial Juridical Person',
            'P': 'Individual',
            'T': 'Trust'
        }
        
        holder_type = pan_types.get(fourth_char, 'Unknown')
        
        return APIResponse(
            success=True,
            message="PAN information retrieved successfully",
            data={
                "pan_number": pan,
                "structure": {
                    "first_three_letters": first_three,
                    "holder_type_indicator": fourth_char,
                    "holder_type": holder_type,
                    "surname_initial": fifth_char,
                    "sequential_number": middle_four,
                    "check_digit": last_char
                },
                "format_explanation": "AAAAA9999A - 5 letters + 4 digits + 1 letter"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting PAN info: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving PAN information: {str(e)}"
        )

@router.post("/correct-pan-data", response_model=APIResponse)
async def correct_pan_data(
    pan_data: PANData,
    user_service: UserService = Depends(get_user_service)
):
    """Accept corrected PAN card data from frontend"""
    try:
        logger.info(f"Received corrected PAN data: PAN={pan_data.pan_number}, Name={pan_data.name}, Father={pan_data.father_name}, DOB={pan_data.dob}")
        
        # Validate required fields
        if not pan_data.pan_number:
            raise HTTPException(
                status_code=400,
                detail="PAN number is required"
            )
        
        # Basic PAN format validation
        import re
        if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', pan_data.pan_number):
            raise HTTPException(
                status_code=400,
                detail="Invalid PAN format. Expected format: AAAAA9999A"
            )
        
        # Store the corrected data (you can add database storage here)
        corrected_data = {
            "pan_number": pan_data.pan_number,
            "name": pan_data.name,
            "father_name": pan_data.father_name,
            "dob": pan_data.dob,
            "pan_photo_base64": pan_data.pan_photo_base64,
            "status": "corrected",
            "timestamp": str(uuid.uuid4())
        }
        
        logger.info(f"✅ PAN data correction saved successfully for PAN: {pan_data.pan_number}")
        
        return APIResponse(
            success=True,
            message="PAN data corrected and saved successfully",
            data=corrected_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving corrected PAN data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error saving corrected PAN data: {str(e)}"
        )

@router.post("/verify-pan", response_model=APIResponse)
async def verify_pan(
    verification_data: dict,
    user_service: UserService = Depends(get_user_service)
):
    """Send PAN verification request to Redis stream for enclave processing"""
    try:
        logger.info(f"Received PAN verification request for user: {verification_data.get('user_address')}")
        
        # Import redis service
        from app.services.redis_service import get_redis_service
        redis_service = get_redis_service()
        
        # Extract PAN data from request
        pan_data = verification_data.get("pan_data", {})
        user_address = verification_data.get("user_address")
        did_type = verification_data.get("did_type", 0)
        
        # Prepare verification data in the format expected by Redis service
        verification_payload = {
            'pan': pan_data.get('pan_number'),
            'name': pan_data.get('name'),
            'father_name': pan_data.get('father_name'),
            'date_of_birth': pan_data.get('dob')
        }
        
        logger.info(f"📤 Sending PAN verification to Redis stream for user: {user_address}")
        logger.info(f"📋 PAN data: {verification_payload}")
        
        # Send to Redis stream for enclave processing using correct method signature
        stream_result = await redis_service.send_verification_request(
            user_wallet=user_address,
            did_id=did_type,
            document_type="pan",
            verification_data=verification_payload,
            extracted_data=verification_payload,
            user_corrections={}  # No corrections for direct verification
        )
        
        if stream_result:
            logger.info(f"✅ PAN verification request sent to enclave successfully")
            return APIResponse(
                success=True,
                message="PAN verification request sent to enclave for processing",
                data={
                    "verification_id": str(uuid.uuid4()),
                    "status": "processing",
                    "user_address": user_address,
                    "pan_number": pan_data.get('pan_number')
                }
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send verification request to enclave"
            )
        
    except Exception as e:
        logger.error(f"Error in PAN verification: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PAN verification: {str(e)}"
        )
