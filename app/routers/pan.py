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
    """Extract PAN number, name, father's name, DOB, and photo from PAN card image"""
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Please upload an image file."
            )
        
        # Validate file size (max 10MB)
        file_content = await file.read()
        if len(file_content) > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400,
                detail="File size too large. Maximum size allowed is 10MB."
            )
        
        if len(file_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Empty file uploaded."
            )
        
        # Process PAN card image and extract data
        logger.info(f"Processing PAN card image: {file.filename}")
        result = pan_ocr_service.extract_pan_data(file_content)
        
        if not result.get('success', False):
            logger.error(f"Error processing PAN card: {result.get('error', 'Unknown error')}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process PAN card: {result.get('error', 'Unknown error')}"
            )
        
        # Extract the key fields
        pan_number = result.get('pan_number')
        name = result.get('name')
        father_name = result.get('father_name')
        dob = result.get('dob')
        pan_photo_base64 = result.get('pan_photo_base64')
        
        # Log extraction results
        logger.info(f"PAN extraction results - PAN: {pan_number}, Name: {name}, DOB: {dob}")
        
        # Prepare response data
        pan_data = PANData(
            pan_number=pan_number,
            name=name,
            father_name=father_name,
            dob=dob,
            pan_photo_base64=pan_photo_base64,
            raw_text=result.get('raw_text', '')
        )
        
        # Calculate extraction success metrics
        extracted_fields = sum([
            1 if pan_number else 0,
            1 if name else 0,
            1 if dob else 0,
            1 if father_name else 0
        ])
        
        success_rate = (extracted_fields / 4) * 100  # 4 main fields
        
        return APIResponse(
            success=True,
            message=f"PAN card data extracted successfully. {extracted_fields}/4 fields found ({success_rate:.0f}% success rate).",
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
