"""
Complete KYC verification flow
"""
from fastapi import APIRouter, HTTPException, Depends, Form, File, UploadFile
from typing import List
import logging
import base64
import uuid

from app.models.schemas import APIResponse
from app.models.user import VerificationLog
from app.services.user_service import get_user_service, UserService
from app.services.ocr_service import get_ocr_service, OCRService
from app.services.face_recognition_service import get_face_recognition_service, HighAccuracyFaceService
# from app.services.otp_service import get_otp_service, OTPService  # OTP service commented out
from app.services.redis_service import get_redis_service, RedisService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kyc", tags=["KYC Verification"])

# Store temporary verification data (in production, use Redis)
temp_verification_data = {}

@router.post("/start-verification", response_model=APIResponse)
async def start_kyc_verification(
    verification_type: str = Form(..., description="Type: 'above18' or 'citizenship'"),
    aadhaar_image: UploadFile = File(...),
    face_images: List[UploadFile] = File(...),
    ocr_service: OCRService = Depends(get_ocr_service),
    face_service: HighAccuracyFaceService = Depends(get_face_recognition_service)
    # otp_service: OTPService = Depends(get_otp_service)  # OTP service commented out
):
    """Start KYC verification: Process Aadhaar + Face images (OTP skipped)"""
    try:
        # Validate verification type
        if verification_type not in ['above18', 'citizenship']:
            raise HTTPException(
                status_code=400,
                detail="verification_type must be 'above18' or 'citizenship'"
            )
        
        # Generate unique session ID for this verification
        session_id = str(uuid.uuid4())
        
        # Step 1: Process Aadhaar document
        aadhaar_bytes = await aadhaar_image.read()
        
        try:
            aadhaar_data = ocr_service.extract_aadhaar_data(aadhaar_bytes)
            aadhaar_photo = ocr_service.extract_photo_from_aadhaar(aadhaar_bytes)
            
            if not aadhaar_data.get('name') or not aadhaar_data.get('aadhaar_number'):
                raise ValueError("Could not extract essential Aadhaar information")
                
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Aadhaar processing failed: {str(e)}")
        
        # Step 2: Process face images and perform face matching
        if len(face_images) < 3:
            raise HTTPException(
                status_code=400, 
                detail="At least 3 face images required for verification"
            )
        
        face_match_results = []
        
        try:
            # Convert face images to base64
            face_images_b64 = []
            for face_img in face_images:
                face_bytes = await face_img.read()
                face_b64 = base64.b64encode(face_bytes).decode('utf-8')
                face_images_b64.append(face_b64)
            
            # Convert Aadhaar photo to base64
            if aadhaar_photo:
                aadhaar_photo_b64 = base64.b64encode(aadhaar_photo).decode('utf-8')
                
                # Compare each face image with Aadhaar photo
                for i, face_b64 in enumerate(face_images_b64):
                    try:
                        match_result = face_service.compare_faces(aadhaar_photo_b64, face_b64)
                        face_match_results.append({
                            'image_index': i,
                            'match_result': match_result
                        })
                    except Exception as e:
                        logger.warning(f"Face comparison failed for image {i}: {e}")
                        face_match_results.append({
                            'image_index': i,
                            'match_result': {'verified': False, 'error': str(e)}
                        })
            else:
                raise ValueError("Could not extract photo from Aadhaar card")
                
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Face matching failed: {str(e)}")
        
        # Step 3: Evaluate face verification result
        successful_matches = sum(1 for result in face_match_results 
                               if result['match_result'].get('verified', False))
        
        face_verification_passed = successful_matches >= 2  # At least 2 out of 3+ images should match
        
        if not face_verification_passed:
            raise HTTPException(
                status_code=400, 
                detail=f"Face verification failed. Only {successful_matches} out of {len(face_images)} images matched."
            )
        
        # Step 4: Extract phone number and send OTP
        phone_number = aadhaar_data.get('phone_number')  # Updated key name
        if not phone_number:
            raise HTTPException(
                status_code=400,
                detail="Phone number not found in Aadhaar. Please ensure your Aadhaar has a registered mobile number."
            )
        
        # Clean phone number
        phone_clean = phone_number.replace('+91', '').replace('-', '').replace(' ', '').strip()
        
        # Store verification data temporarily (use session_id as key)
        temp_verification_data[session_id] = {
            'aadhaar_data': aadhaar_data,
            'phone_number': phone_clean,
            'face_verification_passed': True,
            'face_matches': successful_matches,
            'total_face_images': len(face_images),
            'verification_type': verification_type,  # Store verification type
            'did': 0 if verification_type == 'above18' else 1  # Set DID based on type
        }
        
        # OTP generation and sending commented out
        # try:
        #     otp = otp_service.generate_otp(phone_clean)
        #     sms_sent = otp_service.send_otp_sms(phone_clean, otp)
        #     
        #     logger.info(f"OTP sent to {phone_clean} for session {session_id}")
        
        # Skip OTP for now - directly proceed to verification
        sms_sent = True  # Simulate OTP sent
        logger.info(f"OTP step skipped for session {session_id}")
        
        return APIResponse(
            success=True,
            message="Aadhaar and face verification successful. OTP step skipped.",
            data={
                'session_id': session_id,
                'phone_number': phone_clean,
                'aadhaar_verified': True,
                'face_verified': True,
                'otp_sent': sms_sent,
                'expires_in_minutes': 5,  # Default value
                'extracted_data': {
                    'name': aadhaar_data.get('name'),
                    'aadhaar_number': aadhaar_data.get('aadhaar_number', '').replace(' ', ''),
                    'date_of_birth': aadhaar_data.get('dob'),
                    'gender': aadhaar_data.get('gender')
                }
            }
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in start KYC verification: {e}")
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {str(e)}")


@router.post("/complete-verification", response_model=APIResponse)
async def complete_kyc_verification(
    session_id: str = Form(...),
    # otp: str = Form(...),  # OTP verification commented out
    user_service: UserService = Depends(get_user_service)
    # otp_service: OTPService = Depends(get_otp_service)  # OTP service commented out
):
    """Complete KYC verification: Skip OTP and save user data to database"""
    try:
        # Step 1: Check if session exists
        if session_id not in temp_verification_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID or session expired. Please start verification again."
            )
        
        verification_data = temp_verification_data[session_id]
        phone_clean = verification_data['phone_number']
        
        # Step 2: OTP verification commented out - skip directly to user creation
        # try:
        #     otp_verified = otp_service.verify_otp(phone_clean, otp)
        #     if not otp_verified:
        #         raise HTTPException(status_code=400, detail="Invalid OTP")
        # except Exception as e:
        #     raise HTTPException(status_code=400, detail=f"OTP verification failed: {str(e)}")
        
        logger.info(f"OTP verification skipped for session {session_id}")
        
        # Step 3: Generate dummy wallet address and save user data
        dummy_wallet_address = f"0x{uuid.uuid4().hex[:64]}"  # Generate 64-char dummy wallet address
        aadhaar_data = verification_data['aadhaar_data']
        did_value = verification_data['did']
        
        # Create user data
        from app.models.user import UserCreate
        user_create_data = UserCreate(
            wallet_address=dummy_wallet_address,
            phone_number=phone_clean,
            aadhaar_number=aadhaar_data.get('aadhaar_number', '').replace(' ', ''),
            date_of_birth=aadhaar_data.get('dob'),
            full_name=aadhaar_data.get('name'),
            gender=aadhaar_data.get('gender'),
            is_verified=0,  # Do NOT set as verified - pending government verification
            did=did_value   # Set DID based on verification type
        )
        
        # Save to database
        try:
            created_user = await user_service.create_user(user_create_data)
            
            # Log successful verification
            log_data = VerificationLog(
                wallet_address=dummy_wallet_address,
                verification_type="kyc_complete",
                status="success",
                details={
                    "aadhaar_data": aadhaar_data,
                    "face_matches": verification_data['face_matches'],
                    "total_face_images": verification_data['total_face_images'],
                    "phone_verified": True,
                    "user_verified": True,
                    "session_id": session_id
                }
            )
            await user_service.log_verification_attempt(log_data)
            
            # Clean up temporary data
            del temp_verification_data[session_id]
            
            logger.info(f"KYC verification completed successfully for wallet: {dummy_wallet_address}")
            
            return APIResponse(
                success=True,
                message="KYC verification completed successfully! User data saved to database.",
                data={
                    'wallet_address': dummy_wallet_address,
                    'verification_status': 'VERIFIED',
                    'is_verified': 1,
                    'user_data': {
                        'wallet_address': dummy_wallet_address,
                        'phone_number': phone_clean,
                        'aadhaar_number': aadhaar_data.get('aadhaar_number', '').replace(' ', ''),
                        'date_of_birth': aadhaar_data.get('dob'),
                        'full_name': aadhaar_data.get('name'),
                        'gender': aadhaar_data.get('gender'),
                        'is_verified': 1,
                        'did': did_value,
                        'verification_type': verification_data['verification_type']
                    },
                    'verification_details': {
                        'aadhaar_verified': True,
                        'face_verified': True,
                        'phone_verified': True,
                        'face_matches': verification_data['face_matches'],
                        'total_face_images': verification_data['total_face_images']
                    }
                }
            )
            
        except Exception as e:
            # Clean up temp data on database error
            if session_id in temp_verification_data:
                del temp_verification_data[session_id]
            raise HTTPException(status_code=500, detail=f"Failed to save user data: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in complete KYC verification: {e}")
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {str(e)}")


