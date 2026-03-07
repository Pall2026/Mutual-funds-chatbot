"""
pdf_extractor.py — Download PDF and extract scheme fields using PyMuPDF.
Accepts pdf_url and scheme_name as arguments.
Saves each found field as a row in scheme_fields with is_pdf=True.
Never guesses values — if field not found, it is skipped silently.
"""

import os
import re
import sys
import requests
import fitz  # PyMuPDF
from typing import Optional
from dotenv import load_dotenv
from db import insert_field

load_dotenv()

# Fields to look for in PDF text.
# Each entry: (field_name, list of regex patterns to try)
FIELD_PATTERNS = {
    "expense_ratio_direct": [
        r"(?:direct[^\n]*?plan[^\n]*?)?(?:expense ratio|ter)[^\n]*?direct[^\n]*?(\d+\.?\d*\s*%)",
        r"direct\s*plan[^\n]*?(\d+\.?\d*\s*%)",
        r"expense ratio[^\n]*?direct[^\n]*?(\d+\.?\d*\s*%)",
    ],
    "expense_ratio_regular": [
        r"(?:regular[^\n]*?plan[^\n]*?)?(?:expense ratio|ter)[^\n]*?regular[^\n]*?(\d+\.?\d*\s*%)",
        r"regular\s*plan[^\n]*?(\d+\.?\d*\s*%)",
        r"expense ratio[^\n]*?regular[^\n]*?(\d+\.?\d*\s*%)",
    ],
    "exit_load": [
        r"exit\s*load[^\n]*?(\d+\.?\d*\s*%[^\n]*)",
        r"exit\s*load[^\n]*?(nil|none|zero|no\s*exit)[^\n]*",
    ],
    "exit_load_period": [
        r"exit\s*load[^\n]*?(\d+\s*(?:year|month|day)[s]?[^\n]*)",
        r"within\s*(\d+\s*(?:year|month|day)[s]?)",
        r"redemption\s*within\s*(\d+\s*(?:year|month|day)[s]?)",
    ],
    "minimum_sip": [
        r"minimum[^\n]*?sip[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)(\d[\d,]*)[^\n]*",
        r"sip[^\n]*?minimum[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)(\d[\d,]*)[^\n]*",
        r"systematic\s*investment\s*plan[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)(\d[\d,]*)[^\n]*",
    ],
    "minimum_lumpsum": [
        r"minimum[^\n]*?(?:lump[- ]?sum|purchase|investment)[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)(\d[\d,]*)[^\n]*",
        r"(?:lump[- ]?sum|initial)[^\n]*?minimum[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)(\d[\d,]*)[^\n]*",
        r"minimum\s*application\s*amount[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)(\d[\d,]*)[^\n]*",
    ],
    "lock_in_period": [
        r"lock[- ]?in[^\n]*?(\d+\s*year[s]?)[^\n]*",
        r"(\d+\s*year[s]?)[^\n]*lock[- ]?in[^\n]*",
    ],
    "riskometer_level": [
        r"riskometer[^\n]*?(low|moderate|moderately\s*high|high|very\s*high)[^\n]*",
        r"risk[^\n]*?(low|moderate|moderately\s*high|high|very\s*high)[^\n]*",
        r"(low|moderate|moderately\s*high|high|very\s*high)\s*risk[^\n]*",
    ],
    "benchmark_index": [
        r"benchmark[^\n]*?(?:index)?[:\-\s]+([\w\s\-&]+(?:index|500|sensex|nifty|bse|nse)[^\n]*)",
        r"(?:benchmark|index)[^\n]*?:\s*([^\n]+)",
    ],
    "fund_manager": [
        r"fund\s*manager[s]?[:\-\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
        r"managed\s*by[:\-\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    ],
    "aum": [
        r"aum[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)?(\d[\d,.]*\s*(?:cr|crore|lakh|million|billion)?)[^\n]*",
        r"assets\s*under\s*management[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)?(\d[\d,.]*\s*(?:cr|crore|lakh|million|billion)?)[^\n]*",
        r"corpus[^\n]*?(?:rs\.?\s*|inr\s*|₹\s*)?(\d[\d,.]*\s*(?:cr|crore|lakh|million|billion)?)[^\n]*",
    ],
    "scheme_category": [
        r"(?:scheme|fund)\s*categor[yi][^\n]*?:\s*([^\n]+)",
        r"categor[yi][^\n]*?:\s*([^\n]+(?:fund|equity|debt|hybrid|solution)[^\n]*)",
        r"type\s*of\s*scheme[^\n]*?:\s*([^\n]+)",
    ],
}


# Scheme name detection rules for TER disclosure PDFs (Fix 1).
# Checked in order — first match wins.
SCHEME_NAME_SIGNALS = [
    (["sbi bluechip", "sbi large cap", "sbi largecap"], "SBI Bluechip Fund"),
    (["sbi flexicap", "sbi flexi cap", "sbi flexi-cap"], "SBI Flexicap Fund"),
    (["sbi elss", "sbi long term equity", "sbi lonterm equity"], "SBI ELSS Tax Saver Fund"),
    (["sbi small cap", "sbi smallcap"], "SBI Small Cap Fund"),
]


def detect_scheme_from_text(text: str) -> str:
    """
    Detect which scheme a PDF belongs to by searching for known name keywords.
    Returns the canonical scheme name, or "GENERAL" if no match found.
    Used for TER disclosure PDFs where scheme_name is not known in advance.
    """
    text_lower = text.lower()
    for keywords, canonical_name in SCHEME_NAME_SIGNALS:
        if any(kw in text_lower for kw in keywords):
            return canonical_name
    return "GENERAL"


def download_pdf(pdf_url: str) -> bytes:
    """Download PDF bytes from URL."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(pdf_url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.content


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from PDF bytes using PyMuPDF."""
    text_parts = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)


