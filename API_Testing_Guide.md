# SuiVerify Backend API Testing Guide

## Overview
This guide provides comprehensive curl commands to test the entire SuiVerify backend flow with PAN verification and Redis integration (OTP disabled).

## Prerequisites
1. **Start Redis Server**: `redis-server`
2. **Start Python Backend**: `python main.py`
3. **Backend URL**: `http://localhost:8000`

---

## Testing Flow Overview

```
1. Health Check → 2. OCR Extraction → 3. Face Verification → 4. KYC Start → 5. Data Correction → 6. Confirm & Verify → 7. Redis Stream Check
```

---

## 1. Health Check & System Status

### Basic Health Check
```bash
curl -X GET "http://localhost:8000/" \
  -H "accept: application/json"
```

**Expected Response:**
```json
{
  "message": "SuiVerify API - Identity Verification System",
  "version": "1.0.0",
  "status": "active",
  "services": {
    "mongodb": "connected",
    "user_management": "ready",
    "ocr": "ready",
    "face_recognition": "ready",
    "encryption_metadata": "ready",
    "redis": "connected"
  }
}
```

### Detailed Health Check
```bash
curl -X GET "http://localhost:8000/health" \
  -H "accept: application/json"
```

**Expected Response:**
```json
{
  "status": "healthy",
  "services": {
    "ocr": "healthy",
    "face": "healthy",
    "redis": "connected"
  }
}
```

---

## 2. OCR Extraction (Aadhaar Processing)

### Extract Aadhaar Data
```bash
curl -X POST "http://localhost:8000/api/aadhaar/extract" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "image=@/path/to/aadhaar_sample.jpg"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Aadhaar data extracted successfully",
  "data": {
    "name": "John Doe",
    "aadhaar_number": "1234 5678 9012",
    "dob": "01/01/1990",
    "gender": "Male",
    "phone_number": "9876543210",
    "address": "Sample Address"
  }
}
```

### Extract Photo from Aadhaar
```bash
curl -X POST "http://localhost:8000/api/aadhaar/extract-photo" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "image=@/path/to/aadhaar_sample.jpg"
```

---

## 3. Face Verification

### Compare Face with Aadhaar Photo
```bash
curl -X POST "http://localhost:8000/api/face/compare" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "aadhaar_photo=@/path/to/aadhaar_photo.jpg" \
  -F "face_photo=@/path/to/user_face.jpg"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Face comparison completed",
  "data": {
    "match": true,
    "confidence": 85.5,
    "verified": true,
    "threshold": 80.0
  }
}
```

---

## 4. KYC Verification Flow (OTP Disabled)

### Start KYC Verification
```bash
curl -X POST "http://localhost:8000/api/kyc/start-verification" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "verification_type=above18" \
  -F "aadhaar_image=@/path/to/aadhaar_sample.jpg" \
  -F "face_images=@/path/to/face1.jpg" \
  -F "face_images=@/path/to/face2.jpg" \
  -F "face_images=@/path/to/face3.jpg"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Aadhaar and face verification successful. OTP step skipped.",
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "phone_number": "9876543210",
    "aadhaar_verified": true,
    "face_verified": true,
    "otp_sent": true,
    "expires_in_minutes": 5,
    "extracted_data": {
      "name": "John Doe",
      "aadhaar_number": "123456789012",
      "date_of_birth": "01/01/1990",
      "gender": "Male"
    }
  }
}
```

### Complete KYC Verification (No OTP Required)
```bash
curl -X POST "http://localhost:8000/api/kyc/complete-verification" \
  -H "accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "session_id=550e8400-e29b-41d4-a716-446655440000"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "KYC verification completed successfully! User data saved to database.",
  "data": {
    "wallet_address": "0x1234567890abcdef...",
    "verification_status": "VERIFIED",
    "is_verified": 0,
    "user_data": {
      "wallet_address": "0x1234567890abcdef...",
      "phone_number": "9876543210",
      "aadhaar_number": "123456789012",
      "date_of_birth": "01/01/1990",
      "full_name": "John Doe",
      "gender": "Male",
      "is_verified": 0,
      "did": 0,
      "verification_type": "above18"
    }
  }
}
```