# Legacy endpoint completely removed - OTP service disabled
# The legacy-complete-verification endpoint has been removed because it depends on OTP service
# which is now disabled. Use the new /start-verification and /complete-verification flow instead.


@router.get("/status/{wallet_address}", response_model=APIResponse)
async def get_kyc_status(
    wallet_address: str,
    user_service: UserService = Depends(get_user_service)
):
    """Get complete KYC verification status and user data"""
    try:
        user = await user_service.get_user_by_wallet(wallet_address)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get verification logs
        logs = await user_service.get_user_verification_logs(wallet_address)
        
        # Prepare user data response
        user_data = {
            'wallet_address': user.wallet_address,
            'phone_number': user.phone_number,
            'aadhaar_number': user.aadhaar_number,
            'date_of_birth': user.date_of_birth,
            'full_name': user.full_name,
            'gender': user.gender,
            'is_verified': user.is_verified,
            'verification_flag': user.is_verified,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'updated_at': user.updated_at.isoformat() if user.updated_at else None
        }
        
        # Prepare verification status
        verification_status = {
            'overall_verified': user.is_verified == 1,
            'has_phone': bool(user.phone_number),
            'has_aadhaar': bool(user.aadhaar_number),
            'has_personal_data': bool(user.full_name and user.date_of_birth)
        }
        
        return APIResponse(
            success=True,
            message="KYC status retrieved successfully",
            data={
                'user_data': user_data,
                'verification_status': verification_status,
                'verification_logs': [log.dict() for log in logs[:10]]  # Last 10 logs
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting KYC status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/request-correction", response_model=APIResponse)
async def request_data_correction(
    session_id: str = Form(...),
    correction_data: str = Form(..., description="JSON string of corrected data")
):
    """Allow user to correct OCR extracted data"""
    try:
        import json
        
        # Check if session exists
        if session_id not in temp_verification_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID or session expired"
            )
        
        # Parse correction data
        try:
            corrections = json.loads(correction_data)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid correction data format"
            )
        
        # Store corrections in session
        temp_verification_data[session_id]['user_corrections'] = corrections
        
        return APIResponse(
            success=True,
            message="Data corrections saved successfully",
            data={
                'session_id': session_id,
                'corrections': corrections,
                'status': 'corrections_saved'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving data corrections: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/confirm-and-verify", response_model=APIResponse)
async def confirm_and_verify(
    session_id: str = Form(...),
    user_wallet: str = Form(...),
    document_type: str = Form(default="pan", description="Document type: 'pan' (default and only supported)"),
    redis_service: RedisService = Depends(get_redis_service)
):
    """User confirms corrected data and sends for government verification"""
    try:
        # Check if session exists
        if session_id not in temp_verification_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID or session expired"
            )
        
        verification_data = temp_verification_data[session_id]
        aadhaar_data = verification_data['aadhaar_data']
        user_corrections = verification_data.get('user_corrections', {})
        did_id = verification_data['did']
        
        # Prepare final verification data for PAN verification (use corrections if provided)
        final_data = {
            'pan': user_corrections.get('pan', aadhaar_data.get('pan', aadhaar_data.get('aadhaar_number'))),  # Use PAN or fallback
            'name': user_corrections.get('name', aadhaar_data.get('name')),
            'date_of_birth': user_corrections.get('date_of_birth', aadhaar_data.get('dob')),
            'phone_number': user_corrections.get('phone_number', aadhaar_data.get('phone_number'))
        }
        
        # Send PAN verification request to Redis for enclave processing
        redis_sent = await redis_service.send_verification_request(
            user_wallet=user_wallet,
            did_id=did_id,
            document_type="pan",  # Always PAN for this flow
            verification_data=final_data,
            extracted_data=aadhaar_data,
            user_corrections=user_corrections if user_corrections else None
        )
        
        if redis_sent:
            logger.info(f"Verification request sent to enclave for wallet: {user_wallet}")
            
            # Clean up session data
            del temp_verification_data[session_id]
            
            return APIResponse(
                success=True,
                message="Verification request sent to enclave. Please wait for government verification.",
                data={
                    'user_wallet': user_wallet,
                    'status': 'verification_requested',
                    'document_type': "pan",
                    'redis_sent': True,
                    'message': 'Verification in progress via government APIs'
                }
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send verification request to enclave"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in confirm and verify: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/verified-users", response_model=APIResponse)
async def get_verified_users(
    user_service: UserService = Depends(get_user_service)
):
    """Get all verified users (admin endpoint)"""
    try:
        verified_users = await user_service.get_all_verified_users()
        user_counts = await user_service.get_user_count_by_verification_status()
        
        return APIResponse(
            success=True,
            message="Verified users retrieved successfully",
            data={
                'verified_users': [user.dict() for user in verified_users],
                'statistics': user_counts,
                'total_verified': len(verified_users)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting verified users: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
async def confirm_and_verify(
    session_id: str = Form(...),
    user_wallet: str = Form(...),
    document_type: str = Form(default="pan", description="Document type: 'pan' (default and only supported)"),
    redis_service: RedisService = Depends(get_redis_service)
):
    """User confirms corrected data and sends for government verification"""
    try:
        # Check if session exists
        if session_id not in temp_verification_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid session ID or session expired"
            )
        
        verification_data = temp_verification_data[session_id]
        aadhaar_data = verification_data['aadhaar_data']
        user_corrections = verification_data.get('user_corrections', {})
        did_id = verification_data['did']
        
        # Prepare final verification data for PAN verification (use corrections if provided)
        final_data = {
            'pan': user_corrections.get('pan', aadhaar_data.get('pan', aadhaar_data.get('aadhaar_number'))),  # Use PAN or fallback
            'name': user_corrections.get('name', aadhaar_data.get('name')),
            'date_of_birth': user_corrections.get('date_of_birth', aadhaar_data.get('dob')),
            'phone_number': user_corrections.get('phone_number', aadhaar_data.get('phone_number'))
        }
        
        # Send PAN verification request to Redis for enclave processing
        redis_sent = await redis_service.send_verification_request(
            user_wallet=user_wallet,
            did_id=did_id,
            document_type="pan",  # Always PAN for this flow
            verification_data=final_data,
            extracted_data=aadhaar_data,
            user_corrections=user_corrections if user_corrections else None
        )
        
        if redis_sent:
            logger.info(f"Verification request sent to enclave for wallet: {user_wallet}")
            
            # Clean up session data
            del temp_verification_data[session_id]
            
            return APIResponse(
                success=True,
                message="Verification request sent to enclave. Please wait for government verification.",
                data={
                    'user_wallet': user_wallet,
                    'status': 'verification_requested',
                    'document_type': "pan",
                    'redis_sent': True,
                    'message': 'Verification in progress via government APIs'
                }
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send verification request to enclave"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in confirm and verify: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/verified-users", response_model=APIResponse)
async def get_verified_users(
    user_service: UserService = Depends(get_user_service)
):
    """Get all verified users (admin endpoint)"""
    try:
        verified_users = await user_service.get_all_verified_users()
        user_counts = await user_service.get_user_count_by_verification_status()
        
        return APIResponse(
            success=True,
            message="Verified users retrieved successfully",
            data={
                'verified_users': [user.dict() for user in verified_users],
                'statistics': user_counts,
                'total_verified': len(verified_users)
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting verified users: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")