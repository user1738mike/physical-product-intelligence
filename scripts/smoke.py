"""Probe running applications without third-party dependencies."""

import json
import re
from urllib.request import urlopen

for url, service in [
    ("http://127.0.0.1:8000/api/v1/health/live/", "backend"),
    ("http://127.0.0.1:8000/api/v1/health/ready/", "backend"),
    ("http://127.0.0.1:3000/health", "frontend"),
]:
    with urlopen(url, timeout=10) as response:
        assert response.status == 200, url
        assert response.headers.get("Cache-Control") == "no-store", url
        assert json.load(response) == {"status": "ok", "service": service}, url
    print(f"PASS {url}")

with urlopen("http://127.0.0.1:3000/", timeout=10) as response:
    html = response.read().decode()
    assert "Physical Product Intelligence Cloud" in html
    assert "Product records and packaging APIs are available." in html
    assert "Uploads and assessments are not yet available." in html
    stylesheets = re.findall(r'href="(/_next/static/[^"?]+\.css)', html)
    assert stylesheets, "Landing page stylesheet missing"
for stylesheet in stylesheets:
    with urlopen(f"http://127.0.0.1:3000{stylesheet}", timeout=10) as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "text/css"
print("PASS landing page")