---

## 5. Data Correction Flow

### Request Data Correction
```bash
curl -X POST "http://localhost:8000/api/kyc/request-correction" \
  -H "accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "session_id=550e8400-e29b-41d4-a716-446655440000" \
  -d 'correction_data={"name": "Corrected Name", "date_of_birth": "02/01/1990", "pan": "ABCDE1234F"}'
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Data corrections saved successfully",
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "corrections": {
      "name": "Corrected Name",
      "date_of_birth": "02/01/1990",
      "pan": "ABCDE1234F"
    },
    "status": "corrections_saved"
  }
}
```

### Confirm and Verify (Send to Redis)
```bash
curl -X POST "http://localhost:8000/api/kyc/confirm-and-verify" \
  -H "accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "session_id=550e8400-e29b-41d4-a716-446655440000" \
  -d "user_wallet=0x1234567890abcdef" \
  -d "document_type=pan"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Verification request sent to enclave. Please wait for government verification.",
  "data": {
    "user_wallet": "0x1234567890abcdef",
    "status": "verification_requested",
    "document_type": "pan",
    "redis_sent": true,
    "message": "Verification in progress via government APIs"
  }
}
```

---

## 6. User Management

### Get User by Wallet Address
```bash
curl -X GET "http://localhost:8000/api/users/wallet/0x1234567890abcdef" \
  -H "accept: application/json"
```

### Get KYC Status
```bash
curl -X GET "http://localhost:8000/api/kyc/status/0x1234567890abcdef" \
  -H "accept: application/json"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "KYC status retrieved successfully",
  "data": {
    "user_data": {
      "wallet_address": "0x1234567890abcdef",
      "phone_number": "9876543210",
      "aadhaar_number": "123456789012",
      "date_of_birth": "01/01/1990",
      "full_name": "John Doe",
      "gender": "Male",
      "is_verified": 0,
      "verification_flag": 0,
      "created_at": "2025-10-19T13:20:00",
      "updated_at": "2025-10-19T13:25:00"
    },
    "verification_status": {
      "overall_verified": false,
      "has_phone": true,
      "has_aadhaar": true,
      "has_personal_data": true
    }
  }
}
```

### Get All Verified Users
```bash
curl -X GET "http://localhost:8000/api/kyc/verified-users" \
  -H "accept: application/json"
```

---

## 7. Redis Stream Testing

### Test Redis Integration (Python Script)
```bash
cd /home/ash-win/projects/suiverify-infra/verification-backend
python test_redis_integration.py
```

**Expected Output:**
```
🧪 Testing Redis Integration...
📡 Testing Redis connection...
Redis Health: {
  "service": "redis",
  "status": "healthy",
  "host": "localhost",
  "port": 6379,
  "stream": "verification_stream",
  "connected": true,
  "error": null
}

🔄 Testing PAN verification request...
✅ Verification request sent successfully!

📊 Stream Information:
{
  "stream_exists": true,
  "stream_name": "verification_stream",
  "length": 1,
  "first_entry_id": "1729343400000-0",
  "last_entry_id": "1729343400000-0"
}

⚠️  Testing legacy method (should show deprecation warning)...
✅ Legacy method works (with deprecation warning)

🎉 Redis integration test completed!
```

---

## 8. Redis Stream Inspection (Manual)

### Check Redis Stream Content
```bash
# Connect to Redis CLI
redis-cli

# List all streams
SCAN 0 MATCH *stream*

# Get stream info
XINFO STREAM verification_stream

# Read stream messages
XREAD STREAMS verification_stream 0

# Get latest message
XREVRANGE verification_stream + - COUNT 1
```

