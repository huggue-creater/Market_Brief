#!/usr/bin/env python3
"""건축물대장 API - URL 패턴 전수 탐색 v4"""
import os, time
import requests
from xml.etree import ElementTree

KEY = os.environ["DATA_GO_KR_KEY"]
print(f"  KEY 마지막 8자: ...{KEY[-8:]}")

APT_TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

SIGUNGU = "41450"
BJDONG  = "10900"

def call(url, params, label):
    t0 = time.time()
    try:
        r = requests.get(url, params=params, timeout=10)
        print(f"  [{label}] {time.time()-t0:.2f}s  HTTP {r.status_code}  응답: {r.text[:200]}")
        return r
    except Exception as e:
        print(f"  [{label}] 오류: {e}")
        return None

base_params = {"serviceKey": KEY, "sigunguCd": SIGUNGU, "bjdongCd": BJDONG, "numOfRows": 3, "pageNo": 1}

# ─── 다양한 base URL 시도 ──────────────────────────────────────────────────────
print("\n=== 건축물대장 URL 패턴 탐색 ===")

candidates = [
    ("http://apis.data.go.kr/1613000/BldRgstService_v2/getBrRecapTitleInfo",   "v2-http"),
    ("https://apis.data.go.kr/1613000/BldRgstService_v2/getBrRecapTitleInfo",  "v2-https"),
    ("http://apis.data.go.kr/1613000/BldRgstService/getBrRecapTitleInfo",      "v1-http"),
    ("https://apis.data.go.kr/1613000/BldRgstService/getBrRecapTitleInfo",     "v1-https"),
    ("http://apis.data.go.kr/1611000/BldRgstService_v2/getBrRecapTitleInfo",   "1611000-v2"),
    ("http://apis.data.go.kr/1611000/BldRgstService/getBrRecapTitleInfo",      "1611000-v1"),
    ("http://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo",   "Hub"),
]

for url, label in candidates:
    call(url, base_params, label)
    time.sleep(0.3)

# ─── 공공데이터포털 에러코드 확인용 (파라미터 일부러 누락) ─────────────────────────
print("\n=== 에러 응답 상세 확인 (파라미터 누락) ===")
r = requests.get(
    "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrRecapTitleInfo",
    params={"serviceKey": KEY},
    timeout=10
)
print(f"  파라미터 누락 응답: {r.text[:400]}")

# ─── 실거래가 API는 여전히 정상인지 확인 ──────────────────────────────────────────
print("\n=== 실거래가 API 정상 확인 ===")
r = requests.get(APT_TRADE_URL, params={
    "serviceKey": KEY, "LAWD_CD": "41450",
    "DEAL_YMD": "202606", "numOfRows": 1, "pageNo": 1,
}, timeout=10)
root = ElementTree.fromstring(r.text)
print(f"  resultCode: {root.findtext('.//resultCode')}  totalCount: {root.findtext('.//totalCount')}")

print("\n=== 완료 ===")
