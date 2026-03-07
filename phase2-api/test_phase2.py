import pytest
from guardrails import check_pii, check_advice
from db import get_field_scraped_at
from rag import generate_answer
from unittest.mock import MagicMock, patch

# 1. Test PII Detection (PAN)
def test_pii_pan():
    assert check_pii("My PAN is ABCDE1234F") == True

# 2. Test PII Detection (Aadhaar)
def test_pii_aadhaar():
    assert check_pii("Aadhaar: 123412341234") == True

# 3. Test PII Detection (Phone)
def test_pii_phone():
    assert check_pii("Call me at 9876543210") == True

# 4. Test Advice Detection (Positive)
def test_advice_positive():
    assert check_advice("Should I invest in SBI Bluechip?") == True
    assert check_advice("recommend a fund") == True

# 5. Test Advice Detection (Negative)
def test_advice_negative():
    assert check_advice("What is the AUM of SBI Bluechip?") == False

# 6. Test DB Utility (Mocked)
@patch('psycopg2.connect')
def test_db_scraped_at(mock_connect):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchone.return_value = ("2026-03-07",)
    
    from db import get_field_scraped_at
    assert get_field_scraped_at("mock_id") == "2026-03-07"

# 7. Test RAG Answer Generation (Mocked)
@patch('rag.client.models.generate_content')
def test_generate_answer(mock_gen):
    mock_response = MagicMock()
    mock_response.text = "This is a fact."
    mock_gen.return_value = mock_response
    
    ans = generate_answer("Question", "Context")
    assert ans == "This is a fact."

# 8. Test RAG Refusal (Mocked)
@patch('rag.client.models.generate_content')
def test_generate_answer_refusal(mock_gen):
    mock_response = MagicMock()
    mock_response.text = "I could not find a reliable source for this."
    mock_gen.return_value = mock_response
    
    ans = generate_answer("Question", "Empty Context")
    assert "reliable source" in ans
