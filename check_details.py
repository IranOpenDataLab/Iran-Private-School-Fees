import requests
import re

r = requests.get('https://my.mosharekatha.ir/school-details/IR2O2O8O3Oab', timeout=30)
print('Status:', r.status_code)
print('Length:', len(r.text))
if r.text.strip().startswith('<'):
    print('HTML page')
    # Find any API endpoints
    for match in re.finditer(r'(https?://[^\s"<>]+|/core-api/[^\s"<>]+)', r.text):
        print(match.group())
else:
    print('API response:', r.text[:500])