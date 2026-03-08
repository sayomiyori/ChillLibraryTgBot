# -*- coding: utf-8 -*-
import re
from pathlib import Path
path = Path(__file__).resolve().parent.parent / "debug_mybook.html"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()
count = 0
for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>', text):
    href = m.group(1)
    if "search" in href or "favicon" in href or "next" in href or "static" in href:
        continue
    if "/book" in href or "/b/" in href or (href.startswith("/") and len(href) > 10):
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 150)
        snippet = text[start:end]
        snippet = re.sub(r"><", ">\n<", snippet)
        print("---LINK---")
        print(snippet[:600])
        print()
        count += 1
        if count >= 3:
            break
