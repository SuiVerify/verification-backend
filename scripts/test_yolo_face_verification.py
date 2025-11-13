"""
Test script for YOLO-based PAN face verification
Tests the new /api/face/verify-pan-face-yolo endpoint
"""
import requests
import base64
import os
import sys

# Configuration
API_BASE_URL = "http://127.0.0.1:8000"
VERIFY_ENDPOINT = f"{API_BASE_URL}/api/face/verify-pan-face-yolo"

def test_pan_face_verification(pan_card_path: str, live_image_path: str):
    """
    Test PAN card face verification with live image
    
    Args:
        pan_card_path: Path to PAN card image
        live_image_path: Path to live/selfie image
    """
    print(f"\n{'='*60}")
    print(f"🧪 Testing YOLO-based PAN Face Verification")
    print(f"{'='*60}\n")
    
    # Validate files exist
    if not os.path.exists(pan_card_path):
        print(f"❌ PAN card image not found: {pan_card_path}")
        return False
    
    if not os.path.exists(live_image_path):
        print(f"❌ Live image not found: {live_image_path}")
        return False
    
    print(f"📁 PAN Card Image: {pan_card_path}")
    print(f"📁 Live Image: {live_image_path}\n")
    
    try:
        # Read image files
        with open(pan_card_path, 'rb') as f:
            pan_card_data = f.read()
        
        with open(live_image_path, 'rb') as f:
            live_image_data = f.read()
        
        print(f"📤 Sending request to: {VERIFY_ENDPOINT}")
        print(f"   PAN card size: {len(pan_card_data)} bytes")
        print(f"   Live image size: {len(live_image_data)} bytes\n")
        
        # Prepare multipart form data
        files = {
            'pan_card_image': ('pan_card.jpg', pan_card_data, 'image/jpeg'),
            'live_image': ('live_image.jpg', live_image_data, 'image/jpeg')
        }
        
        # Send POST request
        response = requests.post(VERIFY_ENDPOINT, files=files, timeout=30)
        
        print(f"📥 Response Status: {response.status_code}\n")
        
        if response.status_code == 200:
            result = response.json()
            
            data = result.get('data', {})
            
            # Get verification status from API
            verification_status = data.get('verification_status', 'UNKNOWN')
            verified = data.get('verified', False)
            confidence = data.get('confidence', 0)
            face_distance = data.get('face_distance', 0)
            threshold = data.get('threshold', 60)
            detection_method = data.get('detection_method', 'N/A')
            
            # Display main verification result prominently
            if verification_status == 'SUCCESS' and verified:
                print("✅ VERIFICATION SUCCESS!")
            else:
                print("❌ VERIFICATION FAILED!")
            
            print(f"\n{'─'*60}")
            print(f"📊 Results:")
            print(f"{'─'*60}")
            
            print(f"🎯 Status: {verification_status}")
            print(f"📈 Confidence: {confidence}% (Threshold: {threshold}%)")
            print(f"📏 Face Distance: {face_distance}")
            print(f"🔧 Detection Method: {detection_method}")
            print(f"\n💬 Message: {result.get('message', 'N/A')}")
            
            # Show validation details
            validation = data.get('validation', {})
            if validation:
                print(f"\n🔍 Validation Details:")
                pan_val = validation.get('pan_photo', {})
                live_val = validation.get('live_image', {})
                
                print(f"   PAN Photo: {pan_val.get('reason', 'N/A')} "
                      f"(Method: {pan_val.get('detection_method', 'N/A')})")
                print(f"   Live Image: {live_val.get('reason', 'N/A')} "
                      f"(Method: {live_val.get('detection_method', 'N/A')})")
            
            print(f"{'─'*60}\n")
            
            # Recommend action based on confidence
            if match and confidence >= 80:
                print("✅ HIGH CONFIDENCE MATCH - Verification passed")
            elif match and confidence >= 60:
                print("⚠️  MODERATE CONFIDENCE MATCH - Manual review recommended")
            elif match and confidence < 60:
                print("⚠️  LOW CONFIDENCE MATCH - Additional verification required")
            else:
                print("❌ NO MATCH - Verification failed")
            
            return True
            
        else:
            print(f"❌ Verification Failed!")
            print(f"Status Code: {response.status_code}")
            
            try:
                error_data = response.json()
                print(f"Error: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"Error: {response.text}")
            
            return False
    
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Could not connect to API server")
        print(f"   Make sure the server is running at {API_BASE_URL}")
        return False
    
    except requests.exceptions.Timeout:
        print("❌ Timeout Error: Request took too long")
        return False
    
    except Exception as e:
        print(f"❌ Unexpected Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("\n" + "="*60)
    print("🚀 YOLO PAN Face Verification Test Suite")
    print("="*60)
    
    # Default test images (update these paths)
    default_pan = "scripts/0818f3524b09a68115c5ec95eb43f868.jpg"
    
    # Check if custom paths provided via command line
    if len(sys.argv) >= 3:
        pan_path = sys.argv[1]
        live_path = sys.argv[2]
    else:
        pan_path = default_pan
        # For testing, you can use the same PAN image or provide a different live image
        live_path = default_pan  # Replace with actual live/selfie image path
        
        print(f"\nℹ️  Using default test images")
        print(f"   Usage: python {sys.argv[0]} <pan_card_path> <live_image_path>")
    
    # Run test
    success = test_pan_face_verification(pan_path, live_path)
    
    print("\n" + "="*60)
    if success:
        print("✅ Test completed successfully!")
    else:
        print("❌ Test failed!")
    print("="*60 + "\n")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
