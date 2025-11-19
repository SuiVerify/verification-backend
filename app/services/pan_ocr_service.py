import cv2
import numpy as np
import pytesseract
import re
import base64
from typing import Optional, Dict, Tuple, List
from PIL import Image, ImageEnhance, ImageFilter
import io
import os
import logging

# Set up logger
logger = logging.getLogger(__name__)

class PANOCRService:
    def __init__(self):
        # Set Tesseract path for Linux (auto-detect or use system path)
        import platform
        if platform.system() == "Windows":
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            os.environ['TESSDATA_PREFIX'] = r'C:\Program Files\Tesseract-OCR\tessdata'
        else:
            # Linux/Unix - use system installation
            pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
        
        logger.info("PAN OCR Service initialized with Tesseract")
    
    def preprocess_image_methods(self, image_bytes: bytes) -> List[Image.Image]:
        """Create multiple preprocessed versions of the image for better OCR"""
        try:
            # Original PIL Image
            pil_image = Image.open(io.BytesIO(image_bytes))
            processed_images = [pil_image]
            
            # Convert to RGB if necessary
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # Method 1: Enhanced contrast
            enhancer = ImageEnhance.Contrast(pil_image)
            contrast_img = enhancer.enhance(2.0)
            processed_images.append(contrast_img)
            
            # Method 2: Grayscale with sharpening
            gray_img = pil_image.convert('L')
            sharpened = gray_img.filter(ImageFilter.SHARPEN)
            processed_images.append(sharpened)
            
            # Method 3: Binary threshold
            opencv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(opencv_image, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            binary_pil = Image.fromarray(binary)
            processed_images.append(binary_pil)
            
            # Method 4: Adaptive threshold with denoising
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            adaptive = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                           cv2.THRESH_BINARY, 11, 2)
            adaptive_pil = Image.fromarray(adaptive)
            processed_images.append(adaptive_pil)
            
            # Method 5: Enhanced brightness and contrast
            bright_enhancer = ImageEnhance.Brightness(pil_image)
            bright_img = bright_enhancer.enhance(1.5)
            contrast_enhancer = ImageEnhance.Contrast(bright_img)
            bright_contrast = contrast_enhancer.enhance(1.5)
            processed_images.append(bright_contrast)
            
            return processed_images
            
        except Exception as e:
            logger.error(f"Error in image preprocessing: {e}")
            return [Image.open(io.BytesIO(image_bytes))]
    
    # ==================== OCR Helper Utilities (from ocr tools) ====================
    
    def _auto_enhance_brightness(self, img: Image.Image) -> Image.Image:
        """Automatically enhance brightness and exposure if image is too dark.
        
        Returns enhanced image if brightness is below threshold, otherwise returns original.
        """
        try:
            from PIL import ImageStat, ImageEnhance
            
            gray = img.convert('L')
            stat = ImageStat.Stat(gray)
            mean_brightness = stat.mean[0]  # 0-255
            
            if mean_brightness < 150:
                brightness_factor = min(4.0, 200 / (mean_brightness + 1))  # cap at 4x
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(brightness_factor)
                
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.8)
        
        except Exception as e:
            logger.debug(f"Brightness enhancement failed: {e}")
        
        return img
    
    def _setup_tesseract(self) -> None:
        """Ensure pytesseract has tesseract binary and TESSDATA_PREFIX configured."""
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            # Try to find tesseract binary
            possible = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                os.path.join(os.path.expanduser('~'), 'scoop', 'shims', 'tesseract.exe'),
                os.path.join(os.path.expanduser('~'), 'scoop', 'apps', 'tesseract', 'current', 'tesseract.exe'),
            ]
            for p in possible:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    logger.info(f"Tesseract binary found at: {p}")
                    break
        
        # Ensure TESSDATA_PREFIX is set
        if 'TESSDATA_PREFIX' not in os.environ:
            tessdata_candidates = [
                os.path.join(os.path.expanduser('~'), 'scoop', 'persist', 'tesseract', 'tessdata'),
                os.path.join(os.path.expanduser('~'), 'scoop', 'apps', 'tesseract', 'current', 'tessdata'),
                r'C:\Program Files\Tesseract-OCR\tessdata',
            ]
            for td in tessdata_candidates:
                if os.path.isdir(td):
                    os.environ['TESSDATA_PREFIX'] = td
                    logger.info(f"TESSDATA_PREFIX set to: {td}")
                    break
    
    def _pytesseract_text_and_conf(self, image: Image.Image) -> Tuple[str, float]:
        """Run pytesseract and return (text, avg_confidence)."""
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            words = data.get('text', [])
            confs = data.get('conf', [])
            texts = [w for w in words if w and w.strip()]
            valid_confs = []
            for c in confs:
                try:
                    if c is None or c == '' or c == '-1':
                        continue
                    valid_confs.append(int(float(c)))
                except Exception:
                    continue
            avg_conf = float(sum(valid_confs)) / len(valid_confs) if valid_confs else 0.0
            text = " ".join(texts).strip()
            if not text:
                text = pytesseract.image_to_string(image)
            return text, avg_conf
        except Exception as e:
            logger.debug(f"pytesseract_text_and_conf failed: {e}")
            try:
                text = pytesseract.image_to_string(image)
                return text, 0.0
            except Exception:
                return "", 0.0
    
    def ensemble_tesseract_bytes(self, image_bytes: bytes, runs: int = 3) -> str:
        """Run pytesseract multiple times and return the most common text (or highest-confidence if all differ)."""
        try:
            from collections import Counter
            
            pil_img = Image.open(io.BytesIO(image_bytes))
            pil_img = self._auto_enhance_brightness(pil_img)
            
            results: List[Tuple[str, float]] = []
            for run_idx in range(runs):
                try:
                    text, conf = self._pytesseract_text_and_conf(pil_img)
                except Exception:
                    text, conf = "", 0.0
                results.append((text, conf))
                logger.debug(f"Ensemble run {run_idx + 1}: confidence={conf:.2f}, text_len={len(text)}")
            
            texts = [t for t, _ in results if t]
            if not texts:
                return ""
            
            text_counts = Counter(texts)
            most_common_text, count = text_counts.most_common(1)[0]
            
            # If all results differ (count == 1), pick highest confidence
            if count == 1 and len(text_counts) == len(texts):
                best = max(results, key=lambda x: x[1])
                logger.info(f"Ensemble: all results differ, picking highest confidence ({best[1]:.2f})")
                return best[0]
            
            logger.info(f"Ensemble: returning most common text (count={count})")
            return most_common_text
        
        except Exception as e:
            logger.error(f"Ensemble tesseract failed: {e}")
            return ""
    
    def extract_text_with_tesseract(self, image_bytes: bytes, use_ensemble: bool = False) -> str:
        """Extract text using Tesseract OCR with multiple preprocessing methods.
        
        Args:
            image_bytes: Image data as bytes
            use_ensemble: If True, runs ensemble multiple passes for more robust extraction
        
        Returns:
            Combined OCR text from all attempts
        """
        if use_ensemble:
            logger.info("Using ensemble mode for text extraction")
            ensemble_text = self.ensemble_tesseract_bytes(image_bytes, runs=3)
            if ensemble_text:
                return ensemble_text
        
        try:
            self._setup_tesseract()
            all_texts = []
            processed_images = self.preprocess_image_methods(image_bytes)
            
            # Different Tesseract configurations
            configs = [
                '--psm 6',  # Uniform block of text
                '--psm 3',  # Fully automatic page segmentation
                '--psm 11', # Sparse text
            ]
            
            for idx, img in enumerate(processed_images):
                # Auto-enhance brightness on this variant
                try:
                    enhanced_img = self._auto_enhance_brightness(img)
                except Exception:
                    enhanced_img = img
                
                for config in configs:
                    try:
                        # Try with English
                        text = pytesseract.image_to_string(enhanced_img, lang='eng', config=config)
                        if text and text.strip():
                            all_texts.append(text)
                        
                        # Also try with specific character whitelist for PAN
                        try:
                            custom_config = config + ' -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/- '
                            text = pytesseract.image_to_string(enhanced_img, lang='eng', config=custom_config)
                            if text and text.strip():
                                all_texts.append(text)
                        except Exception:
                            pass
                    except Exception as e:
                        logger.debug(f"Config {config} failed for image {idx}: {e}")
            
            # If no text found, try ensemble as fallback
            if not all_texts:
                logger.info("No text found in preprocessing variants, trying ensemble fallback")
                ensemble_text = self.ensemble_tesseract_bytes(image_bytes, runs=3)
                if ensemble_text:
                    all_texts.append(ensemble_text)
            
            # Combine all extracted text
            combined_text = '\n'.join(all_texts)
            logger.info(f"Total OCR extracted text length: {len(combined_text)}")
            
            return combined_text
            
        except Exception as e:
            logger.error(f"Error in Tesseract OCR: {e}")
            return ""
    
    def extract_pan_number(self, text: str) -> Optional[str]:
        """Extract PAN number from text"""
        text = text.upper()
        valid_pans = []
        
        # Strategy 1: Look for PAN near "Permanent Account Number" or "PAN" label
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if re.search(r'Permanent\s*Account\s*Number|^\s*PAN\b|Account\s*Number\s*Card', line, re.IGNORECASE):
                # Check same line and next 1-2 lines for the actual PAN
                for j in range(0, min(3, len(lines) - i)):
                    check_line = lines[i + j]
                    line_clean = re.sub(r'\s+', '', check_line)
                    
                    if len(line_clean) >= 10:
                        for k in range(len(line_clean) - 9):
                            potential = line_clean[k:k+10]
                            
                            # Check if it matches PAN pattern
                            if (potential[0].isalpha() and potential[1].isalpha() and 
                                potential[2].isalpha() and potential[3].isalpha() and 
                                potential[4].isalpha() and
                                (potential[5].isdigit() or potential[5] in 'OILSZG') and
                                (potential[6].isdigit() or potential[6] in 'OILSZG') and
                                (potential[7].isdigit() or potential[7] in 'OILSZG') and 
                                (potential[8].isdigit() or potential[8] in 'OILSZG') and 
                                potential[9].isalpha()):
                                
                                corrected = self._fix_pan_ocr_errors(potential)
                                if self._is_valid_pan_format(corrected):
                                    valid_pans.append(corrected)
        
        if valid_pans:
            return valid_pans[0]
        
        # Strategy 2: Standard regex patterns
        pan_patterns = [
            r'\b([A-Z]{5}[0-9]{4}[A-Z])\b',
            r'\b([A-Z]{5}\s*[0-9]{4}\s*[A-Z])\b',
        ]
        
        for pattern in pan_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                pan = re.sub(r'\s+', '', match)
                pan = self._fix_pan_ocr_errors(pan)
                if self._is_valid_pan_format(pan) and pan not in valid_pans:
                    valid_pans.append(pan)
        
        if valid_pans:
            return valid_pans[0]
        
        # Strategy 3: Search entire text but skip obvious false positives
        text_no_space = re.sub(r'\s+', '', text)
        exclude_keywords = ['INCOMETAXDEPARTMENT', 'GOVERNMENTOF', 'ACCOUNTNUMBER', 'PERMANENTACCOUNT', 'CARDSIGNATURE']
        
        for i in range(len(text_no_space) - 9):
            potential = text_no_space[i:i+10]
            
            # Skip if potential is part of known false positive keywords
            context_start = max(0, i - 20)
            context = text_no_space[context_start:i+15]
            if any(keyword in context for keyword in exclude_keywords):
                continue
            
            alpha_count = sum(1 for c in potential if c.isalpha())
            digit_count = sum(1 for c in potential if c.isdigit())
            ocr_digit_like = sum(1 for c in potential if c in 'OILSZG')
            
            if alpha_count >= 5 and (digit_count + ocr_digit_like) >= 4:
                corrected = self._fix_pan_ocr_errors(potential)
                if self._is_valid_pan_format(corrected) and corrected not in valid_pans:
                    valid_pans.append(corrected)
        
        if valid_pans:
            return valid_pans[0]
        
        return None
    
    def _fix_pan_ocr_errors(self, pan: str) -> str:
        """Fix common OCR errors in PAN number - generic approach"""
        if len(pan) < 10:
            return pan
            
        result = list(pan.upper())
        
        # PAN format: LLLLLDDDDL (5 letters, 4 digits, 1 letter)
        # Positions 0-4: LETTERS, Positions 5-8: DIGITS, Position 9: LETTER
        
        # Fix positions 5-8 (should be digits - most likely to be misread as letters)
        digit_corrections = {
            'O': '0', 'I': '1', 'L': '1', 'S': '5', 'Z': '2',
            'B': '8', 'G': '6', 'J': '5', 'R': '4', 'T': '7'
        }
        for i in [5, 6, 7, 8]:
            if i < len(result) and result[i] in digit_corrections:
                result[i] = digit_corrections[result[i]]
        
        # Fix positions 0-4 and 9 (should be letters - convert misread digits)
        letter_corrections = {
            '0': 'O', '1': 'I', '5': 'S', '8': 'B', '3': 'E',
            '2': 'Z', '6': 'G', '9': 'G', '4': 'A', '7': 'T'
        }
        
        for i in [0, 1, 2, 3, 4, 9]:
            if i < len(result) and result[i] in '0123456789':
                result[i] = letter_corrections.get(result[i], result[i])
        
        # Don't do any special B->3 conversion - let validation handle it
        # Different PANs might use different valid first letters
        
        return ''.join(result)
    
    def _is_valid_pan_format(self, pan: str) -> bool:
        """Validate PAN number format"""
        if len(pan) != 10:
            return False
        pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
        return bool(re.match(pattern, pan))
    
    def extract_name(self, text: str) -> Optional[str]:
        """Extract name from PAN card text - improved to get correct name before Father's Name"""
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        
        candidates = []
        
        # Strategy 1: Find FIRST occurrence of Father's Name, then look 1-2 lines backward
        # PAN card structure: Name is always right before Father's Name label
        father_line_index = -1
        for i, line in enumerate(cleaned_lines):
            if re.search(r"(Father'?s?\s*Name|/FN|F/FN)", line, re.IGNORECASE):
                father_line_index = i
                break
        
        # If we found Father's Name label, check 1-2 lines before for the actual name
        if father_line_index > 0:
            # Check immediate previous line first
            line = cleaned_lines[father_line_index - 1]
            line_clean = re.sub(r'[^A-Z\s]', '', line.upper()).strip()
            
            # Extract only valid name words (usually 2-3 words before garbage)
            words = line_clean.split()
            if len(words) >= 2:
                # Take first 2-3 words that look like names
                name_words = []
                for word in words[:4]:  # Look at first 4 words max
                    if len(word) >= 3 and not re.search(r'(TAX|DEPT|INCOME|GOVT|CARD|NUMBER)', word):
                        name_words.append(word)
                    elif len(name_words) >= 2:
                        break  # Stop after we have 2 valid name words
                
                if len(name_words) >= 2:
                    name_candidate = ' '.join(name_words)
                    cleaned_name = self._clean_name(name_candidate)
                    if self._is_valid_name(cleaned_name):
                        candidates.append((cleaned_name, 'before_father', 0))
        
        # Strategy 2: Look for "Name" label and collect candidates
        if not candidates:
            for i, line in enumerate(cleaned_lines):
                if re.search(r'\bName\b', line, re.IGNORECASE) and not re.search(r"Father|Mother|F/|/FN", line, re.IGNORECASE):
                    # Collect candidates from next few lines
                    for j in range(1, min(4, len(cleaned_lines) - i)):
                        next_line = cleaned_lines[i + j]
                        next_line_clean = re.sub(r'[^A-Z\s]', '', next_line.upper()).strip()
                        
                        # Stop if we hit Father's Name or another label
                        if re.search(r"(Father|Mother|F/|/FN|Date|Birth|Signature|Address)", next_line, re.IGNORECASE):
                            break
                        
                        if next_line_clean and len(next_line_clean) >= 5:
                            cleaned_name = self._clean_name(next_line_clean)
                            if self._is_valid_name(cleaned_name):
                                candidates.append((cleaned_name, 'label', j))
        
        # Strategy 3: Find first valid multi-word name in document
        if not candidates:
            all_text = ' '.join(cleaned_lines)
            name_pattern = r'\b([A-Z]{3,}\s+[A-Z]{3,}(?:\s+[A-Z]{3,})?)\b'
            matches = re.findall(name_pattern, all_text)
            
            if matches:
                for match in matches:
                    cleaned_name = self._clean_name(match)
                    if self._is_valid_name(cleaned_name):
                        candidates.append((cleaned_name, 'pattern', 0))
                        break
        
        # Return best candidate
        if candidates:
            candidates.sort(key=lambda x: (x[1] != 'before_father', x[1] != 'label', x[2]))
            return candidates[0][0]
        
        return None
    
    def _is_valid_name(self, text: str, allow_single_word: bool = False) -> bool:
        """Check if text is a valid name - generic validation"""
        exclude_patterns = [
            'INCOME', 'TAX', 'DEPARTMENT', 'GOVT', 'INDIA', 'PERMANENT', 
            'ACCOUNT', 'NUMBER', 'CARD', 'SIGNATURE', 'DATE', 'BIRTH', 'FATHER',
            'ADDRESS', 'PAN', 'GOVERNMENT', 'MINISTRY', 'OFFICIAL'
        ]
        
        text_upper = text.upper().strip()
        
        # Basic length check
        if len(text_upper) < 5:
            return False
        
        # Don't match structural/label words or noise patterns
        for pattern in exclude_patterns:
            if pattern in text_upper:
                return False
        
        words = text_upper.split()
        
        # Names should have at least 2 words (FirstName LastName)
        # Unless allow_single_word is True (for father's names like "BALAGURU")
        if len(words) < 2 and not allow_single_word:
            return False
        elif len(words) < 1:
            return False
        
        # Each word should be reasonable length (3-15 chars)
        for word in words:
            if len(word) < 3 or len(word) > 15:
                return False
            
            # Each word should be mostly letters
            if not all(c.isalpha() or c in ' -' for c in word):
                return False
        
        # Check for pronounceable patterns (real names don't have impossible letter sequences)
        vowels = 'AEIOU'
        for word in words:
            vowel_count = 0
            consonant_count = 0
            
            for char in word:
                if char in vowels:
                    vowel_count += 1
                    consonant_count = 0
                    if vowel_count > 3:  # Too many vowels in a row (unrealistic)
                        return False
                elif char not in ' -':
                    consonant_count += 1
                    vowel_count = 0
                    if consonant_count > 4:  # Too many consonants in a row (unrealistic)
                        return False
        
        return True
    
    def _correct_name_ocr_errors(self, name: str) -> str:
        """Correct common OCR errors in name text (generic, not hardcoded)"""
        name = name.upper()
        
        # Replace ONLY obvious digit-letter confusions that are unambiguous
        corrections = {
            '0': 'O',  # zero to letter O
            '1': 'I',  # 1 to I  
            '5': 'S',  # 5 to S
            '8': 'B',  # 8 to B
            '3': 'E',  # 3 to E
        }
        
        for wrong, right in corrections.items():
            name = name.replace(wrong, right)
        
        # Generic common OCR patterns (not card-specific)
        generic_corrections = {
            'RN': 'M',  # RN often misread as M
            'CL': 'D',  # CL often misread as D
            'VV': 'W',  # VV often misread as W
            'II': 'U',  # II often misread as U
            'O0': 'OO', # O0 -> OO (zero and letter O)
        }
        
        # Only apply if confident (pattern appears exactly)
        for pattern, replacement in generic_corrections.items():
            if pattern in name:
                # Check context - only replace if surrounded by letters
                # This is more conservative to avoid false positives
                pass  # Don't apply these heuristics - too risky
        
        return name.strip()

    def _clean_name(self, name: str) -> str:
        """Clean and correct extracted name (whitespace normalization + basic OCR error fixes)"""
        name = re.sub(r'\s+', ' ', name.strip()).upper()
        
        # Fix obvious digit-letter confusions ONLY
        corrections = {'0': 'O', '1': 'I', '5': 'S', '8': 'B', '3': 'E'}
        for wrong, right in corrections.items():
            name = name.replace(wrong, right)
        
        # Apply generic OCR error corrections
        name = self._correct_name_ocr_errors(name)
        
        # Remove common OCR noise patterns (repeated letters at end)
        # E.g., "BALAGURU EEE" -> "BALAGURU", "SINGH AAA" -> "SINGH"
        words = name.split()
        cleaned_words = []
        for word in words:
            # Skip words that are just repeated single letters (EEE, AAA, etc.)
            if len(set(word)) == 1 and len(word) >= 2:
                continue  # Skip this noise word
            cleaned_words.append(word)
        
        name = ' '.join(cleaned_words)
        
        return name
    
    def extract_father_name(self, text: str) -> Optional[str]:
        """Extract father's name - improved to avoid picking up the person's full name"""
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        
        candidates = []
        person_name = self.extract_name(text)  # Get the person's name to avoid confusion
        
        # Strategy 1: Look for "Father" label and collect candidates from same/nearby lines
        for i, line in enumerate(cleaned_lines):
            if re.search(r"Father'?s?\s*Name|FN\b|पिता\s*का\s*नाम", line, re.IGNORECASE):
                # Try to extract from same line first (after the label)
                # e.g., "Father's Name: JOHN DOE" or "पिता का नाम / Father's Name BALAGURU"
                match = re.search(r"(?:Father'?s?\s*Name|FN|पिता\s*का\s*नाम)[:\s/]+([A-Z][A-Z\s]+?)(?:\s+\d|\s*$)", line, re.IGNORECASE)
                if match:
                    name_part = match.group(1).strip()
                    name_clean = re.sub(r'[^A-Z\s]', '', name_part).strip()
                    if name_clean and len(name_clean) >= 3:  # Reduced minimum length for single names
                        cleaned_name = self._clean_name(name_clean)
                        # Avoid picking up the person's full name
                        if (self._is_valid_name(cleaned_name, allow_single_word=True) and 
                            cleaned_name != person_name):
                            candidates.append((cleaned_name, 'same_line', 0))
                
                # Collect candidates from next few lines
                for j in range(1, min(3, len(cleaned_lines) - i)):  # Reduced range to be more precise
                    next_line = cleaned_lines[i + j]
                    next_line_clean = re.sub(r'[^A-Z\s]', '', next_line.upper()).strip()
                    
                    # Stop if we hit another label
                    if re.search(r'(Date|Birth|Signature|Address|जन्म)', next_line, re.IGNORECASE):
                        break
                    
                    if next_line_clean and len(next_line_clean) >= 3:  # Reduced minimum length
                        cleaned_name = self._clean_name(next_line_clean)
                        # Allow single-word names for father's name (common in India)
                        # Avoid picking up the person's full name
                        if (self._is_valid_name(cleaned_name, allow_single_word=True) and 
                            cleaned_name != person_name):
                            
                            # Special handling: if person's name is "ASHWIN BALAGURU" and we find "BALAGURU",
                            # prefer the single word (likely the father's name)
                            if person_name and len(cleaned_name.split()) == 1:
                                person_words = person_name.split()
                                if len(person_words) > 1 and cleaned_name in person_words:
                                    # This single word is part of the person's name, likely the father's name
                                    candidates.append((cleaned_name, 'single_word_match', j))
                            else:
                                candidates.append((cleaned_name, 'label', j))
        
        # Strategy 2: If we have the person's name, try to extract father's name as the last word
        # This is common in Indian names where father's name becomes the last name
        if not candidates and person_name:
            person_words = person_name.split()
            if len(person_words) >= 2:
                # The last word is often the father's name in Indian naming convention
                potential_father_name = person_words[-1]
                if (len(potential_father_name) >= 3 and 
                    self._is_valid_name(potential_father_name, allow_single_word=True)):
                    candidates.append((potential_father_name, 'last_word_extraction', 0))
        
        # Strategy 3: Find single-word uppercase sequences as fallback (but avoid person's name)
        if not candidates:
            all_text = ' '.join(cleaned_lines)
            # Look for single words that could be father's names
            single_word_pattern = r'\b([A-Z]{4,})\b'  # Single words with 4+ letters
            matches = re.findall(single_word_pattern, all_text)
            
            for match in matches:
                cleaned_name = self._clean_name(match)
                if (self._is_valid_name(cleaned_name, allow_single_word=True) and 
                    cleaned_name != person_name and 
                    cleaned_name not in [c[0] for c in candidates]):
                    # Avoid common PAN card words
                    if not re.search(r'(INCOME|GOVERNMENT|DEPARTMENT|PERMANENT|ACCOUNT|NUMBER|CARD|INDIA)', cleaned_name):
                        candidates.append((cleaned_name, 'single_word_pattern', 0))
        
        # Return best candidate (single_word_match > same_line > last_word_extraction > label > single_word_pattern)
        if candidates:
            candidates.sort(key=lambda x: (
                x[1] != 'single_word_match',
                x[1] != 'same_line', 
                x[1] != 'last_word_extraction',
                x[1] != 'label',
                x[2]
            ))
            return candidates[0][0]
        
        return None
    
    def extract_dob(self, text: str) -> Optional[str]:
        """Extract date of birth"""
        # Pattern to match dates: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
        # Must match day (1-2 digits), month (1-2 digits), year (4 digits)
        date_patterns = [
            r'(\d{1,2})[/\.\-](\d{1,2})[/\.\-](\d{4})',  # DD/MM/YYYY or DD.MM.YYYY or DD-MM-YYYY
            r'(\d{4})[/\.\-](\d{1,2})[/\.\-](\d{1,2})',  # YYYY/MM/DD or YYYY.MM.DD (reverse)
        ]
        
        valid_dates = []
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    # Determine if it's DD/MM/YYYY or YYYY/MM/DD
                    if len(str(match[0])) == 4:  # YYYY format
                        year, month, day = int(match[0]), int(match[1]), int(match[2])
                    else:  # DD/MM/YYYY format
                        day, month, year = int(match[0]), int(match[1]), int(match[2])
                    
                    # Validate date range (reasonable birth dates 1920-2010)
                    if 1 <= day <= 31 and 1 <= month <= 12 and 1920 <= year <= 2010:
                        valid_dates.append(f"{day:02d}/{month:02d}/{year}")
                except Exception:
                    continue
        
        if valid_dates:
            return valid_dates[0]
        
        # If no direct match found, return None
        return None
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string"""
        date_str = date_str.replace('-', '/').replace('O', '0').replace('I', '1')
        
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            
            if 1 <= day <= 31 and 1 <= month <= 12 and 1920 <= year <= 2010:
                return f"{day:02d}/{month:02d}/{year}"
        
        return None
    
    def extract_photo_from_pan(self, image_bytes: bytes) -> Optional[str]:
        """Extract user photo from PAN card and return as base64"""
        try:
            pil_image = Image.open(io.BytesIO(image_bytes))
            opencv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            
            height, width = opencv_image.shape[:2]
            
            # Photo region (left side of PAN)
            photo_x_start = int(width * 0.02)
            photo_x_end = int(width * 0.25)
            photo_y_start = int(height * 0.25)
            photo_y_end = int(height * 0.75)
            
            photo_region = opencv_image[photo_y_start:photo_y_end, photo_x_start:photo_x_end]
            
            if photo_region.size == 0:
                return None
            
            # Convert and resize
            photo_rgb = cv2.cvtColor(photo_region, cv2.COLOR_BGR2RGB)
            photo_pil = Image.fromarray(photo_rgb)
            photo_pil = photo_pil.resize((150, 200), Image.LANCZOS)
            
            # Convert to base64
            buffer = io.BytesIO()
            photo_pil.save(buffer, format='JPEG', quality=85)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error extracting photo: {str(e)}")
            return None
    
    def get_pan_photo(self, image_bytes: bytes) -> Dict:
        """
        Extract only the photo from PAN card for face verification use
        Returns dict with photo_base64 and success status
        """
        try:
            photo_base64 = self.extract_photo_from_pan(image_bytes)
            
            if photo_base64:
                return {
                    'success': True,
                    'pan_photo_base64': photo_base64,
                    'message': 'PAN card photo extracted successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to extract photo from PAN card',
                    'message': 'Could not locate or extract photo region'
                }
                
        except Exception as e:
            logger.error(f"Error in get_pan_photo: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Error extracting PAN photo: {str(e)}'
            }
    
    def extract_pan_data(self, image_bytes: bytes, use_ensemble: bool = False) -> Dict:
        """Extract all relevant data from PAN card image.
        
        Args:
            image_bytes: Image data as bytes
            use_ensemble: If True, uses ensemble OCR for more robust extraction
        
        Returns:
            Dictionary with pan_number, name, father_name, dob, pan_photo_base64, raw_text, success
        """
        try:
            # Extract text (with optional ensemble)
            extracted_text = self.extract_text_with_tesseract(image_bytes, use_ensemble=use_ensemble)
            logger.debug(f"Extracted text:\n{extracted_text}")
            
            # Extract fields
            pan_number = self.extract_pan_number(extracted_text)
            name = self.extract_name(extracted_text)
            father_name = self.extract_father_name(extracted_text)
            dob = self.extract_dob(extracted_text)
            
            # Extract photo
            pan_photo_base64 = self.extract_photo_from_pan(image_bytes)
            
            result = {
                'pan_number': pan_number,
                'name': name,
                'father_name': father_name,
                'dob': dob,
                'pan_photo_base64': pan_photo_base64,
                'raw_text': extracted_text,
                'success': True
            }
            
            logger.info(f"PAN extraction result: PAN={pan_number}, Name={name}, Father={father_name}, DOB={dob}")
            return result
            
        except Exception as e:
            logger.error(f"Error in PAN data extraction: {str(e)}")
            return {
                'error': f"Error processing PAN card data: {str(e)}",
                'success': False
            }

# Global instance
pan_ocr_service = None

def get_pan_ocr_service() -> PANOCRService:
    """Get or create PAN OCR service instance"""
    global pan_ocr_service
    if pan_ocr_service is None:
        pan_ocr_service = PANOCRService()
    return pan_ocr_service