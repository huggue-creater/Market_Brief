#!/usr/bin/env python3
"""건축물대장 BldRgstHubService - 공급면적 필드 확인 v5"""
import os, time
import requests
from xml.etree import ElementTree

KEY = os.environ["DATA_GO_KR_KEY"]
BASE = "http://apis.data.go.kr/1613000/BldRgstHubService"
APT_TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

SIGUNGU = "41450"
BJDONG  = "10900"

def call(url, params, label):
    t0 = time.time()
    r = requests.get(url, params=params, timeout=15)
    elapsed = time.time() - t0
    print(f"\n  [{label}] {elapsed:.2f}s  HTTP {r.status_code}")
    if r.status_code == 200:
        try:
            root = ElementTree.fromstring(r.text)
            items = root.findall(".//item")
            total = root.findtext(".//totalCount") or "0"
            print(f"  totalCount={total}, 파싱={len(items)}건")
            if items:
                first = {c.tag: (c.text or "").strip() for c in items[0]}
                print(f"  전체 필드: {list(first.keys())}")
                area_fields = {k: v for k, v in first.items()
                               if any(x in k for x in ["Ar","ar","area","Area","plat","Plat"])}
                print(f"  면적 관련: {area_fields}")
                return items
        except Exception as e:
            print(f"  파싱오류: {e}  응답: {r.text[:200]}")
    else:
        print(f"  응답: {r.text[:200]}")
    return []

# ─── 실거래가에서 bonbun/bubun 추출 ───────────────────────────────────────────
r = requests.get(APT_TRADE_URL, params={
    "serviceKey": KEY, "LAWD_CD": "41450",
    "DEAL_YMD": "202606", "numOfRows": 20, "pageNo": 1,
}, timeout=15)
root = ElementTree.fromstring(r.text)
trades = [
    {c.tag: (c.text or "").strip() for c in item}
    for item in root.findall(".//item")
    if (item.findtext("umdNm") or "").strip() == "망월동"
]
seen, samples = set(), []
for t in trades:
    k = (t.get("aptNm",""), t.get("bonbun",""))
    if k not in seen and t.get("bonbun",""):
        seen.add(k); samples.append(t)
    if len(samples) >= 3: break

print("샘플:")
for t in samples:
    print(f"  {t['aptNm']:35s} bonbun={t['bonbun']} bubun={t['bubun']} 전용={t['excluUseAr']}㎡")

# ─── Hub 엔드포인트 전수 테스트 ────────────────────────────────────────────────
t = samples[0]
bonbun = t["bonbun"].zfill(4)
bubun  = t["bubun"].zfill(4)
exclu  = t["excluUseAr"]
apt    = t["aptNm"]

print(f"\n=== [{apt}] bun={bonbun} ji={bubun} 전용={exclu}㎡ ===")

endpoints = [
    ("getBrRecapTitleInfo", {"sigunguCd": SIGUNGU, "bjdongCd": BJDONG, "numOfRows": 5}),
    ("getBrTitleInfo",      {"sigunguCd": SIGUNGU, "bjdongCd": BJDONG, "bun": bonbun, "ji": bubun, "numOfRows": 50}),
    ("getBrFlrOulnInfo",    {"sigunguCd": SIGUNGU, "bjdongCd": BJDONG, "bun": bonbun, "ji": bubun, "numOfRows": 100}),
    ("getBrExposInfo",      {"sigunguCd": SIGUNGU, "bjdongCd": BJDONG, "bun": bonbun, "ji": bubun, "numOfRows": 200}),
]

for ep, params in endpoints:
    params["serviceKey"] = KEY
    params["pageNo"] = 1
    items = call(f"{BASE}/{ep}", params, ep)

    if ep == "getBrExposInfo" and items:
        print(f"\n  [getBrExposInfo 상세 - 전유/공유 분류]")
        for item in items[:15]:
            d = {c.tag: (c.text or "").strip() for c in item}
            print(f"    구분={d.get('exposPubuseGbCdNm','?'):8s}  "
                  f"면적={d.get('area','?'):10s}  "
                  f"전용={d.get('excluUseAr','?'):10s}  "
                  f"etcPurps={d.get('etcPurps','?')}")
        print(f"\n  [전용 {exclu}㎡ 매칭 항목]")
        matched = [
            {c.tag: (c.text or "").strip() for c in item}
            for item in items
            if (item.findtext("excluUseAr") or "").strip() == exclu
        ]
        print(f"  매칭 {len(matched)}건:")
        for m in matched[:5]:
            print(f"    {m}")

    time.sleep(0.4)

print("\n=== 완료 ===")
