#!/usr/bin/env python
"""
PAN Card OCR Test Script

This script tests the PAN OCR extraction service locally.
In production, images will be uploaded from the frontend to the /extract-pan-data endpoint.

Usage:
    python extract_pan.py <path_to_pan_image>
    
Example:
    python extract_pan.py test_pan_card.jpg
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("="*80)
print("PAN CARD OCR TEST SCRIPT")
print("="*80)
print("\nThis script tests the OCR extraction locally.")
print("In production, images are uploaded from the frontend.\n")

# Get image path from command line argument
if len(sys.argv) < 2:
    print("❌ Error: No image path provided")
    print("\nUsage:")
    print(f"  python {Path(__file__).name} <path_to_pan_image>")
    print("\nExample:")
    print(f"  python {Path(__file__).name} test_pan_card.jpg")
    sys.exit(1)

image_path = Path(sys.argv[1])

if not image_path.exists():
    print(f"❌ Error: Image file not found at: {image_path}")
    print("\nPlease provide a valid path to a PAN card image.")
    sys.exit(1)

# Import the PAN OCR service
from app.services.pan_ocr_service import get_pan_ocr_service

# Read image file
print(f"📸 Reading image from: {image_path}")
try:
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    print(f"✅ Image loaded successfully ({len(image_bytes):,} bytes)")
except Exception as e:
    print(f"❌ Error reading image: {e}")
    sys.exit(1)

# Initialize OCR service
print("\n" + "="*80)
print("🔍 RUNNING PAN OCR EXTRACTION")
print("="*80)

try:
    service = get_pan_ocr_service()
    
    # Run extraction with ensemble mode for best accuracy
    result = service.extract_pan_data(image_bytes, use_ensemble=True)
    
    # Display extraction results
    print("\n📋 EXTRACTED DATA:")
    print("-" * 80)
    print(f"PAN Number     : {result.get('pan_number') or '❌ NOT FOUND'}")
    print(f"Name           : {result.get('name') or '❌ NOT FOUND'}")
    print(f"Father's Name  : {result.get('father_name') or '❌ NOT FOUND'}")
    print(f"Date of Birth  : {result.get('dob') or '❌ NOT FOUND'}")
    print(f"Photo Extracted: {'✅ YES' if result.get('pan_photo_base64') else '❌ NO'}")
    print(f"Overall Success: {'✅ SUCCESS' if result.get('success') else '❌ FAILED'}")
    print("-" * 80)
    
    # Calculate extraction quality
    extracted_count = sum([
        1 if result.get('pan_number') else 0,
        1 if result.get('name') else 0,
        1 if result.get('father_name') else 0,
        1 if result.get('dob') else 0
    ])
    quality = (extracted_count / 4) * 100
    
    print(f"\n📊 Extraction Quality: {extracted_count}/4 fields ({quality:.0f}%)")
    
    # Show raw OCR text preview
    if result.get('raw_text'):
        print("\n📄 RAW OCR TEXT (first 800 chars):")
        print("-" * 80)
        raw = result.get('raw_text', '')
        print(raw[:800])
        if len(raw) > 800:
            print(f"\n... (total {len(raw):,} characters)")
        print("-" * 80)
    
    print("\n✅ Test completed successfully!")
    
except Exception as e:
    print(f"\n❌ Error during OCR extraction: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
