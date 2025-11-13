# Scripts Folder

This folder contains utility scripts for testing and development purposes.

## 📁 Contents

### `extract_pan.py`
**Purpose:** Test PAN OCR extraction locally with sample images.

**Usage:**
```bash
python scripts/extract_pan.py <path_to_pan_image>
```

**Example:**
```bash
python scripts/extract_pan.py test_images/sample_pan.jpg
```

**Output:**
- Extracted PAN number
- Cardholder name
- Father's name
- Date of birth
- Photo extraction status
- Raw OCR text preview

---

### `check_tesseract.py`
**Purpose:** Verify Tesseract OCR installation and configuration.

**Usage:**
```bash
python scripts/check_tesseract.py
```

---

## 🔄 Development vs Production Flow

### Local Testing (Development)
```
Image File (scripts/) → extract_pan.py → PAN OCR Service → Console Output
```

Use the test scripts in this folder to:
- Test OCR accuracy with sample images
- Debug extraction logic
- Validate Tesseract configuration

### Production Flow (Real Usage)
```
Frontend Upload → /extract-pan-data API → PAN OCR Service → JSON Response
```

In production:
- Images are uploaded from the frontend via POST request
- The `/extract-pan-data` endpoint in `app/routers/pan.py` handles the request
- OCR service extracts data and returns structured JSON
- Frontend displays results for user verification

---

## 🚀 Production API Endpoints

### POST `/extract-pan-data`
Extract PAN card data from uploaded image.

**Request:**
```
Content-Type: multipart/form-data
Body: file (image file)
```

**Response:**
```json
{
  "success": true,
  "message": "✅ All PAN card fields extracted successfully! (Success rate: 100%)",
  "data": {
    "pan_number": "ABCDE1234F",
    "name": "JOHN DOE",
    "father_name": "RICHARD DOE",
    "dob": "15/08/1990",
    "pan_photo_base64": "data:image/jpeg;base64,...",
    "raw_text": "..."
  }
}
```

---

## 📝 Notes

- **No hardcoded test images:** Test images should be provided by developers locally
- **Scripts are for testing only:** Production flow uses API endpoints
- **Ensemble OCR enabled:** The service uses multiple OCR configurations for best accuracy
- **Generic extraction:** No card-specific logic; works with any PAN card format

---

## 🔧 Adding New Test Images

To test with your own PAN card images:

1. Save your test image anywhere on your system
2. Run the extraction script with the path:
   ```bash
   python scripts/extract_pan.py /path/to/your/pan_card.jpg
   ```
3. Review the extraction results in the console

---

## ⚠️ Important

- Never commit real PAN card images to the repository
- Test images should be synthetic or properly anonymized
- Production images are handled securely through the API and never stored on disk
