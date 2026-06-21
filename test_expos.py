#!/usr/bin/env python3
"""공급면적 API 탐색 v7
- 덕풍동 bjdongCd 자동 탐색
- getBrExposPubuseAreaInfo 올바른 코드로 재시도
- 망월동으로도 먼저 기준 확인
"""
import os, time
import requests
from xml.etree import ElementTree

KEY  = os.environ["DATA_GO_KR_KEY"]
HUB  = "http://apis.data.go.kr/1613000/BldRgstHubService"
TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

def xml_items(text):
    try:
        root = ElementTree.fromstring(text)
        items = root.findall(".//item")
        total = root.findtext(".//totalCount") or "0"
        code  = root.findtext(".//resultCode") or ""
        return items, total, code, root
    except:
        return [], "0", "??", None

def hub(ep, params, label=""):
    t0 = time.time()
    r = requests.get(f"{HUB}/{ep}", params={"serviceKey": KEY, "pageNo": 1, **params}, timeout=15)
    items, total, code, root = xml_items(r.text)
    print(f"  [{label or ep}] {time.time()-t0:.2f}s  HTTP {r.status_code}  code={code}  total={total}  parsed={len(items)}")
    if not items and r.status_code == 200:
        print(f"  raw: {r.text[:200]}")
    return items

# ─── STEP 0. 망월동(10900) + bun=1170 으로 기준선 확인 ────────────────────────
print("=" * 60)
print("STEP 0. 망원동(10900) getBrExposPubuseAreaInfo 기준 확인")
print("=" * 60)
items = hub("getBrExposPubuseAreaInfo", {
    "sigunguCd": "41450", "bjdongCd": "10900",
    "bun": "1170", "ji": "0000", "numOfRows": 50,
}, "망월동-1170")
if items:
    for i in items[:5]:
        d = {c.tag: (c.text or "").strip() for c in i}
        print(f"  {d}")

time.sleep(0.4)

# ─── STEP 1. 덕풍동 bjdongCd 탐색 ─────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 1. 덕풍동 bjdongCd 탐색 (getBrRecapTitleInfo)")
print("=" * 60)
# 하남시 법정동 코드 후보: 10400~12000 범위 시도
# 알려진: 망월동=10900 → 덕풍동은 인접 코드 중 하나
CANDIDATES = ["10700", "10800", "10600", "10500", "10300", "11000", "11100", "11200"]
dukpung_bjdong = None
for bjd in CANDIDATES:
    r = requests.get(f"{HUB}/getBrRecapTitleInfo", params={
        "serviceKey": KEY, "sigunguCd": "41450", "bjdongCd": bjd,
        "bun": "0823", "ji": "0000", "numOfRows": 3, "pageNo": 1
    }, timeout=15)
    items, total, code, _ = xml_items(r.text)
    if items:
        plat = items[0].findtext("platPlc") or ""
        print(f"  bjdong={bjd}  total={total}  platPlc={plat}")
        if "덕풍" in plat:
            dukpung_bjdong = bjd
            print(f"  *** 덕풍동 bjdong={bjd} 확인! ***")
    else:
        print(f"  bjdong={bjd}  total={total}  (결과없음)")
    time.sleep(0.25)

if not dukpung_bjdong:
    print("\n  → 후보 중 없음. bjdong 없이 전체 검색 시도")
    r = requests.get(f"{HUB}/getBrRecapTitleInfo", params={
        "serviceKey": KEY, "sigunguCd": "41450",
        "numOfRows": 100, "pageNo": 1
    }, timeout=15)
    items, total, code, _ = xml_items(r.text)
    print(f"  sigungu 전체 검색: total={total}  parsed={len(items)}")
    dongs = set()
    for i in items:
        p = i.findtext("platPlc") or ""
        bjd = i.findtext("bjdongCd") or ""
        for tok in p.split():
            if "동" in tok or "읍" in tok:
                dongs.add((bjd, tok))
    print(f"  발견된 동: {sorted(dongs)[:20]}")

time.sleep(0.4)

# ─── STEP 2. getBrExposPubuseAreaInfo — 올바른 bjdong으로 재시도 ─────────────
print("\n" + "=" * 60)
print("STEP 2. getBrExposPubuseAreaInfo (덕풍동 bjdong)")
print("=" * 60)
bjd = dukpung_bjdong or "10700"
print(f"  사용 bjdong={bjd}")

items = hub("getBrExposPubuseAreaInfo", {
    "sigunguCd": "41450", "bjdongCd": bjd,
    "bun": "0823", "ji": "0000", "numOfRows": 200,
}, f"ExposPubuseArea-{bjd}")

if items:
    print(f"\n  [필드 목록]: {[c.tag for c in items[0]]}")
    print(f"\n  [상위 20건]")
    for i in items[:20]:
        d = {c.tag: (c.text or "").strip() for c in i}
        print(f"  {d}")
else:
    # 여러 bjdong 후보 모두 시도
    print("  → 0건. 다른 bjdong 코드로도 시도")
    for bjd2 in ["10700", "10800", "10600", "10500", "11000"]:
        if bjd2 == bjd:
            continue
        items2 = hub("getBrExposPubuseAreaInfo", {
            "sigunguCd": "41450", "bjdongCd": bjd2,
            "bun": "0823", "ji": "0000", "numOfRows": 5,
        }, f"ExposPubuse-{bjd2}")
        if items2:
            print(f"  *** bjdong={bjd2} 로 결과 나옴! ***")
            for i in items2[:3]:
                print(f"  {{{', '.join(f'{c.tag}={c.text}' for c in i)}}}")
            break
        time.sleep(0.25)

time.sleep(0.4)

# ─── STEP 3. getBrFlrOulnInfo — 층별개요에서 전용면적 힌트 ──────────────────
print("\n" + "=" * 60)
print("STEP 3. getBrFlrOulnInfo (층별개요) — 호별 면적 조합 가능 여부")
print("=" * 60)
bjd_main = dukpung_bjdong or "10700"
items = hub("getBrFlrOulnInfo", {
    "sigunguCd": "41450", "bjdongCd": bjd_main,
    "bun": "0823", "ji": "0000", "numOfRows": 50,
}, f"FlrOuln-{bjd_main}")
if items:
    print(f"  필드: {[c.tag for c in items[0]]}")
    for i in items[:5]:
        d = {c.tag: (c.text or "").strip() for c in i}
        print(f"  {d}")

time.sleep(0.4)

# ─── STEP 4. 공동주택 가격공시 서비스 — 별도 면적 정보 확인 ───────────────────
print("\n" + "=" * 60)
print("STEP 4. 개별공동주택가격 서비스 (1611000)")
print("=" * 60)
# 개별공동주택가격 서비스: 국토부 1611000 계열
PRICE_URL = "http://apis.data.go.kr/1611000/nsdi/IndvCombHousingPriceService/wfsGetIndvCombHousingPriceAttr"
r = requests.get(PRICE_URL, params={
    "serviceKey": KEY,
    "pnu": "4145010700",
    "numOfRows": 10,
    "pageNo": 1,
}, timeout=15)
items, total, code, _ = xml_items(r.text)
print(f"  HTTP {r.status_code}  total={total}")
if r.status_code != 200:
    print(f"  응답: {r.text[:200]}")
elif items:
    for i in items[:2]:
        print(f"  {{{', '.join(f'{c.tag}={c.text}' for c in i)}}}")

print("\n=== 완료 ===")
