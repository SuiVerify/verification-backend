#!/usr/bin/env python3
"""
Test script for the updated Redis integration
Tests the new verification request flow
"""

import asyncio
import json
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.redis_service import get_redis_service

async def test_redis_integration():
    """Test the new Redis verification request flow"""
    
    print("🧪 Testing Redis Integration...")
    
    # Show Redis configuration being used
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', '6379')
    redis_stream = os.getenv('REDIS_STREAM_NAME', 'verification_stream')
    
    print(f"📡 Using Redis Configuration:")
    print(f"   Host: {redis_host}")
    print(f"   Port: {redis_port}")
    print(f"   Stream: {redis_stream}")
    
    # Get Redis service
    redis_service = get_redis_service()
    
    # Test connection
    print("📡 Testing Redis connection...")
    health = await redis_service.health_check()
    print(f"Redis Health: {json.dumps(health, indent=2)}")
    
    if not health.get('connected'):
        print("❌ Redis not connected. Please start Redis server.")
        return False
    
    # Test new PAN verification request method
    print("\n🔄 Testing PAN verification request...")
    
    # Use real data from the working curl example
    test_data = {
        'pan': 'HJTPB9891M',
        'name': 'Ashwin Balaguru',
        'date_of_birth': '27/10/2004',
        'phone_number': '9876543210'
    }
    
    # Test with slight corrections to verify correction flow
    user_corrections = {
        'pan': 'HJTPB9891M',  # Include PAN in corrections
        'name': 'Ashwin Balaguru',  # Keep same name
        'date_of_birth': '27/10/2004'  # Keep same DOB
    }
    
    success = await redis_service.send_verification_request(
        user_wallet="0x812bacb619f60a09d4fd01841f37f141be40ecc2d2892023df8c3dd9bcb73ec4",
        did_id=0,
        document_type="pan",
        verification_data=test_data,
        extracted_data=test_data,
        user_corrections=user_corrections
    )
    if success:
        print("✅ Verification request sent successfully!")
        
        # Get stream info
        print("\n📊 Stream Information:")
        try:
            stream_info = await redis_service.get_stream_info()
            # Convert bytes to strings for JSON serialization
            if isinstance(stream_info, dict):
                for key, value in stream_info.items():
                    if isinstance(value, bytes):
                        stream_info[key] = value.decode('utf-8')
            print(json.dumps(stream_info, indent=2, default=str))
        except Exception as e:
            print(f"Could not get stream info: {e}")
            print("✅ But verification request was sent successfully!")
        
    else:
        print("❌ Failed to send verification request")
        return False
    # Skip legacy method for now to avoid confusion
    print("\n⚠️  Skipping legacy method to focus on new data...")
    
    print("\n🎉 Redis integration test completed!")
    return True

if __name__ == "__main__":
    asyncio.run(test_redis_integration())