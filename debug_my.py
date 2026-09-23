# -*- coding: utf-8 -*-
import json, base64, hashlib, requests
from Crypto.Cipher import AES
from scraper import evp_bytes_to_key, MY_PORTAL_KEY, PORTAL_KEY, HEADERS_MY_PORTAL, MY_PORTAL_URL

payload = {
    'serviceId': 'my.mosharekatha.ir',
    'key': 'my-mosharekatha/school-panel/school-detail/load',
    'params': {'school_path': 'IR2O2O8O3Oab'}
}
r = requests.post(MY_PORTAL_URL, json=payload, headers=HEADERS_MY_PORTAL, timeout=60)
print('status', r.status_code)
print('set-cookie:', r.headers.get('Set-Cookie'))
print('resp header client-id:', r.headers.get('client-id'))
token = r.json().get('token')
data = base64.b64decode(token)
salt, ct = data[8:16], data[16:]

candidates = {
    'my_localstorage': MY_PORTAL_KEY,
    'fallback': b'79f39sg5%90ni9hwp%ligb4vl6%uw5by2ae%yxqup1ql',
    'raw_cookie_guess': None,
}

# try decrypt with each
for name, pw in candidates.items():
    if pw is None:
        continue
    try:
        key, iv = evp_bytes_to_key(pw, salt)
        pt = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
        pad = pt[-1]
        if 1 <= pad <= 16:
            pt = pt[:-pad]
        text = pt.decode('utf-8')
        print(name, 'OK ->', text[:300])
    except Exception as e:
        print(name, 'FAIL', e)

# Also try: fetch with cookie from a homepage visit first
s = requests.Session()
s.headers.update(HEADERS_MY_PORTAL)
h = s.get('https://my.mosharekatha.ir/school-details/IR2O2O8O3Oab', timeout=60)
print('cookies after GET:', dict(s.cookies))
print('pages-client-id cookie:', s.cookies.get('pages-client-id'))
cid = s.cookies.get('pages-client-id')
if cid:
    pw = '%'.join(sorted(cid.split('-'))).encode()
    print('derived key:', pw)
    r2 = s.post(MY_PORTAL_URL, json=payload, timeout=60)
    data = base64.b64decode(r2.json()['token'])
    key, iv = evp_bytes_to_key(pw, data[8:16])
    pt = AES.new(key, AES.MODE_CBC, iv).decrypt(data[16:])
    pad = pt[-1]
    if 1 <= pad <= 16:
        pt = pt[:-pad]
    print('cookie-key decrypt ->', pt.decode('utf-8')[:300])