**Expected Redis Message Format:**
```json
{
  "user_wallet": "0x1234567890abcdef",
  "did_id": "0",
  "verification_type": "pan",
  "document_data": {
    "pan": "ABCDE1234F",
    "name_as_per_pan": "Corrected Name",
    "date_of_birth": "02/01/1990",
    "consent": "Y",
    "reason": "For onboarding customers"
  },
  "timestamp": "2025-10-19T13:25:40.123456",
  "status": "pending_verification"
}
```

---

## 9. Error Testing

### Test Invalid Session ID
```bash
curl -X POST "http://localhost:8000/api/kyc/complete-verification" \
  -H "accept: application/json" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "session_id=invalid-session-id"
```

**Expected Response:**
```json
{
  "detail": "Invalid session ID or session expired. Please start verification again."
}
```

### Test Missing Required Fields
```bash
curl -X POST "http://localhost:8000/api/kyc/start-verification" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "verification_type=invalid_type"
```

**Expected Response:**
```json
{
  "detail": "verification_type must be 'above18' or 'citizenship'"
}
```

---

## 10. Complete End-to-End Test Script

### Automated Test Script
```bash
#!/bin/bash

echo "🚀 Starting SuiVerify Backend E2E Testing..."

# 1. Health Check
echo "📋 Step 1: Health Check"
curl -s -X GET "http://localhost:8000/" | jq .

# 2. Start KYC (with sample images)
echo "📋 Step 2: Start KYC Verification"
RESPONSE=$(curl -s -X POST "http://localhost:8000/api/kyc/start-verification" \
  -H "Content-Type: multipart/form-data" \
  -F "verification_type=above18" \
  -F "aadhaar_image=@sample_aadhaar.jpg" \
  -F "face_images=@sample_face1.jpg" \
  -F "face_images=@sample_face2.jpg" \
  -F "face_images=@sample_face3.jpg")

SESSION_ID=$(echo $RESPONSE | jq -r '.data.session_id')
echo "Session ID: $SESSION_ID"

# 3. Complete KYC
echo "📋 Step 3: Complete KYC Verification"
curl -s -X POST "http://localhost:8000/api/kyc/complete-verification" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "session_id=$SESSION_ID" | jq .

# 4. Test Redis Integration
echo "📋 Step 4: Test Redis Integration"
python test_redis_integration.py

echo "✅ E2E Testing Complete!"
```

---

## 11. Troubleshooting

### Common Issues and Solutions

#### Redis Connection Failed
```bash
# Check Redis status
redis-cli ping

# Start Redis if not running
redis-server

# Check Redis logs
tail -f /var/log/redis/redis-server.log
```

#### MongoDB Connection Issues
```bash
# Check MongoDB status
sudo systemctl status mongod

# Start MongoDB if not running
sudo systemctl start mongod
```

#### Backend Server Issues
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process if needed
kill -9 $(lsof -t -i:8000)

# Start backend with debug logs
python main.py --log-level debug
```

---

## 12. Expected Redis Stream Flow

### Message Flow to Rust Enclave
1. **Python Backend** → Redis Stream (verification request)
2. **Rust Enclave** → Consume from Redis Stream
3. **Rust Enclave** → Call Government APIs (PAN verification)
4. **Rust Enclave** → Generate evidence hash
5. **Rust Enclave** → Sign verification result
6. **Rust Enclave** → Send result back (future implementation)

### Current Status
- ✅ **Python Backend**: Sends PAN verification requests to Redis
- ✅ **Redis Stream**: Stores verification requests
- ⏳ **Rust Enclave**: Next phase - consume and process requests
- ⏳ **Government APIs**: Next phase - actual PAN verification
- ⏳ **Evidence Hash**: Next phase - generated in Rust enclave

---

## Summary

This testing guide covers the complete SuiVerify backend flow with:
- ✅ **Health checks and system status**
- ✅ **OCR extraction and face verification**
- ✅ **KYC verification (OTP disabled)**
- ✅ **Data correction workflow**
- ✅ **Redis stream integration**
- ✅ **User management endpoints**
- ✅ **Error handling and troubleshooting**

The backend is now ready for Rust enclave integration to complete the government API verification process.