def find_field(field_name: str, text: str, scheme_name: str) -> Optional[str]:
    """
    Try each regex pattern for a field and return the first match found.
    Special case: lock_in_period for ELSS is always '3 years'.
    Returns None if field not found — never guesses.
    """
    # Special ELSS lock-in rule from architecture
    if field_name == "lock_in_period":
        if "elss" in scheme_name.lower() or "tax saver" in scheme_name.lower() or "long term equity" in scheme_name.lower():
            return "3 years"
        # Non-ELSS funds: try regex
    
    patterns = FIELD_PATTERNS.get(field_name, [])
    text_lower = text.lower()

    for pattern in patterns:
        try:
            match = re.search(pattern, text_lower, re.IGNORECASE | re.MULTILINE)
            if match:
                # Return the first captured group, stripped
                value = match.group(1).strip()
                if value:
                    return value
        except re.error:
            continue
    return None


def extract_and_save(pdf_url: str, scheme_name: str, is_sid: bool = False, auto_detect_scheme: bool = False):
    """
    Main entry point: download PDF, extract text, find fields, save to DB.
    If field not found — skip silently.

    Args:
        pdf_url:            URL of the PDF to download.
        scheme_name:        Canonical scheme name. If auto_detect_scheme=True,
                            this value is used only as fallback.
        is_sid:             If True, use 50,000-char text limit (SID docs are
                            100+ pages; key tables appear deep in the document).
        auto_detect_scheme: If True, detect scheme name from PDF text first
                            (for TER disclosure PDFs). Falls back to scheme_name.
    """
    print(f"  Downloading PDF: {pdf_url}")
    try:
        pdf_bytes = download_pdf(pdf_url)
    except Exception as e:
        print(f"  ERROR downloading {pdf_url}: {e}")
        return

    print(f"  Extracting text from PDF...")
    try:
        text = extract_text_from_pdf(pdf_bytes)
    except Exception as e:
        print(f"  ERROR extracting text from {pdf_url}: {e}")
        return

    if not text.strip():
        print(f"  WARNING: No text extracted from {pdf_url}. Skipping.")
        return

    # Fix 1: auto-detect scheme name from PDF content for TER disclosure PDFs.
    if auto_detect_scheme:
        detected = detect_scheme_from_text(text)
        if detected != "GENERAL":
            print(f"  Detected scheme: '{detected}' (overrides passed scheme_name='{scheme_name}')")
        else:
            print(f"  Scheme not detected in PDF text. Using fallback: '{scheme_name}'")
            detected = scheme_name
        scheme_name = detected

    # Fix 2: SID PDFs use 50,000-char limit; all others use full text.
    # SID docs are 100+ pages — exit load tables and other key data
    # can appear anywhere throughout the document.
    text_for_search = text[:50000] if is_sid else text

    # Determine which fields to look for
    fields_to_extract = list(FIELD_PATTERNS.keys())
    # Only add lock_in_period for ELSS
    if "lock_in_period" not in fields_to_extract:
        fields_to_extract.append("lock_in_period")

    fields_saved = 0
    for field_name in fields_to_extract:
        value = find_field(field_name, text_for_search, scheme_name)
        if value:
            try:
                insert_field(
                    scheme_name=scheme_name,
                    field_name=field_name,
                    field_value=value,
                    source_url=pdf_url,
                    is_pdf=True,
                )
                fields_saved += 1
            except Exception as e:
                print(f"  ERROR saving field '{field_name}' for {scheme_name}: {e}")

    print(f"  Saved {fields_saved} fields from PDF for {scheme_name}.")


