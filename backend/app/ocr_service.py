"""
Passport OCR Service using Google Cloud Vision API.
Handles multiple passports per image with MRZ parsing.
"""

import io
import re
import base64
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from PIL import Image
import numpy as np
import cv2
import requests

from .config import GOOGLE_CLOUD_VISION_API_KEY

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@dataclass
class PassportData:
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    gender: str = ""
    date_of_birth: str = ""
    nationality: str = ""
    passport_number: str = ""
    confidence: float = 0.0
    low_confidence_fields: List[str] = field(default_factory=list)


# Google Cloud Vision API endpoint
VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"


def call_google_vision_api(image_base64: str) -> Optional[dict]:
    """
    Call Google Cloud Vision API for text detection.
    Returns the API response or None if failed.
    """
    if not GOOGLE_CLOUD_VISION_API_KEY:
        print("Google Cloud Vision API key not configured")
        return None

    payload = {
        "requests": [
            {
                "image": {
                    "content": image_base64
                },
                "features": [
                    {
                        "type": "DOCUMENT_TEXT_DETECTION",
                        "maxResults": 1
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post(
            f"{VISION_API_URL}?key={GOOGLE_CLOUD_VISION_API_KEY}",
            json=payload,
            timeout=30
        )

        # Log the full response for debugging
        logger.info(f"Google Vision API status code: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Google Vision API error response: {response.text}")

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Google Vision API error: {e}")
        return None


def extract_text_from_vision_response(response: dict) -> str:
    """Extract full text from Vision API response."""
    try:
        responses = response.get("responses", [])
        if responses and "fullTextAnnotation" in responses[0]:
            text = responses[0]["fullTextAnnotation"]["text"]
            logger.info("=" * 60)
            logger.info("GOOGLE VISION RAW TEXT:")
            logger.info("=" * 60)
            logger.info(text)
            logger.info("=" * 60)
            return text
        elif responses and "textAnnotations" in responses[0]:
            # Fallback to textAnnotations
            annotations = responses[0]["textAnnotations"]
            if annotations:
                text = annotations[0].get("description", "")
                logger.info("=" * 60)
                logger.info("GOOGLE VISION RAW TEXT (from textAnnotations):")
                logger.info("=" * 60)
                logger.info(text)
                logger.info("=" * 60)
                return text
    except (KeyError, IndexError) as e:
        logger.error(f"Error extracting text: {e}")
    return ""


def validate_mrz_line1(line: str) -> bool:
    """Validate that a string looks like a valid MRZ Line 1."""
    if not line or len(line) < 30:
        return False
    if not line.startswith('P<'):
        return False
    if '<<' not in line:
        return False
    # Should have a 3-letter country code at positions 2-5
    country = line[2:5]
    if not re.match(r'^[A-Z]{3}$', country):
        return False
    # Names section should be mostly letters and < (not digits)
    names = line[5:]
    digit_count = sum(1 for c in names if c.isdigit())
    if digit_count > 2:  # Allow small number of OCR errors
        return False
    return True


def validate_mrz_line2(line: str) -> bool:
    """Validate that a string looks like a valid MRZ Line 2."""
    if not line or len(line) < 30:
        return False
    # Must match the pattern: passport# + check + nationality + DOB + check + sex
    if not re.match(r'^[A-Z0-9<]{9}[0-9<][A-Z]{3}[0-9]{6}[0-9<][MF<]', line):
        return False
    return True


def score_mrz_line2(line: str) -> int:
    """Score a Line 2 candidate - higher is better."""
    score = 0
    # Prefer lines that are closer to 44 characters
    if len(line) >= 40 and len(line) <= 48:
        score += 10
    # Prefer lines with valid passport number (not all <)
    passport_num = line[0:9]
    actual_chars = passport_num.replace('<', '')
    if len(actual_chars) >= 7:
        score += 20
    # Prefer lines with valid nationality (3 real letters, not <)
    nationality = line[10:13] if len(line) > 13 else ""
    if re.match(r'^[A-Z]{3}$', nationality) and '<' not in nationality:
        score += 15
    # Prefer lines with valid sex indicator
    sex = line[20] if len(line) > 20 else ""
    if sex in ('M', 'F'):
        score += 10
    # Prefer lines with valid DOB (all digits)
    dob = line[13:19] if len(line) > 19 else ""
    if re.match(r'^[0-9]{6}$', dob):
        score += 15
    return score


def find_mrz_lines(text: str) -> List[List[str]]:
    """
    Find MRZ lines from OCR text.
    MRZ lines are 44 characters (TD3 passport) containing letters, numbers, and <.
    Returns list of MRZ line pairs (for multiple passports).
    """
    logger.info("=" * 60)
    logger.info("SEARCHING FOR MRZ LINES...")
    logger.info("=" * 60)

    mrz_pairs = []
    lines = text.split('\n')

    # STRATEGY 1: Find lines that look like MRZ (line-by-line)
    # This is more reliable than stripping all non-MRZ chars from entire text
    logger.info("STRATEGY 1: Line-by-line MRZ detection...")

    line1_candidates = []  # Lines starting with P<
    line2_candidates = []  # Lines with passport number pattern

    for i, line in enumerate(lines):
        # Keep only MRZ characters from this line
        cleaned = re.sub(r'[^A-Z0-9<]', '', line.upper())

        if len(cleaned) < 15:
            continue

        # Check if this is MRZ Line 1 (starts with P<XXX)
        if cleaned.startswith('P<') and len(cleaned) >= 20:
            # Must have << (name separator) and pass validation
            if '<<' in cleaned and validate_mrz_line1(cleaned):
                logger.info(f"  Line {i}: MRZ Line 1 candidate: {cleaned[:50]}...")
                line1_candidates.append((i, cleaned))

        # Check if this is MRZ Line 2 (passport number pattern)
        # Pattern: 9 chars (alphanumeric or <) + check + 3 letters (nationality) + 6 digits (DOB)
        # Passport number can contain < as filler
        if re.match(r'^[A-Z0-9<]{9}[0-9<][A-Z]{3}[0-9]{6}', cleaned) and len(cleaned) >= 30:
            if validate_mrz_line2(cleaned):
                score = score_mrz_line2(cleaned)
                logger.info(f"  Line {i}: MRZ Line 2 candidate (score={score}): {cleaned[:50]}...")
                line2_candidates.append((i, cleaned, score))

    # Try to pair Line 1 with Line 2 - pick the best scored Line 2
    for line1_idx, line1 in line1_candidates:
        # Find the best scored Line 2 that comes after this Line 1
        best_line2 = None
        best_score = -1
        best_idx = -1

        for line2_idx, line2, score in line2_candidates:
            if line2_idx > line1_idx:
                # Prefer closer Line 2, but also consider score
                distance_penalty = (line2_idx - line1_idx) * 2
                adjusted_score = score - distance_penalty
                if adjusted_score > best_score or (adjusted_score == best_score and line2_idx < best_idx):
                    best_score = adjusted_score
                    best_line2 = line2
                    best_idx = line2_idx

        if best_line2:
            # Normalize to 44 chars
            l1 = line1[:44].ljust(44, '<')
            l2 = best_line2[:44].ljust(44, '<')

            logger.info(f"Found MRZ pair (lines {line1_idx}, {best_idx}, score={best_score}):")
            logger.info(f"  Line 1: {l1}")
            logger.info(f"  Line 2: {l2}")
            mrz_pairs.append([l1, l2])

    if mrz_pairs:
        logger.info(f"STRATEGY 1 found {len(mrz_pairs)} MRZ pair(s)")
        return mrz_pairs

    # STRATEGY 2: Reconstruct split MRZ lines
    # Sometimes MRZ Line 1 is split: "P<ISRRON<<OSNAT<<<<<<<<<" + "<<<<<<<<<<<<<<<<<<<"
    logger.info("STRATEGY 2: Reconstructing split MRZ lines...")

    # Find partial Line 1 (starts with P< but less than 44 chars)
    for i, line in enumerate(lines):
        cleaned = re.sub(r'[^A-Z0-9<]', '', line.upper())
        if cleaned.startswith('P<') and '<<' in cleaned and 15 <= len(cleaned) < 44:
            logger.info(f"  Found partial Line 1 at {i}: {cleaned}")

            # Try to find continuation (line of mostly < chars) and Line 2
            line1_parts = [cleaned]
            line2 = None

            for j in range(i + 1, min(i + 10, len(lines))):
                next_cleaned = re.sub(r'[^A-Z0-9<]', '', lines[j].upper())
                if not next_cleaned:
                    continue

                # Check if this is a Line 2 (allow < in passport number)
                if re.match(r'^[A-Z0-9<]{9}[0-9<][A-Z]{3}[0-9]{6}', next_cleaned):
                    line2 = next_cleaned[:44].ljust(44, '<')
                    break

                # Check if this is continuation of Line 1 (mostly < chars)
                if len(next_cleaned) >= 5 and next_cleaned.count('<') / len(next_cleaned) > 0.7:
                    line1_parts.append(next_cleaned)

            if line2:
                # Combine Line 1 parts
                combined_line1 = ''.join(line1_parts)[:44].ljust(44, '<')
                logger.info(f"Reconstructed MRZ pair:")
                logger.info(f"  Line 1: {combined_line1}")
                logger.info(f"  Line 2: {line2}")
                mrz_pairs.append([combined_line1, line2])

    if mrz_pairs:
        logger.info(f"STRATEGY 2 found {len(mrz_pairs)} MRZ pair(s)")
        return mrz_pairs

    # STRATEGY 3: Find Line 2 first, then look backwards for Line 1
    logger.info("STRATEGY 3: Find Line 2 first, search backwards for Line 1...")

    # Sort by score descending to try best Line 2 candidates first
    sorted_line2 = sorted(line2_candidates, key=lambda x: x[2], reverse=True)

    for line2_idx, line2, score in sorted_line2:
        # Search backwards for P< pattern
        for i in range(line2_idx - 1, max(0, line2_idx - 15), -1):
            cleaned = re.sub(r'[^A-Z0-9<]', '', lines[i].upper())
            if cleaned.startswith('P<') and '<<' in cleaned and validate_mrz_line1(cleaned):
                l1 = cleaned[:44].ljust(44, '<')
                l2 = line2[:44].ljust(44, '<')
                logger.info(f"Found MRZ pair (backwards search, score={score}):")
                logger.info(f"  Line 1: {l1}")
                logger.info(f"  Line 2: {l2}")
                mrz_pairs.append([l1, l2])
                break

    logger.info(f"Final result: {len(mrz_pairs)} MRZ pair(s)")
    return mrz_pairs


def parse_mrz_names(names_section: str) -> Tuple[str, str, str, List[str]]:
    """
    Parse names from MRZ.
    Format: LASTNAME<<FIRSTNAME<MIDDLENAME<<<...

    Example: VALKUSZ<<MILAN<TAMAS<<<<<<<<<<<<<<<<<<
    - VALKUSZ = last name
    - MILAN = first name
    - TAMAS = middle name

    Example: ROTARI<DOANI<<OLGA<<<<<<<<<<<<<<<<<<
    - ROTARI<DOANI = last name (single < = space, so ROTARI DOANI)
    - OLGA = first name
    """
    logger.info(f"Parsing names from: '{names_section}'")
    low_confidence = []

    if not names_section:
        logger.warning("Empty names section")
        return "", "", "", ["first_name", "last_name"]

    # Remove trailing < characters
    names_section = names_section.rstrip('<')
    logger.info(f"After stripping trailing <: '{names_section}'")

    # Split on << (double chevron) to separate last name from given names
    parts = names_section.split('<<')
    logger.info(f"Split by '<<': {parts}")

    if len(parts) < 1:
        logger.warning("No parts found after splitting")
        return "", "", "", ["first_name", "last_name"]

    # First part is last name - single < becomes space
    last_name_raw = parts[0]
    # Replace single < with space (for compound names like ROTARI<DOANI -> ROTARI DOANI)
    last_name = last_name_raw.replace('<', ' ').strip().upper()
    # Clean up multiple spaces
    last_name = re.sub(r' +', ' ', last_name).strip()
    logger.info(f"Last name: raw='{last_name_raw}' -> cleaned='{last_name}'")

    # Validate last name doesn't look like garbage
    if len(last_name) < 2 or not re.match(r'^[A-Z\s]+$', last_name):
        logger.warning(f"Last name '{last_name}' looks invalid")
        low_confidence.append("last_name")

    # Second part contains given names separated by single <
    first_name = ""
    middle_name = ""

    if len(parts) > 1:
        # Join remaining parts (in case there were multiple <<)
        given_section = '<<'.join(parts[1:]).rstrip('<')
        logger.info(f"Given names section: '{given_section}'")

        # Split by single < to get individual given names
        given_names = [n for n in given_section.split('<') if n and len(n) >= 2]
        logger.info(f"Given names split by '<': {given_names}")

        if given_names:
            first_name = given_names[0].upper()
            logger.info(f"First name: '{first_name}'")

            # Validate first name
            if len(first_name) < 2 or not re.match(r'^[A-Z]+$', first_name):
                logger.warning(f"First name '{first_name}' looks invalid")
                low_confidence.append("first_name")

            if len(given_names) > 1:
                # Filter middle names - must be valid
                middle_parts = [n.upper() for n in given_names[1:] if n and re.match(r'^[A-Z]+$', n)]
                middle_name = " ".join(middle_parts)
                logger.info(f"Middle name(s): {given_names[1:]} -> '{middle_name}'")
        else:
            logger.warning("No given names found")
            low_confidence.append("first_name")
    else:
        logger.warning("Only one part found (no << separator)")
        low_confidence.append("first_name")

    logger.info(f"Final names: first='{first_name}', middle='{middle_name}', last='{last_name}'")
    return first_name, middle_name, last_name, low_confidence


def clean_name(name: str) -> str:
    """Clean a name field."""
    if not name:
        return ""

    # Replace hyphens with spaces
    name = name.replace('-', ' ')
    # Remove non-letter characters (except spaces)
    name = re.sub(r'[^A-Za-z\s]', '', name)
    # Remove repeated characters
    name = re.sub(r'(.)\1{3,}', '', name)
    # Clean up spaces
    name = " ".join(name.split())

    return name.upper()


def format_date(date_str: str) -> Tuple[str, bool]:
    """Convert YYMMDD to DD/MM/YYYY format."""
    if not date_str or len(date_str) < 6:
        return date_str, False

    cleaned = re.sub(r'[^0-9]', '', date_str[:6])

    if len(cleaned) != 6:
        return date_str, False

    try:
        yy, mm, dd = cleaned[:2], cleaned[2:4], cleaned[4:6]
        dd_int = int(dd)
        mm_int = int(mm)

        if not (1 <= dd_int <= 31 and 1 <= mm_int <= 12):
            return date_str, False

        year = int(yy)
        full_year = f"20{yy}" if year <= 30 else f"19{yy}"

        return f"{dd}/{mm}/{full_year}", True
    except (ValueError, IndexError):
        return date_str, False


def clean_passport_number(number: str) -> Tuple[str, bool]:
    """Clean passport number."""
    if not number:
        return "", False

    cleaned = number.replace('<', '').strip().upper()
    is_valid = bool(re.match(r'^[A-Z0-9]{5,12}$', cleaned))

    return cleaned, is_valid


def clean_country_code(code: str) -> Tuple[str, bool]:
    """Clean 3-letter country code."""
    code = code.upper().replace("<", "").strip()[:3]
    is_valid = bool(re.match(r'^[A-Z]{3}$', code))

    return code, is_valid


def parse_mrz_with_library(line1: str, line2: str) -> Optional[dict]:
    """Use mrz library to parse and validate MRZ."""
    try:
        line1 = line1.ljust(44, '<')[:44]
        line2 = line2.ljust(44, '<')[:44]

        checker = TD3CodeChecker(line1 + '\n' + line2)

        if checker.result:
            fields = checker.fields()
            return {
                'surname': getattr(fields, 'surname', ''),
                'name': getattr(fields, 'name', ''),
                'nationality': getattr(fields, 'nationality', ''),
                'birth_date': getattr(fields, 'birth_date', ''),
                'sex': getattr(fields, 'sex', ''),
                'document_number': getattr(fields, 'document_number', ''),
                'valid': True
            }
    except Exception as e:
        print(f"MRZ library parsing failed: {e}")

    return None


def parse_mrz_manual(line1: str, line2: str) -> PassportData:
    """
    Manual MRZ parsing.

    Line 1 format: P<CTYLASTNAME<<FIRSTNAME<MIDDLENAME<<<<<<<<<<<<<<<
    - Position 0: Document type (P)
    - Position 1: Type secondary (<)
    - Position 2-4: Country code (3 letters)
    - Position 5+: Names (LASTNAME<<FIRSTNAME<MIDDLENAME)

    Line 2 format: PASSPORT#XCTYDOB___XSEXEXP___XPERSONAL_______X
    - Position 0-8: Passport number (9 chars)
    - Position 9: Check digit for passport number
    - Position 10-12: Nationality (3 letters)
    - Position 13-18: Date of birth (YYMMDD)
    - Position 19: Check digit for DOB
    - Position 20: Sex (M/F/<)
    - Position 21-26: Expiry date (YYMMDD)
    - Position 27: Check digit for expiry
    - Position 28-42: Optional data
    - Position 43: Overall check digit
    """
    logger.info("=" * 60)
    logger.info("MANUAL MRZ PARSING")
    logger.info("=" * 60)
    logger.info(f"Line 1: {line1}")
    logger.info(f"Line 2: {line2}")

    low_confidence_fields = []

    # === PARSE LINE 1: Names ===
    # Extract country code from line 1 (positions 2-5)
    country_from_line1 = line1[2:5] if len(line1) > 5 else ""
    logger.info(f"Country from Line 1 (pos 2-5): '{country_from_line1}'")

    # Names start at position 5
    names_part = line1[5:] if len(line1) > 5 else ""
    logger.info(f"Names part (from pos 5): '{names_part}'")

    first_name, middle_name, last_name, name_confidence = parse_mrz_names(names_part)
    logger.info(f"Parsed names - Last: '{last_name}', First: '{first_name}', Middle: '{middle_name}'")
    low_confidence_fields.extend(name_confidence)

    # === PARSE LINE 2 ===
    # Passport number: positions 0-8 (9 characters, excluding check digit at position 9)
    passport_num_raw = line2[0:9] if len(line2) > 9 else ""
    logger.info(f"Passport number raw (pos 0-9): '{passport_num_raw}'")
    passport_num, pn_valid = clean_passport_number(passport_num_raw)
    logger.info(f"Passport number cleaned: '{passport_num}', valid: {pn_valid}")
    if not pn_valid:
        low_confidence_fields.append("passport_number")

    # Nationality: positions 10-12 (3 characters)
    nationality_raw = line2[10:13] if len(line2) > 13 else ""
    logger.info(f"Nationality raw (pos 10-13): '{nationality_raw}'")
    nationality, nat_valid = clean_country_code(nationality_raw)
    logger.info(f"Nationality cleaned: '{nationality}', valid: {nat_valid}")
    if not nat_valid:
        low_confidence_fields.append("nationality")

    # Date of birth: positions 13-18 (YYMMDD format)
    dob_raw = line2[13:19] if len(line2) > 19 else ""
    logger.info(f"DOB raw (pos 13-19): '{dob_raw}'")
    dob, dob_valid = format_date(dob_raw)
    logger.info(f"DOB formatted: '{dob}', valid: {dob_valid}")
    if not dob_valid:
        low_confidence_fields.append("date_of_birth")

    # Sex: position 20
    sex = line2[20] if len(line2) > 20 else ""
    logger.info(f"Sex (pos 20): '{sex}'")
    gender = sex if sex in ('M', 'F') else ""
    if not gender:
        low_confidence_fields.append("gender")

    result = PassportData(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        gender=gender,
        date_of_birth=dob,
        nationality=nationality,
        passport_number=passport_num,
        confidence=0.8 if not low_confidence_fields else 0.5,
        low_confidence_fields=list(set(low_confidence_fields))
    )

    logger.info("=" * 60)
    logger.info("PARSING RESULT:")
    logger.info(f"  First Name: {result.first_name}")
    logger.info(f"  Middle Name: {result.middle_name}")
    logger.info(f"  Last Name: {result.last_name}")
    logger.info(f"  Gender: {result.gender}")
    logger.info(f"  DOB: {result.date_of_birth}")
    logger.info(f"  Nationality: {result.nationality}")
    logger.info(f"  Passport #: {result.passport_number}")
    logger.info(f"  Confidence: {result.confidence}")
    logger.info(f"  Low confidence fields: {result.low_confidence_fields}")
    logger.info("=" * 60)

    return result


def extract_from_mrz_lines(mrz_lines: List[str]) -> Optional[PassportData]:
    """Extract passport data from MRZ lines (single pair)."""
    if len(mrz_lines) < 2:
        logger.warning("Not enough MRZ lines provided")
        return None

    line1, line2 = mrz_lines[0], mrz_lines[1]

    # Try mrz library first (if available)
    try:
        from mrz.checker.td3 import TD3CodeChecker
        mrz_result = parse_mrz_with_library(line1, line2)

        if mrz_result and mrz_result.get('valid'):
            logger.info("MRZ library parsing succeeded")
            low_confidence_fields = []

            # Parse names
            full_names = mrz_result.get('surname', '') + '<<' + mrz_result.get('name', '')
            first_name, middle_name, last_name, name_confidence = parse_mrz_names(full_names)
            low_confidence_fields.extend(name_confidence)

            # Nationality
            nationality, nat_valid = clean_country_code(mrz_result.get('nationality', ''))
            if not nat_valid:
                low_confidence_fields.append("nationality")

            # Date of birth
            dob, dob_valid = format_date(mrz_result.get('birth_date', ''))
            if not dob_valid:
                low_confidence_fields.append("date_of_birth")

            # Passport number
            passport_num, pn_valid = clean_passport_number(mrz_result.get('document_number', ''))
            if not pn_valid:
                low_confidence_fields.append("passport_number")

            # Gender
            sex = mrz_result.get('sex', '').upper()
            gender = sex if sex in ('M', 'F') else ""
            if not gender:
                low_confidence_fields.append("gender")

            return PassportData(
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                gender=gender,
                date_of_birth=dob,
                nationality=nationality,
                passport_number=passport_num,
                confidence=0.95 if not low_confidence_fields else 0.7,
                low_confidence_fields=list(set(low_confidence_fields))
            )
        else:
            logger.info("MRZ library parsing failed or returned invalid, falling back to manual")
    except ImportError:
        logger.info("MRZ library not available, using manual parsing")
    except Exception as e:
        logger.warning(f"MRZ library error: {e}, falling back to manual parsing")

    # Fallback to manual parsing
    return parse_mrz_manual(line1, line2)


def extract_fields_from_text(text: str) -> Optional[PassportData]:
    """
    TIER 2: Extract passport fields directly from OCR text labels.
    This is used when MRZ parsing fails or returns incomplete data.
    """
    logger.info("=" * 60)
    logger.info("TIER 2: DIRECT FIELD EXTRACTION FROM TEXT")
    logger.info("=" * 60)

    low_confidence_fields = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    text_upper = text.upper()

    logger.info(f"Processing {len(lines)} non-empty lines")

    # Helper to find value after a label - improved version
    def find_value_after_label(label_patterns, text_lines, max_lines_ahead=3):
        for i, line in enumerate(text_lines):
            line_upper = line.upper().strip()
            for pattern in label_patterns:
                if re.search(pattern, line_upper):
                    logger.info(f"  Found label matching '{pattern}' at line {i}: '{line}'")

                    # Check if value is on same line (after the label)
                    match = re.search(pattern + r'[:\s/]*(.+)$', line_upper)
                    if match:
                        value = match.group(1).strip()
                        # Filter out common noise
                        if value and len(value) > 1 and not re.match(r'^[/\-:,\s]+$', value):
                            logger.info(f"    Same line value: '{value}'")
                            return value

                    # Check next few lines for value
                    for j in range(1, min(max_lines_ahead + 1, len(text_lines) - i)):
                        next_line = text_lines[i + j].strip()
                        # Skip empty lines or lines that are just labels
                        if not next_line or len(next_line) < 2:
                            continue
                        # Skip if this line contains another label
                        is_label = any(re.search(p, next_line.upper()) for p in label_patterns)
                        if is_label:
                            break
                        # Skip lines with lots of special characters (likely noise)
                        alpha_ratio = sum(1 for c in next_line if c.isalpha()) / len(next_line) if next_line else 0
                        if alpha_ratio > 0.5 or re.match(r'^[A-Z0-9\s\-]+$', next_line.upper()):
                            logger.info(f"    Next line value: '{next_line}'")
                            return next_line
        return ""

    # === EXTRACT SURNAME / LAST NAME ===
    surname_patterns = [
        r'\bSURNAME\b',
        r'\bFAMILY\s*NAME\b',
        r'\bLAST\s*NAME\b',
        r'CSAL[AÁ]DI\s*N[EÉ]V',  # Hungarian
        r'\bNUMELUL\b',  # Romanian
        r'\b1\.\s*NUMELE\b',  # Romanian numbered
    ]
    logger.info("Looking for surname...")
    last_name = find_value_after_label(surname_patterns, lines)
    # Clean: remove any label text and non-alpha characters
    last_name = re.sub(r'(?:SURNAME|FAMILY\s*NAME|NOM|NUMELE|/.*)', '', last_name, flags=re.IGNORECASE).strip()
    # Replace hyphens with spaces for compound names
    last_name = last_name.replace('-', ' ')
    last_name = re.sub(r'[^A-Za-z\s]', '', last_name).strip().upper()
    # Clean up multiple spaces
    last_name = re.sub(r' +', ' ', last_name)
    # Take only the first word if multiple
    if last_name and ' ' in last_name:
        parts = last_name.split()
        # Filter out noise words
        parts = [p for p in parts if len(p) > 1 and p not in ['OF', 'THE', 'AND']]
        if parts:
            last_name = parts[0]
    logger.info(f"Extracted surname: '{last_name}'")

    # === EXTRACT GIVEN NAMES / FIRST NAME ===
    given_patterns = [
        r'\bGIVEN\s*NAME',
        r'\bFIRST\s*NAME',
        r'\bFORENAME',
        r'\bPR[EÉ]NOM',  # French
        r'UT[OÓ]N[EÉ]V',  # Hungarian
        r'\bPRENUMELE\b',  # Romanian
        r'\b2\.\s*PRENUMELE\b',  # Romanian numbered
    ]
    logger.info("Looking for given names...")

    # Garbage patterns to skip (watermark text from passports)
    garbage_patterns = [
        r'^OFISRA',  # Partial "OF ISRAEL"
        r'^FISRA',   # Partial "F ISRAEL"
        r'^ISRAEL',
        r'^STATE',
        r'^SRAE',
        r'ISRAEL\d',  # ISRAEL7, etc.
        r'^OFISRAB',  # OCR mangled "OF ISRAEL"
        r'^SPRIN',   # Garbage OCR
        r'^SUMA',    # Garbage OCR
        r'^MAON',    # Garbage OCR
        r'OFISRAEL', # Combined "OF ISRAEL"
        r'^[A-Z]{1,3}\d{2,}',  # Letter+numbers pattern (likely document noise)
        r'^\d+[A-Z]+$',  # Numbers followed by letters (likely noise)
        r'^ROMANEASCA',  # Romanian watermark
        r'^PASAPORT',  # Passport label misread as name
        r'^PASSPORT',
    ]

    # Custom search for given name that skips garbage
    given_names = ""
    for i, line in enumerate(lines):
        line_upper = line.upper().strip()
        if any(re.search(p, line_upper) for p in given_patterns):
            logger.info(f"  Found given name label at line {i}: {line}")
            # Search next several lines for a valid name
            for j in range(1, min(15, len(lines) - i)):
                candidate = lines[i + j].strip()
                candidate_upper = candidate.upper()

                if not candidate or len(candidate) < 2:
                    continue

                # Skip if it's another label
                if any(re.search(p, candidate_upper) for p in given_patterns + surname_patterns):
                    break

                # Skip garbage/watermark text
                is_garbage = any(re.search(gp, candidate_upper) for gp in garbage_patterns)
                if is_garbage:
                    logger.info(f"    Skipping garbage: '{candidate}'")
                    continue

                # Skip if mostly non-alphabetic
                alpha_count = sum(1 for c in candidate if c.isalpha())
                if alpha_count < len(candidate) * 0.7:
                    continue

                # Found a valid name candidate
                logger.info(f"    Found given name: '{candidate}'")
                given_names = candidate
                break
            break

    given_names = re.sub(r'(?:GIVEN\s*NAME|FIRST\s*NAME|FORENAME|PRENUMELE|PR[EÉ]NOM|/.*)', '', given_names, flags=re.IGNORECASE).strip()
    # Replace hyphens with spaces for compound names
    given_names = given_names.replace('-', ' ')
    given_names = re.sub(r'[^A-Za-z\s]', '', given_names).strip().upper()
    # Clean up multiple spaces
    given_names = re.sub(r' +', ' ', given_names)
    # Filter out noise words
    if given_names:
        parts = given_names.split()
        parts = [p for p in parts if len(p) > 1 and p not in ['OF', 'THE', 'AND', 'ISRAEL', 'STATE', 'FISRAEL', 'OFISRAEL']]
        given_names = ' '.join(parts)
    logger.info(f"Extracted given names: '{given_names}'")

    # Split given names into first and middle
    first_name = ""
    middle_name = ""
    if given_names:
        name_parts = given_names.split()
        if name_parts:
            first_name = name_parts[0]
            if len(name_parts) > 1:
                middle_name = " ".join(name_parts[1:])

    # === EXTRACT PASSPORT NUMBER ===
    passport_num = ""
    logger.info("Looking for passport number...")

    # Try specific patterns first
    pn_patterns = [
        r'PASSPORT\s*(?:NO\.?|NUMBER|#)[:\s]*([A-Z0-9]{6,12})',
        r'DOCUMENT\s*(?:NO\.?|NUMBER)[:\s]*([A-Z0-9]{6,12})',
        r'[ÚU]TLEV[ÉE]LSZ[ÁA]M[:\s/]*([A-Z0-9]{6,12})',  # Hungarian
        r'NO\.?\s+([A-Z]{0,2}[0-9]{7,9})\b',
    ]
    for pattern in pn_patterns:
        match = re.search(pattern, text_upper)
        if match:
            passport_num = match.group(1).strip()
            logger.info(f"Found passport number via pattern '{pattern}': '{passport_num}'")
            break

    # Try to find value after "Passport No" label
    if not passport_num:
        pp_label_patterns = [
            r'\bPASSPORT\s*NO\b',
            r'\bPASSPORT\s*NUMBER\b',
            r'[ÚU]TLEV[ÉE]LSZ[ÁA]M',
        ]
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if any(re.search(p, line_upper) for p in pp_label_patterns):
                # Look for number on same line or next lines
                for j in range(0, min(3, len(lines) - i)):
                    check_line = lines[i + j] if j == 0 else lines[i + j]
                    # Find any 7-9 digit number
                    num_match = re.search(r'\b([A-Z]{0,2}[0-9]{7,9})\b', check_line.upper())
                    if num_match:
                        passport_num = num_match.group(1)
                        logger.info(f"Found passport number near label: '{passport_num}'")
                        break
                if passport_num:
                    break

    # If still not found, look for standalone passport-like numbers
    if not passport_num:
        for line in lines:
            cleaned = re.sub(r'[^A-Z0-9]', '', line.upper())
            if re.match(r'^[A-Z]{0,2}[0-9]{7,9}$', cleaned) and len(cleaned) >= 7:
                passport_num = cleaned
                logger.info(f"Found passport number as standalone: '{passport_num}'")
                break

    # Last resort: find any 8-9 digit number in the text
    if not passport_num:
        all_numbers = re.findall(r'\b(\d{8,9})\b', text)
        if all_numbers:
            passport_num = all_numbers[0]
            logger.info(f"Found passport number from digit search: '{passport_num}'")

    # === EXTRACT DATE OF BIRTH ===
    dob = ""
    logger.info("Looking for date of birth...")

    dob_label_patterns = [
        r'DATE\s*OF\s*BIRTH',
        r'BIRTH\s*DATE',
        r'\bDOB\b',
        r'SZ[ÜU]LET[ÉE]SI',  # Hungarian
        r'N[ÉE]\s*LE',  # French
        r'DATA\s*NA[SȘ]TERII',  # Romanian
    ]

    month_map = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
                'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'}

    # First try to find labeled DOB
    for i, line in enumerate(lines):
        line_upper = line.upper()
        if any(re.search(p, line_upper) for p in dob_label_patterns):
            # Look for date on same line or next few lines
            search_text = ' '.join(lines[i:min(i+3, len(lines))])

            # Try various date formats
            # DD/MM/YYYY or DD-MM-YYYY
            date_match = re.search(r'(\d{2})[/\-\.](\d{2})[/\-\.](\d{4})', search_text)
            if date_match:
                day, month, year = date_match.groups()
                dob = f"{day}/{month}/{year}"
                logger.info(f"Found DOB (DD/MM/YYYY): '{dob}'")
                break

            # DD MMM YY or DD MMM YYYY (e.g., 05 AUG 96)
            date_match = re.search(r'(\d{1,2})\s*([A-Z]{3})[/\s]*([A-Z]{3})?\s*(\d{2,4})', search_text.upper())
            if date_match:
                day = date_match.group(1)
                month_str = date_match.group(2)
                year = date_match.group(4)
                month = month_map.get(month_str, '01')
                if len(year) == 2:
                    year = f"20{year}" if int(year) <= 30 else f"19{year}"
                dob = f"{day.zfill(2)}/{month}/{year}"
                logger.info(f"Found DOB (DD MMM YY): '{dob}'")
                break

    # Try DD/MM/YYYY format anywhere in text
    if not dob:
        date_matches = re.findall(r'(\d{2})/(\d{2})/(\d{4})', text)
        # Filter for reasonable birth dates (year > 1940, year < 2020)
        for match in date_matches:
            day, month, year = match
            if 1940 < int(year) < 2020:
                dob = f"{day}/{month}/{year}"
                logger.info(f"Found DOB from date pattern: '{dob}'")
                break

    logger.info(f"Extracted DOB: '{dob}'")

    # === EXTRACT GENDER ===
    gender = ""
    logger.info("Looking for gender...")

    # Look for Sex/Gender label and value
    for i, line in enumerate(lines):
        line_upper = line.upper()
        if re.search(r'\bSEX\b|\bGENDER\b|\bNEM\b|\bSEXE\b|\bSEXUARE\b', line_upper):
            logger.info(f"  Found sex/gender label at line {i}: {line}")
            # Check same line for M or F (possibly with slash like F/M or M/F)
            mf_match = re.search(r'[/\s]([MF])[/\s]|[/\s]([MF])$|^([MF])[/\s]|\b([MF])\b', line_upper)
            if mf_match:
                gender = next(g for g in mf_match.groups() if g)
                logger.info(f"Found gender on same line: '{gender}'")
                break
            # Check next few lines
            for j in range(1, min(4, len(lines) - i)):
                next_line = lines[i + j].strip()
                next_upper = next_line.upper()
                if not next_line:
                    continue
                # Single letter M or F
                if next_upper in ['M', 'F']:
                    gender = next_upper
                    logger.info(f"Found gender on line {i+j}: '{gender}'")
                    break
                if next_upper in ['MALE', 'FEMALE']:
                    gender = 'M' if next_upper == 'MALE' else 'F'
                    logger.info(f"Found gender on line {i+j}: '{gender}'")
                    break
                # F/M pattern or M/F
                mf_match = re.search(r'^([MF])[/\s]|[/\s]([MF])$', next_upper)
                if mf_match:
                    gender = next(g for g in mf_match.groups() if g)
                    logger.info(f"Found gender on line {i+j}: '{gender}'")
                    break
            if gender:
                break

    # Fallback patterns
    if not gender:
        # Look for F/M or M/F patterns anywhere
        fm_match = re.search(r'\bF\s*/\s*M\b', text_upper)
        if fm_match:
            gender = "F"
            logger.info("Found F/M pattern, using F")
        else:
            mf_match = re.search(r'\bM\s*/\s*F\b', text_upper)
            if mf_match:
                gender = "M"
                logger.info("Found M/F pattern, using M")

    if not gender:
        if re.search(r'\bMALE\b', text_upper) and not re.search(r'\bFEMALE\b', text_upper):
            gender = "M"
            logger.info("Found MALE keyword")
        elif re.search(r'\bFEMALE\b', text_upper):
            gender = "F"
            logger.info("Found FEMALE keyword")

    # Hebrew for male/female (ז = male, נ = female)
    if not gender:
        if 'זכר' in text or ' ז' in text or '/ז' in text:
            gender = "M"
            logger.info("Found Hebrew male indicator")
        elif 'נקבה' in text or ' נ' in text or '/נ' in text:
            gender = "F"
            logger.info("Found Hebrew female indicator")

    logger.info(f"Extracted gender: '{gender}'")

    # === EXTRACT NATIONALITY ===
    nationality = ""
    logger.info("Looking for nationality...")

    # Country name to code mapping
    country_codes = {
        'HUNGARIAN': 'HUN', 'HUNGARY': 'HUN', 'MAGYAR': 'HUN',
        'ISRAELI': 'ISR', 'ISRAEL': 'ISR',
        'AMERICAN': 'USA', 'UNITED STATES': 'USA',
        'BRITISH': 'GBR', 'UNITED KINGDOM': 'GBR',
        'GERMAN': 'DEU', 'GERMANY': 'DEU',
        'FRENCH': 'FRA', 'FRANCE': 'FRA',
        'ITALIAN': 'ITA', 'ITALY': 'ITA',
        'SPANISH': 'ESP', 'SPAIN': 'ESP',
        'CANADIAN': 'CAN', 'CANADA': 'CAN',
        'AUSTRALIAN': 'AUS', 'AUSTRALIA': 'AUS',
        'ROMANIAN': 'ROU', 'ROMANIA': 'ROU', 'ROMANA': 'ROU',
        'POLISH': 'POL', 'POLAND': 'POL',
        'UKRAINIAN': 'UKR', 'UKRAINE': 'UKR',
        'RUSSIAN': 'RUS', 'RUSSIA': 'RUS',
        'MOLDOVAN': 'MDA', 'MOLDOVA': 'MDA',
    }

    # Look for nationality label and value
    for i, line in enumerate(lines):
        line_upper = line.upper()
        if re.search(r'\bNATIONALITY\b|\bCITIZENSHIP\b|\bÁLLAMPOLGÁRSÁG\b', line_upper):
            # Check same line
            for name, code in country_codes.items():
                if name in line_upper:
                    nationality = code
                    logger.info(f"Found nationality on same line: '{nationality}'")
                    break
            # Check next line
            if not nationality and i + 1 < len(lines):
                next_line = lines[i + 1].upper().strip()
                for name, code in country_codes.items():
                    if name in next_line:
                        nationality = code
                        logger.info(f"Found nationality on next line: '{nationality}'")
                        break
            if nationality:
                break

    # Look for 3-letter country code
    if not nationality:
        # Common 3-letter codes
        code_match = re.search(r'\b(HUN|ISR|USA|GBR|DEU|FRA|ITA|ESP|CAN|AUS|ROU|POL|UKR|RUS|MDA)\b', text_upper)
        if code_match:
            nationality = code_match.group(1)
            logger.info(f"Found nationality code: '{nationality}'")

    # Look for country names anywhere in text
    if not nationality:
        for name, code in country_codes.items():
            if name in text_upper:
                nationality = code
                logger.info(f"Found nationality from country name: '{nationality}'")
                break

    logger.info(f"Extracted nationality: '{nationality}'")

    # === BUILD RESULT ===
    if not last_name:
        low_confidence_fields.append("last_name")
    if not first_name:
        low_confidence_fields.append("first_name")
    if not passport_num:
        low_confidence_fields.append("passport_number")
    if not dob:
        low_confidence_fields.append("date_of_birth")
    if not gender:
        low_confidence_fields.append("gender")
    if not nationality:
        low_confidence_fields.append("nationality")

    logger.info("=" * 60)
    logger.info("TIER 2 EXTRACTION RESULT:")
    logger.info(f"  Last Name: {last_name}")
    logger.info(f"  First Name: {first_name}")
    logger.info(f"  Middle Name: {middle_name}")
    logger.info(f"  Passport #: {passport_num}")
    logger.info(f"  DOB: {dob}")
    logger.info(f"  Gender: {gender}")
    logger.info(f"  Nationality: {nationality}")
    logger.info(f"  Low confidence: {low_confidence_fields}")
    logger.info("=" * 60)

    # Return if we found at least some data
    if last_name or first_name or passport_num:
        return PassportData(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            gender=gender,
            date_of_birth=dob,
            nationality=nationality,
            passport_number=passport_num,
            confidence=0.5 if len(low_confidence_fields) <= 2 else 0.3,
            low_confidence_fields=list(set(low_confidence_fields))
        )

    return None


def is_valid_name(name: str) -> bool:
    """Check if a name looks valid (not garbage OCR)."""
    if not name or len(name) < 2:
        return False

    # Garbage patterns that indicate OCR errors
    garbage_indicators = [
        r'OFISRA', r'FISRA', r'ISRAEL', r'STATE', r'PASAPORT', r'PASSPORT',
        r'SPRIN', r'SUMA', r'MAON', r'ROMANA', r'DOCUMENT', r'REPUBLIC',
        r'^\d', r'\d$',  # Starts or ends with digit
    ]

    name_upper = name.upper()
    for pattern in garbage_indicators:
        if re.search(pattern, name_upper):
            logger.info(f"Name '{name}' flagged as garbage (matched: {pattern})")
            return False

    # Check for reasonable name patterns
    # Valid names should be mostly alphabetic (spaces allowed for compound names)
    alpha_count = sum(1 for c in name if c.isalpha() or c == ' ')
    if alpha_count < len(name) * 0.8:
        logger.info(f"Name '{name}' flagged as garbage (low alpha ratio)")
        return False

    # Check for too many consecutive consonants (likely garbage)
    consonants = 'BCDFGHJKLMNPQRSTVWXYZ'
    consec = 0
    max_consec = 0
    for c in name.upper():
        if c in consonants:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    if max_consec > 5:  # More than 5 consecutive consonants is suspicious
        logger.info(f"Name '{name}' flagged as garbage (too many consecutive consonants)")
        return False

    return True


def is_valid_passport_number(pn: str) -> bool:
    """Check if passport number looks valid."""
    if not pn:
        return False

    # Valid passport numbers are typically 7-9 alphanumeric characters
    if not re.match(r'^[A-Z0-9]{7,9}$', pn.upper()):
        return False

    return True


def merge_passport_data(mrz_data: Optional[PassportData], text_data: Optional[PassportData]) -> Optional[PassportData]:
    """
    Merge MRZ parsing results with direct text extraction.
    MRZ data takes ABSOLUTE priority when valid.
    Text extraction only fills truly empty MRZ fields with valid-looking data.
    """
    if not mrz_data and not text_data:
        return None

    if not mrz_data:
        return text_data

    if not text_data:
        return mrz_data

    logger.info("=" * 60)
    logger.info("MERGING MRZ + TEXT EXTRACTION DATA")
    logger.info("=" * 60)
    logger.info(f"MRZ Data: first='{mrz_data.first_name}', last='{mrz_data.last_name}', pn='{mrz_data.passport_number}'")
    logger.info(f"Text Data: first='{text_data.first_name}', last='{text_data.last_name}', pn='{text_data.passport_number}'")

    # Helper to choose best value: MRZ takes priority if valid
    def choose_name(mrz_val: str, text_val: str, field_name: str) -> str:
        # MRZ always wins if it has a value
        if mrz_val and is_valid_name(mrz_val):
            logger.info(f"  {field_name}: Using MRZ value '{mrz_val}'")
            return mrz_val
        elif mrz_val:
            # MRZ has value but it looks like garbage - still prefer it over text extraction
            # because MRZ is more reliable source, text extraction garbage is usually worse
            logger.info(f"  {field_name}: MRZ value '{mrz_val}' looks suspicious, but still using it")
            return mrz_val
        elif text_val and is_valid_name(text_val):
            logger.info(f"  {field_name}: MRZ empty, using text value '{text_val}'")
            return text_val
        else:
            logger.info(f"  {field_name}: No valid value found")
            return mrz_val or text_val or ""

    def choose_value(mrz_val: str, text_val: str, field_name: str) -> str:
        # MRZ always wins if it has a value
        if mrz_val:
            logger.info(f"  {field_name}: Using MRZ value '{mrz_val}'")
            return mrz_val
        elif text_val:
            logger.info(f"  {field_name}: MRZ empty, using text value '{text_val}'")
            return text_val
        else:
            return ""

    # MRZ passport number validation - should be 7-9 chars, not nationality code
    mrz_pn = mrz_data.passport_number
    text_pn = text_data.passport_number

    # Validate passport numbers
    mrz_pn_valid = is_valid_passport_number(mrz_pn)
    text_pn_valid = is_valid_passport_number(text_pn)

    if mrz_pn_valid:
        passport_number = mrz_pn
        logger.info(f"  passport_number: Using MRZ value '{mrz_pn}'")
    elif text_pn_valid:
        passport_number = text_pn
        logger.info(f"  passport_number: MRZ invalid, using text value '{text_pn}'")
    else:
        passport_number = mrz_pn or text_pn
        logger.info(f"  passport_number: No valid passport number found, using '{passport_number}'")

    merged = PassportData(
        first_name=choose_name(mrz_data.first_name, text_data.first_name, "first_name"),
        middle_name=choose_name(mrz_data.middle_name, text_data.middle_name, "middle_name"),
        last_name=choose_name(mrz_data.last_name, text_data.last_name, "last_name"),
        gender=choose_value(mrz_data.gender, text_data.gender, "gender"),
        date_of_birth=choose_value(mrz_data.date_of_birth, text_data.date_of_birth, "date_of_birth"),
        nationality=choose_value(mrz_data.nationality, text_data.nationality, "nationality"),
        passport_number=passport_number,
        confidence=max(mrz_data.confidence, text_data.confidence),
        low_confidence_fields=[]
    )

    # Recalculate low confidence fields
    if not merged.first_name:
        merged.low_confidence_fields.append("first_name")
    if not merged.last_name:
        merged.low_confidence_fields.append("last_name")
    if not merged.passport_number:
        merged.low_confidence_fields.append("passport_number")
    if not merged.date_of_birth:
        merged.low_confidence_fields.append("date_of_birth")
    if not merged.gender:
        merged.low_confidence_fields.append("gender")
    if not merged.nationality:
        merged.low_confidence_fields.append("nationality")

    logger.info(f"MERGED RESULT: {merged.first_name} {merged.last_name} - {merged.passport_number}")
    logger.info("=" * 60)

    return merged


def rotate_image_arbitrary(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotate image by arbitrary angle (in degrees)."""
    if angle == 0:
        return image

    height, width = image.shape[:2]
    center = (width // 2, height // 2)

    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    cos = np.abs(rotation_matrix[0, 0])
    sin = np.abs(rotation_matrix[0, 1])
    new_width = int((height * sin) + (width * cos))
    new_height = int((height * cos) + (width * sin))

    rotation_matrix[0, 2] += (new_width / 2) - center[0]
    rotation_matrix[1, 2] += (new_height / 2) - center[1]

    rotated = cv2.warpAffine(image, rotation_matrix, (new_width, new_height),
                              borderMode=cv2.BORDER_CONSTANT,
                              borderValue=(255, 255, 255))

    return rotated


def process_passport_image(image_bytes: bytes, rotation_angle: float = 0) -> List[dict]:
    """
    Main function to process a passport image using Google Cloud Vision API.

    TWO-TIER STRATEGY:
    1. TIER 1: Try MRZ parsing (most accurate if MRZ is readable)
    2. TIER 2: Direct field extraction from text labels (fallback)
    3. Merge results: MRZ data + fill gaps from text extraction
    """
    logger.info("=" * 60)
    logger.info("PROCESSING PASSPORT IMAGE (TWO-TIER STRATEGY)")
    logger.info("=" * 60)

    # Load image
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        logger.error("Failed to decode image")
        return []

    logger.info(f"Image size: {image.shape}")

    # Apply manual rotation if specified
    if rotation_angle != 0:
        logger.info(f"Applying rotation: {rotation_angle} degrees")
        image = rotate_image_arbitrary(image, rotation_angle)
        # Re-encode for API
        _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        image_bytes = buffer.tobytes()

    # Convert to base64 for Google Vision API
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')

    # Call Google Cloud Vision API
    logger.info("Calling Google Cloud Vision API...")
    vision_response = call_google_vision_api(image_base64)

    if not vision_response:
        logger.error("No response from Google Vision API")
        return []

    # Extract text from response
    full_text = extract_text_from_vision_response(vision_response)

    if not full_text:
        logger.error("No text extracted from image")
        return []

    results = []

    # === TIER 1: MRZ PARSING ===
    logger.info("=" * 60)
    logger.info("TIER 1: MRZ PARSING")
    logger.info("=" * 60)

    mrz_pairs = find_mrz_lines(full_text)
    logger.info(f"Found {len(mrz_pairs)} MRZ pair(s)")

    mrz_results = []
    if mrz_pairs:
        for i, mrz_lines in enumerate(mrz_pairs):
            logger.info(f"Processing MRZ pair {i + 1}...")
            passport_data = extract_from_mrz_lines(mrz_lines)
            if passport_data:
                logger.info(f"MRZ parsed passport {i + 1}: {passport_data.first_name} {passport_data.last_name} - {passport_data.passport_number}")
                mrz_results.append(passport_data)
            else:
                logger.warning(f"Failed to parse MRZ pair {i + 1}")
                mrz_results.append(None)

    # === TIER 2: DIRECT TEXT EXTRACTION ===
    # Always try text extraction to fill gaps
    logger.info("=" * 60)
    logger.info("TIER 2: DIRECT TEXT EXTRACTION")
    logger.info("=" * 60)

    text_data = extract_fields_from_text(full_text)

    # === MERGE RESULTS ===
    if mrz_results:
        # We have MRZ results - merge with text extraction to fill gaps
        for mrz_data in mrz_results:
            merged = merge_passport_data(mrz_data, text_data)
            if merged:
                results.append(merged)
    elif text_data:
        # No MRZ found - use text extraction only
        logger.info("Using TIER 2 text extraction results only")
        results.append(text_data)

    # === FINAL OUTPUT ===
    logger.info("=" * 60)
    logger.info(f"FINAL RESULTS: {len(results)} passport(s) extracted")
    logger.info("=" * 60)

    for i, r in enumerate(results):
        logger.info(f"  Passport {i + 1}:")
        logger.info(f"    Name: {r.first_name} {r.middle_name} {r.last_name}")
        logger.info(f"    Passport #: {r.passport_number}")
        logger.info(f"    DOB: {r.date_of_birth}")
        logger.info(f"    Gender: {r.gender}")
        logger.info(f"    Nationality: {r.nationality}")
        logger.info(f"    Confidence: {r.confidence}")
        logger.info(f"    Low confidence fields: {r.low_confidence_fields}")

    # Helper to clean name - replace hyphens with spaces
    def clean_name_output(name: str) -> str:
        if not name:
            return ""
        # Replace hyphens with spaces and clean up multiple spaces
        return re.sub(r' +', ' ', name.replace('-', ' ')).strip()

    return [
        {
            "first_name": clean_name_output(r.first_name),
            "middle_name": clean_name_output(r.middle_name),
            "last_name": clean_name_output(r.last_name),
            "gender": r.gender,
            "date_of_birth": r.date_of_birth,
            "nationality": r.nationality,
            "passport_number": r.passport_number,
            "confidence": r.confidence,
            "low_confidence_fields": r.low_confidence_fields
        }
        for r in results
    ]
