#!/usr/bin/env python3
"""
건축물대장 getBrExposInfo (전유공유부 면적) API 테스트
- 공급면적 필드가 있는지 확인
- 응답 속도 측정
- 전용면적 기준 매칭 정확도 확인
"""
import os, time, json
import requests
from xml.etree import ElementTree

KEY = os.environ["DATA_GO_KR_KEY"]

APT_TRADE_URL  = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
EXPOS_URL      = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrExposInfo"
FLR_URL        = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrFlrOulnInfo"

SIGUNGU = "41450"   # 하남시
BJDONG  = "10900"   # 망월동

def get(url, params, label=""):
    t0 = time.time()
    r = requests.get(url, params=params, timeout=15)
    elapsed = time.time() - t0
    print(f"  [{label}] {elapsed:.2f}s  HTTP {r.status_code}")
    return r, elapsed

def parse_jibun(s):
    parts = s.strip().split("-")
    bun = parts[0].strip().zfill(4)
    ji  = parts[1].strip().zfill(4) if len(parts) > 1 else "0000"
    return bun, ji

# ─── 1. 실거래가 API로 망월동 최근 거래 수집 ─────────────────────────────────
print("\n═══ STEP 1. 실거래가 API (망월동 202606) ════════════════")
r, _ = get(APT_TRADE_URL, {
    "serviceKey": KEY, "LAWD_CD": "41450",
    "DEAL_YMD": "202606", "numOfRows": 50, "pageNo": 1,
}, "실거래가")

root   = ElementTree.fromstring(r.text)
trades = []
for item in root.findall(".//item"):
    d = {c.tag: (c.text or "").strip() for c in item}
    if d.get("umdNm", "").strip() == "망월동" and d.get("jibun", "").strip():
        trades.append(d)

print(f"  망월동 거래: {len(trades)}건")
print(f"  실거래가 API 필드: {list(trades[0].keys()) if trades else '없음'}")

# 고유 (apt, jibun) 3개 추출
seen, samples = set(), []
for t in trades:
    key = (t["aptNm"], t["jibun"].strip())
    if key not in seen:
        seen.add(key); samples.append(t)
    if len(samples) >= 3:
        break

print(f"\n  테스트 샘플:")
for t in samples:
    print(f"    {t['aptNm']:30s}  jibun={t['jibun']:10s}  전용={t['excluUseAr']}㎡")

# ─── 2. getBrExposInfo 전유공유부 면적 테스트 ────────────────────────────────
print("\n═══ STEP 2. getBrExposInfo (전유공유부 면적) ════════════")

total_time = 0
for t in samples:
    apt    = t["aptNm"]
    exclu  = t["excluUseAr"]
    bun, ji = parse_jibun(t["jibun"])
    print(f"\n  ▶ {apt}  전용={exclu}㎡  (bun={bun}, ji={ji})")

    r, elapsed = get(EXPOS_URL, {
        "serviceKey": KEY,
        "sigunguCd":  SIGUNGU,
        "bjdongCd":   BJDONG,
        "bun": bun, "ji": ji,
        "numOfRows": 200, "pageNo": 1,
    }, "ExposInfo")
    total_time += elapsed

    root  = ElementTree.fromstring(r.text)
    items = root.findall(".//item")
    total_cnt = root.findtext(".//totalCount") or "0"
    print(f"  totalCount={total_cnt}, 파싱={len(items)}건")

    if not items:
        print(f"  결과 없음. 응답 일부: {r.text[:300]}")
        continue

    # 전체 필드명 출력 (첫 항목)
    first = {c.tag: (c.text or "").strip() for c in items[0]}
    print(f"  필드 목록: {list(first.keys())}")

    # 전용면적 매칭 시도
    matched = [
        {c.tag: (c.text or "").strip() for c in item}
        for item in items
        if (item.findtext("excluUseAr") or "").strip() == exclu
    ]
    print(f"  전용={exclu}㎡ 매칭: {len(matched)}건")
    for m in matched[:2]:
        area_fields = {k: v for k, v in m.items() if "ar" in k.lower() or "area" in k.lower() or "Ar" in k}
        print(f"    면적 관련 필드: {area_fields}")
        print(f"    전체: {m}")

    # 전체 excluUseAr 분포 확인
    all_exclu = sorted(set(
        (item.findtext("excluUseAr") or "").strip()
        for item in items
    ))
    print(f"  전체 전용면적 값: {all_exclu[:10]}")

    time.sleep(0.5)

print(f"\n  평균 응답시간: {total_time/len(samples):.2f}s / 호출당")

# ─── 3. getBrFlrOulnInfo 층별개요 비교 ──────────────────────────────────────
print("\n═══ STEP 3. getBrFlrOulnInfo (층별개요) 비교 ═══════════")

t = samples[0]
bun, ji = parse_jibun(t["jibun"])
print(f"  ▶ {t['aptNm']}  (bun={bun}, ji={ji})")

r, _ = get(FLR_URL, {
    "serviceKey": KEY,
    "sigunguCd":  SIGUNGU,
    "bjdongCd":   BJDONG,
    "bun": bun, "ji": ji,
    "numOfRows": 50, "pageNo": 1,
}, "FlrOuln")

root  = ElementTree.fromstring(r.text)
items = root.findall(".//item")
print(f"  건수: {root.findtext('.//totalCount') or 0}")
if items:
    first = {c.tag: (c.text or "").strip() for c in items[0]}
    print(f"  필드 목록: {list(first.keys())}")
    print(f"  첫 항목: {first}")

print("\n═══ 테스트 완료 ════════════════════════════════════════")