# KIM PDFs to process
KIM_PDFS = [
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/kim---sbi-large-cap-fund-(formerly-known-as-bluechip-fund).pdf",
        "SBI Bluechip Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/kim---sbi-flexicap-fund.pdf",
        "SBI Flexicap Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/kim---sbi-elss-tax-saver-fund-(formerly-known-as-sbi-long-term-equity-fund).pdf",
        "SBI ELSS Tax Saver Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/kim---sbi-small-cap-fund.pdf",
        "SBI Small Cap Fund",
    ),
]

# SID PDFs to process
SID_PDFS = [
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/sid---sbi-large-cap-fund-(formerly-known-as-bluechip-fund).pdf",
        "SBI Bluechip Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/sid---sbi-flexicap-fund.pdf",
        "SBI Flexicap Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/sid---sbi-elss-tax-saver-fund.pdf",
        "SBI ELSS Tax Saver Fund",
    ),
    (
        "https://www.sbimf.com/docs/default-source/sif-forms/sid---sbi-small-cap-fund.pdf",
        "SBI Small Cap Fund",
    ),
]


def process_all_kim_sid():
    """Process all KIM and SID PDFs. Called from scraper.py."""
    total_kim = len(KIM_PDFS)
    total_sid = len(SID_PDFS)
    total = total_kim + total_sid

    for i, (url, scheme) in enumerate(KIM_PDFS, 1):
        print(f"Extracting PDF {i}/{total}: {scheme} — {url.split('/')[-1]}")
        extract_and_save(url, scheme, is_sid=False)

    for i, (url, scheme) in enumerate(SID_PDFS, total_kim + 1):
        print(f"Extracting PDF {i}/{total}: {scheme} — {url.split('/')[-1]}")
        extract_and_save(url, scheme, is_sid=True)  # Fix 2: 50k-char limit for SID docs


if __name__ == "__main__":
    # Allow calling as: python pdf_extractor.py <pdf_url> <scheme_name>
    if len(sys.argv) == 3:
        pdf_url = sys.argv[1]
        scheme_name = sys.argv[2]
        extract_and_save(pdf_url, scheme_name)
    else:
        # Process all KIM + SID PDFs
        process_all_kim_sid()
