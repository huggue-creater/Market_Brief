#!/usr/bin/env python3
"""건축물대장 API 디버깅 테스트 v3"""
import os, time, urllib.parse
import requests
from xml.etree import ElementTree

TRADE_KEY = os.environ["DATA_GO_KR_KEY"]
BUILD_KEY = os.environ.get("BUILD_API_KEY", "")

print(f"  TRADE_KEY 마지막 8자: ...{TRADE_KEY[-8:]}")
print(f"  BUILD_KEY 마지막 8자: ...{BUILD_KEY[-8:] if BUILD_KEY else '(없음)'}")
print(f"  BUILD_KEY == TRADE_KEY: {BUILD_KEY == TRADE_KEY}")

BASE_HTTP  = "http://apis.data.go.kr/1613000/BldRgstService_v2"
BASE_HTTPS = "https://apis.data.go.kr/1613000/BldRgstService_v2"
APT_TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

SIGUNGU = "41450"
BJDONG  = "10900"

def call(url, params, label):
    t0 = time.time()
    r = requests.get(url, params=params, timeout=15)
    print(f"  [{label}] {time.time()-t0:.2f}s  HTTP {r.status_code}")
    print(f"  응답: {r.text[:300]}")
    return r

# ─── 실거래가로 bonbun/bubun 추출 ─────────────────────────────────────────────
print("\n=== STEP 1. 실거래가 샘플 ===")
r = requests.get(APT_TRADE_URL, params={
    "serviceKey": TRADE_KEY, "LAWD_CD": "41450",
    "DEAL_YMD": "202606", "numOfRows": 10, "pageNo": 1,
}, timeout=15)
root = ElementTree.fromstring(r.text)
trades = [
    {c.tag: (c.text or "").strip() for c in item}
    for item in root.findall(".//item")
    if (item.findtext("umdNm") or "").strip() == "망월동"
]
t = trades[0] if trades else {}
bonbun = t.get("bonbun", "1170").zfill(4)
bubun  = t.get("bubun",  "0000").zfill(4)
print(f"  샘플: {t.get('aptNm')}  bonbun={bonbun} bubun={bubun}")

# ─── 시도 1: http + bun/ji 있음 (기존 방식) ────────────────────────────────────
print("\n=== STEP 2. getBrRecapTitleInfo (bot.py 방식 - bun/ji 없음) ===")
call(f"{BASE_HTTP}/getBrRecapTitleInfo", {
    "serviceKey": BUILD_KEY or TRADE_KEY,
    "sigunguCd": SIGUNGU, "bjdongCd": BJDONG,
    "numOfRows": 5, "pageNo": 1,
}, "RecapTitle-nobun")

# ─── 시도 2: https ──────────────────────────────────────────────────────────────
print("\n=== STEP 3. getBrRecapTitleInfo (https) ===")
call(f"{BASE_HTTPS}/getBrRecapTitleInfo", {
    "serviceKey": BUILD_KEY or TRADE_KEY,
    "sigunguCd": SIGUNGU, "bjdongCd": BJDONG,
    "numOfRows": 5, "pageNo": 1,
}, "RecapTitle-https")

# ─── 시도 3: TRADE_KEY로 건축물대장 시도 ────────────────────────────────────────
print("\n=== STEP 4. getBrRecapTitleInfo (TRADE_KEY 사용) ===")
call(f"{BASE_HTTP}/getBrRecapTitleInfo", {
    "serviceKey": TRADE_KEY,
    "sigunguCd": SIGUNGU, "bjdongCd": BJDONG,
    "numOfRows": 5, "pageNo": 1,
}, "RecapTitle-tradekey")

# ─── 시도 4: 인코딩된 키 형태 ───────────────────────────────────────────────────
print("\n=== STEP 5. URL 직접 조합 (key 인코딩) ===")
key = BUILD_KEY or TRADE_KEY
encoded_key = urllib.parse.quote(key, safe='')
url = f"{BASE_HTTP}/getBrRecapTitleInfo?serviceKey={encoded_key}&sigunguCd={SIGUNGU}&bjdongCd={BJDONG}&numOfRows=5&pageNo=1"
t0 = time.time()
r = requests.get(url, timeout=15)
print(f"  [직접URL] {time.time()-t0:.2f}s  HTTP {r.status_code}")
print(f"  응답: {r.text[:300]}")

# ─── 시도 5: getBrExposInfo + bun/ji ────────────────────────────────────────────
print("\n=== STEP 6. getBrExposInfo (BUILD_KEY, bun/ji 포함) ===")
call(f"{BASE_HTTP}/getBrExposInfo", {
    "serviceKey": BUILD_KEY or TRADE_KEY,
    "sigunguCd": SIGUNGU, "bjdongCd": BJDONG,
    "bun": bonbun, "ji": bubun,
    "numOfRows": 100, "pageNo": 1,
}, "ExposInfo")

print("\n=== 완료 ===")
