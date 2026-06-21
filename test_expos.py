#!/usr/bin/env python3
"""
건축물대장 getBrExposInfo (전유공유부 면적) API 테스트 v2
- bonbun/bubun 필드 직접 사용
- 500 응답 본문 출력
- 여러 엔드포인트 비교
"""
import os, time
import requests
from xml.etree import ElementTree

KEY = os.environ["DATA_GO_KR_KEY"]

APT_TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
BASE = "http://apis.data.go.kr/1613000/BldRgstService_v2"

SIGUNGU = "41450"
BJDONG  = "10900"  # 망월동

def get(url, params, label=""):
    t0 = time.time()
    r = requests.get(url, params=params, timeout=15)
    elapsed = time.time() - t0
    print(f"  [{label}] {elapsed:.2f}s  HTTP {r.status_code}")
    return r, elapsed

# ─── STEP 1. 실거래가 API ─────────────────────────────────────────────────────
print("\n═══ STEP 1. 실거래가 API (망월동 202606) ════════════════")
r, _ = get(APT_TRADE_URL, {
    "serviceKey": KEY, "LAWD_CD": "41450",
    "DEAL_YMD": "202606", "numOfRows": 50, "pageNo": 1,
}, "실거래가")

root = ElementTree.fromstring(r.text)
trades = [
    {c.tag: (c.text or "").strip() for c in item}
    for item in root.findall(".//item")
    if (item.findtext("umdNm") or "").strip() == "망월동"
]
print(f"  망월동: {len(trades)}건")

# 고유 (apt, bonbun, bubun) 샘플 3개
seen, samples = set(), []
for t in trades:
    key = (t.get("aptNm",""), t.get("bonbun",""), t.get("bubun",""))
    if key not in seen and t.get("bonbun",""):
        seen.add(key); samples.append(t)
    if len(samples) >= 3:
        break

print(f"\n  샘플 (bonbun/bubun 직접 사용):")
for t in samples:
    print(f"    {t.get('aptNm'):35s}  bonbun={t.get('bonbun'):6s} bubun={t.get('bubun'):4s}  전용={t.get('excluUseAr')}㎡")

# ─── STEP 2. 여러 엔드포인트 시도 ────────────────────────────────────────────
endpoints = [
    ("getBrExposInfo",     "전유공유부 면적"),
    ("getBrFlrOulnInfo",   "층별개요"),
    ("getBrTitleInfo",     "표제부 상세"),
    ("getBrRecapTitleInfo","표제부(기존)"),
]

t = samples[0]
bonbun = t.get("bonbun", "").zfill(4)
bubun  = t.get("bubun",  "").zfill(4)
exclu  = t.get("excluUseAr", "")
apt    = t.get("aptNm", "")

print(f"\n═══ STEP 2. 엔드포인트별 테스트 [{apt}] bun={bonbun} ji={bubun} ════")

for ep, label in endpoints:
    print(f"\n  ── {label} ({ep}) ──")
    r, elapsed = get(f"{BASE}/{ep}", {
        "serviceKey": KEY,
        "sigunguCd":  SIGUNGU,
        "bjdongCd":   BJDONG,
        "bun":        bonbun,
        "ji":         bubun,
        "numOfRows":  200,
        "pageNo":     1,
    }, ep)

    print(f"  응답 앞 500자: {r.text[:500]}")

    if r.status_code == 200:
        try:
            root = ElementTree.fromstring(r.text)
            items = root.findall(".//item")
            total = root.findtext(".//totalCount") or "0"
            print(f"  totalCount={total}, 파싱={len(items)}건")
            if items:
                first = {c.tag: (c.text or "").strip() for c in items[0]}
                print(f"  필드: {list(first.keys())}")
                # 면적 관련 필드
                area_fields = {k: v for k, v in first.items() if any(x in k.lower() for x in ["ar","area","area","플"])}
                print(f"  면적 필드: {area_fields}")

                # getBrExposInfo: 전유/공유 구분 출력
                if ep == "getBrExposInfo":
                    print(f"\n  [전유/공유 분류]")
                    for item in items[:10]:
                        d = {c.tag: (c.text or "").strip() for c in item}
                        print(f"    구분={d.get('exposPubuseGbCdNm',d.get('mainAtchGbCdNm','?')):10s}  "
                              f"면적={d.get('area',d.get('excluUseAr','?')):10s}  "
                              f"전체: {d}")
        except Exception as e:
            print(f"  XML 파싱 오류: {e}")

    time.sleep(0.5)

# ─── STEP 3. sigunguCd+bjdongCd만으로도 시도 (bun/ji 없이) ──────────────────
print(f"\n═══ STEP 3. getBrExposInfo (bun/ji 없이, dong 전체) ════")
r, elapsed = get(f"{BASE}/getBrExposInfo", {
    "serviceKey": KEY,
    "sigunguCd":  SIGUNGU,
    "bjdongCd":   BJDONG,
    "numOfRows":  10,
    "pageNo":     1,
}, "ExposInfo-nodong")
print(f"  응답: {r.text[:600]}")
if r.status_code == 200:
    try:
        root = ElementTree.fromstring(r.text)
        items = root.findall(".//item")
        if items:
            first = {c.tag: (c.text or "").strip() for c in items[0]}
            print(f"  필드: {list(first.keys())}")
    except: pass

print("\n═══ 완료 ════════════════════════════════════════════════")
