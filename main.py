# Aadhaar OCR + Face Match + OTP Verification System - Backend
# Python FastAPI Backend with OCR, Face Recognition, and OTP Verification

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

from app.routers import aadhar, face, otp, user, kyc, encryption, credentials
from app.services.ocr_service import OCRService
from app.services.face_recognition_service import get_face_recognition_service
from app.services.otp_service import OTPService
from app.services.user_service import get_user_service
from app.services.encryption_service import encryption_service
from app.services.redis_service import get_redis_service
from app.database import connect_to_mongo, close_mongo_connection

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global services
ocr_service = None
face_recognition_service = None
otp_service = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global ocr_service, face_recognition_service, otp_service
    
    logger.info("Starting SuiVerify System with MongoDB integration...")
    
    # Connect to MongoDB
    try:
        await connect_to_mongo()
        logger.info("MongoDB connected successfully")
        
        # Create encryption metadata indexes
        await encryption_service.create_indexes()
        logger.info("Encryption metadata indexes created")
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise
    # Initialize services
    ocr_service = OCRService()
    face_recognition_service = get_face_recognition_service()
    otp_service = OTPService()
    
    # Test Redis connection
    redis_service = get_redis_service()
    try:
        redis_health = await redis_service.health_check()
        if redis_health['connected']:
            logger.info(f"✅ Redis connected successfully to {redis_health['host']}:{redis_health['port']}")
        else:
            logger.warning(f"⚠️ Redis connection failed: {redis_health.get('error', 'Unknown error')}")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection test failed: {e}")
    
    logger.info("All services initialized successfully")
    yield
    
    # Cleanup
    logger.info("Shutting down SuiVerify System...")
    await close_mongo_connection()
    
    # Close Redis service
    try:
        await redis_service.close()
    except Exception as e:
        logger.warning(f"Error closing Redis service: {e}")

# Create FastAPI app
app = FastAPI(
    title="Aadhaar OCR + Face Match + OTP Verification System",
    description="Secure offline Aadhaar verification with OCR, face recognition, and OTP",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173" ,"http://localhost:5175"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(user.router, prefix="/api", tags=["User Management"])
app.include_router(kyc.router, prefix="/api", tags=["KYC Verification"])
app.include_router(aadhar.router, prefix="/api/aadhaar", tags=["Aadhaar OCR"])
app.include_router(face.router, prefix="/api/face", tags=["Face Recognition"])
app.include_router(otp.router, prefix="/api/otp", tags=["OTP Verification"])
app.include_router(encryption.router, prefix="/api", tags=["Encryption Metadata"])
app.include_router(credentials.router, prefix="/api", tags=["Credentials Management"])

@app.get("/")
async def root():
    """Health check endpoint"""
    # Get Redis status
    redis_service = get_redis_service()
    redis_status = "connected" if redis_service.is_connected else "disconnected"
    
    return {
        "message": "SuiVerify API - Identity Verification System",
        "version": "1.0.0",
        "status": "active",
        "services": {
            "mongodb": "connected",
            "user_management": "ready",
            "ocr": "ready",
            "face_recognition": "ready", 
            "otp": "ready",
            "encryption_metadata": "ready",
            "redis": redis_status
        }
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    global ocr_service, face_service, otp_service
    
    health_status = {
        "status": "healthy",
        "services": {}
    }
    
    # Check OCR service
    try:
        if ocr_service and await ocr_service.health_check():
            health_status["services"]["ocr"] = "healthy"
        else:
            health_status["services"]["ocr"] = "unhealthy"
    except Exception as e:
        health_status["services"]["ocr"] = f"error: {str(e)}"
    
    # Check Face service
    try:
        if yolo_face_service and await yolo_face_service.health_check():
            health_status["services"]["face"] = "healthy"
        else:
            health_status["services"]["face"] = "unhealthy"
    except Exception as e:
        health_status["services"]["face"] = f"error: {str(e)}"
    
    # Check OTP service
    try:
        if otp_service and await otp_service.health_check():
            health_status["services"]["otp"] = "healthy"
        else:
            health_status["services"]["otp"] = "unhealthy"
    except Exception as e:
        health_status["services"]["otp"] = f"error: {str(e)}"
    
    # Overall status
    if any("unhealthy" in status or "error" in status for status in health_status["services"].values()):
        health_status["status"] = "degraded"
    
    return health_status

# Dependency to get services
def get_ocr_service():
    global ocr_service
    if not ocr_service:
        raise HTTPException(status_code=503, detail="OCR service not available")
    return ocr_service

def get_yolo_face_service():
    global yolo_face_service
    if not yolo_face_service:
        raise HTTPException(status_code=503, detail="YOLO Face service not available")
    return yolo_face_service

def get_otp_service():
    global otp_service
    if not otp_service:
        raise HTTPException(status_code=503, detail="OTP service not available")
    return otp_service

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )