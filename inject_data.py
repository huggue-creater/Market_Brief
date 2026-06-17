#!/usr/bin/env python3
"""
Inject search_data.json into index.html between placeholder markers.
Replaces:
    // %%SEARCH_DATA_START%%
    const SEARCH_DATA = null;
    // %%SEARCH_DATA_END%%
with:
    // %%SEARCH_DATA_START%%
    const SEARCH_DATA = {...actual data...};
    // %%SEARCH_DATA_END%%
"""
import json
import re
import sys
from pathlib import Path

SEARCH_JSON = Path("search_data.json")
INDEX_HTML  = Path("index.html")

MARKER_RE = re.compile(
    r"(// %%SEARCH_DATA_START%%\s*).*?(\s*// %%SEARCH_DATA_END%%)",
    re.DOTALL,
)

def main():
    if not SEARCH_JSON.exists():
        print("search_data.json not found — skipping inject")
        sys.exit(0)

    raw  = SEARCH_JSON.read_text(encoding="utf-8")

    # Validate JSON
    try:
        json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"search_data.json is invalid JSON: {e}")
        sys.exit(1)

    # Escape </script> sequences so the JSON doesn't break the HTML parser
    safe = raw.replace("</script>", "<\\/script>").replace("<!--", "<\\!--")

    html = INDEX_HTML.read_text(encoding="utf-8")
    replacement = rf"\g<1>const SEARCH_DATA = {safe};\g<2>"
    new_html, count = MARKER_RE.subn(replacement, html)

    if count == 0:
        print("ERROR: placeholder markers not found in index.html")
        sys.exit(1)

    INDEX_HTML.write_text(new_html, encoding="utf-8")
    print(f"Injected {len(safe):,} bytes into index.html ({count} replacement)")


if __name__ == "__main__":
    main()
