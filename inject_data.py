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
NAVER_JSON  = Path("naver_events.json")
INDEX_HTML  = Path("index.html")

MARKER_RE = re.compile(
    r"(// %%SEARCH_DATA_START%%\s*).*?(\s*// %%SEARCH_DATA_END%%)",
    re.DOTALL,
)
NAVER_MARKER_RE = re.compile(
    r"(// %%NAVER_DATA_START%%\s*).*?(\s*// %%NAVER_DATA_END%%)",
    re.DOTALL,
)


def _safe(raw: str) -> str:
    return raw.replace("</script>", "<\\/script>").replace("<!--", "<\\!--")

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
    safe = _safe(raw)

    html = INDEX_HTML.read_text(encoding="utf-8")
    replacement = rf"\g<1>const SEARCH_DATA = {safe};\g<2>"
    new_html, count = MARKER_RE.subn(replacement, html)

    if count == 0:
        print("ERROR: placeholder markers not found in index.html")
        sys.exit(1)

    # 네이버 매물 이벤트 주입 (마커가 있을 때만 — 대시보드 탭 추가 후 활성화)
    n_count = 0
    if NAVER_JSON.exists():
        n_raw = NAVER_JSON.read_text(encoding="utf-8")
        try:
            json.loads(n_raw)
            n_safe = _safe(n_raw)
            new_html, n_count = NAVER_MARKER_RE.subn(
                rf"\g<1>const NAVER_DATA = {n_safe};\g<2>", new_html)
        except json.JSONDecodeError as e:
            print(f"naver_events.json invalid JSON: {e} — skipping naver inject")

    INDEX_HTML.write_text(new_html, encoding="utf-8")
    msg = f"Injected {len(safe):,} bytes SEARCH_DATA ({count})"
    if n_count:
        msg += f" + NAVER_DATA ({n_count})"
    elif NAVER_JSON.exists():
        msg += " · NAVER marker 없음(대시보드 탭 미도입) — 건너뜀"
    print(msg)


if __name__ == "__main__":
    main()
