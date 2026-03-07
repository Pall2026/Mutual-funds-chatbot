import re

# PII Patterns as per ARCHITECTURE.md
PII_PATTERNS = {
    "PAN": r"[A-Z]{5}[0-9]{4}[A-Z]{1}",
    "Aadhaar": r"\d{12}",
    "Phone": r"[6-9]\d{9}",
    "Email": r"[^@]+@[^@]+\.[^@]+"
}

# Advice Refusal Keywords as per ARCHITECTURE.md (plus \b boundaries)
ADVICE_KEYWORDS = [
    r"\bshould i\b", r"\bshall i\b", r"\brecommend\b", r"\bbuy\b",
    r"\bsell\b", r"\binvest\b", r"\bbest fund\b", r"\bcompare\b",
    r"\breturns\b", r"\bperformance\b"
]

def check_pii(text: str) -> bool:
    """
    Returns True if PII is detected in the text.
    """
    for name, pattern in PII_PATTERNS.items():
        if re.search(pattern, text):
            return True
    return False

def check_advice(text: str) -> bool:
    """
    Returns True if the text looks like a request for investment advice.
    """
    text_lower = text.lower()
    for pattern in ADVICE_KEYWORDS:
        if re.search(pattern, text_lower):
            return True
    return False
