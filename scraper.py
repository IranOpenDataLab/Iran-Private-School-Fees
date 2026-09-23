import requests
import json
import base64
import hashlib
import time
from Crypto.Cipher import AES
from typing import Dict, List, Any, Optional

# ============================================================
# CONFIGURATION
# ============================================================

PORTAL_URL = "https://portal.mosharekatha.ir/core-api/v1/data-provider/get-data-source"
MY_PORTAL_URL = "https://my.mosharekatha.ir/core-api/v1/data-provider/get-data-source"

HEADERS_PORTAL = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Origin': 'https://portal.mosharekatha.ir',
    'Referer': 'https://portal.mosharekatha.ir/dashboard/school-tuition',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

HEADERS_MY_PORTAL = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'Origin': 'https://my.mosharekatha.ir',
    'Referer': 'https://my.mosharekatha.ir/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Encryption keys
# When no `client-id` header is sent, server uses the JS fallback key below.
# (localStorage pages-client-id overrides it per client, but we don't send that header.)
PORTAL_KEY = b'79f39sg5%90ni9hwp%ligb4vl6%uw5by2ae%yxqup1ql'

# ============================================================
# DECRYPTION
# ============================================================

def evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16):
    """OpenSSL EVP_BytesToKey with MD5 (CryptoJS compatible)"""
    d = b''
    d_i = b''
    while len(d) < key_len + iv_len:
        m = hashlib.md5()
        if d_i:
            m.update(d_i)
        m.update(password)
        m.update(salt)
        d_i = m.digest()
        d += d_i
    return d[:key_len], d[key_len:key_len+iv_len]

def decrypt_token(token: str, password: bytes) -> dict:
    """Decrypt the token response from the API"""
    data = base64.b64decode(token)
    if data[:8] != b'Salted__':
        raise ValueError("Not a valid OpenSSL salted format")
    salt = data[8:16]
    ciphertext = data[16:]
    
    key, iv = evp_bytes_to_key(password, salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(ciphertext)
    
    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]
    
    text = decrypted.decode('utf-8')
    # CryptoJS side does: JSON.parse(JSON.parse(decrypt(token)))
    value = json.loads(text)
    if isinstance(value, str):
        value = json.loads(value)
    return value

# Persistent sessions (connection reuse = much faster, no TLS handshake per request)
_SESSIONS: Dict[str, requests.Session] = {}

def _session(url: str) -> requests.Session:
    s = _SESSIONS.get(url)
    if s is None:
        s = requests.Session()
        _SESSIONS[url] = s
    return s

def make_request(url: str, payload: dict, headers: dict, password: bytes) -> dict:
    """Make API request and decrypt response (with small retry)"""
    last_err = None
    for attempt in range(3):
        try:
            r = _session(url).post(url, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            resp = r.json()
            token = resp.get('token')
            if not token:
                raise ValueError(f"No token in response: {resp}")
            result = decrypt_token(token, password)
            msg = (result.get('serverMessage') or {}).get('type')
            if msg == 'error':
                raise ValueError(f"API error: {result.get('serverMessage')}")
            return result
        except ValueError:
            raise  # deterministic API error, no point retrying
        except Exception as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    raise last_err

# ============================================================
# API FUNCTIONS
# ============================================================

def get_provinces() -> List[dict]:
    """Get list of all provinces"""
    payload = {
        'serviceId': 'portal.mosharekatha.ir',
        'key': 'medungo-explore/get/sub-organs',
        'params': {'organPath': 'IR2O2'}
    }
    result = make_request(PORTAL_URL, payload, HEADERS_PORTAL, PORTAL_KEY)
    # The result has 'organs' array
    return result.get('organs', [])

def get_districts(province_key: str) -> List[dict]:
    """Get districts for a province"""
    payload = {
        'serviceId': 'portal.mosharekatha.ir',
        'key': 'medungo-explore/get/sub-organs',
        'params': {'organPath': province_key}
    }
    result = make_request(PORTAL_URL, payload, HEADERS_PORTAL, PORTAL_KEY)
    return result.get('organs', [])

def get_schools(district_key: str, gender: str = '1', stage_ids: List[str] = None, year: str = '1405', page: int = 1, limit: int = 50, school_name: str = '') -> dict:
    """Get schools for a district with pagination (params verified from real UI request)"""
    if stage_ids is None:
        stage_ids = ['2', '3', '16', '17']
    
    filters = {}
    if school_name:
        filters['school_name'] = school_name

    payload = {
        'serviceId': 'portal.mosharekatha.ir',
        'key': 'mosharekatha-portal/load/school-tuition-inquiry',
        'params': {
            'regionPath': district_key,
            'gender': gender,
            'stage_id': stage_ids,
            'year': year,
            'limit': limit,
            'page': page,
            'filters': filters,
        }
    }
    result = make_request(PORTAL_URL, payload, HEADERS_PORTAL, PORTAL_KEY)
    return result

def get_school_detail(school_path: str) -> dict:
    """Get school detail from my.mosharekatha.ir"""
    payload = {
        'serviceId': 'my.mosharekatha.ir',
        'key': 'my-mosharekatha/school-panel/school-detail/load',
        'params': {'school_path': school_path}
    }
    result = make_request(MY_PORTAL_URL, payload, HEADERS_MY_PORTAL, PORTAL_KEY)
    return result

def get_school_licenses(school_path: str) -> dict:
    """Get school licenses from my.mosharekatha.ir"""
    payload = {
        'serviceId': 'my.mosharekatha.ir',
        'key': 'my-mosharekatha/school-panel/school-licenses/load',
        'params': {'school_path': school_path}
    }
    result = make_request(MY_PORTAL_URL, payload, HEADERS_MY_PORTAL, PORTAL_KEY)
    return result

def get_tuition_history(school_path: str) -> dict:
    """Get school tuition history from my.mosharekatha.ir"""
    payload = {
        'serviceId': 'my.mosharekatha.ir',
        'key': 'my-mosharekatha/school-panel/school-tuition-history/load',
        'params': {'school_path': school_path}
    }
    result = make_request(MY_PORTAL_URL, payload, HEADERS_MY_PORTAL, PORTAL_KEY)
    return result

# NOTE: the full multi-phase scraper lives in run_scraper.py
# (phases: 1 = school lists, 2 = per-school details, 3 = export)