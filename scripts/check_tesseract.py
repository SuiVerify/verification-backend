import pytesseract
import shutil

print('pytesseract.tesseract_cmd=', pytesseract.pytesseract.tesseract_cmd)
print('shutil.which(tesseract)=', shutil.which('tesseract'))

try:
    v = pytesseract.get_tesseract_version()
    print('tesseract version=', v)
except Exception as e:
    print('tesseract version check failed:', e)
