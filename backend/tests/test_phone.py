from app.services import normalize_phone
import pytest

def test_normalize_phone_keeps_country_prefix():
    assert normalize_phone('+91 98765 43210') == '+919876543210'

def test_rejects_short_phone():
    with pytest.raises(ValueError):
        normalize_phone('12345')
