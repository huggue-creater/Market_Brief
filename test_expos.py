#!/usr/bin/env python3
"""상현동 풍산아파트 공급면적 기준 평형 계산 테스트"""
import os, time
import requests
from xml.etree import ElementTree

KEY  = os.environ["DATA_GO_KR_KEY"]
HUB  = "http://apis.data.go.kr/1613000/BldRgstHubService"
TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

def xml_items(text):
    try:
        root = ElementTree.fromstring(text)
        return root.findall(".//item")
    except:
        return []

# ─── 1. 상현동 풍산아파트 bonbun 확인 ─────────────────────────────────────────
print("=== STEP 1. 상현동 풍산아파트 bonbun/전용면적 확인 ===")
bonbuns = {}
for ym in ["202606", "202605", "202604", "202603", "202602", "202601",
           "202512", "202511", "202510", "202509"]:
    r = requests.get(TRADE_URL, params={
        "serviceKey": KEY, "LAWD_CD": "41465",
        "DEAL_YMD": ym, "numOfRows": 100, "pageNo": 1,
    }, timeout=15)
    for item in xml_items(r.text):
        apt   = (item.findtext("aptNm")      or "").strip()
        umd   = (item.findtext("umdNm")      or "").strip()
        exclu = (item.findtext("excluUseAr") or "").strip()
        bun   = (item.findtext("bonbun")     or "").strip()
        ji    = (item.findtext("bubun")      or "").strip()
        if "풍산" in apt and umd == "상현동":
            key = (bun, ji)
            if key not in bonbuns:
                bonbuns[key] = {"apt": apt, "bonbun": bun, "bubun": ji, "areas": set()}
            bonbuns[key]["areas"].add(exclu)
    if bonbuns:
        break
    time.sleep(0.2)

if not bonbuns:
    print("  최근 거래 없음 — 더 많은 월 검색")
    for ym in ["202508","202507","202506","202505","202504","202503"]:
        r = requests.get(TRADE_URL, params={
            "serviceKey": KEY, "LAWD_CD": "41465",
            "DEAL_YMD": ym, "numOfRows": 100, "pageNo": 1,
        }, timeout=15)
        for item in xml_items(r.text):
            apt   = (item.findtext("aptNm")      or "").strip()
            umd   = (item.findtext("umdNm")      or "").strip()
            exclu = (item.findtext("excluUseAr") or "").strip()
            bun   = (item.findtext("bonbun")     or "").strip()
            ji    = (item.findtext("bubun")      or "").strip()
            if "풍산" in apt and umd == "상현동":
                key = (bun, ji)
                if key not in bonbuns:
                    bonbuns[key] = {"apt": apt, "bonbun": bun, "bubun": ji, "areas": set()}
                bonbuns[key]["areas"].add(exclu)
        if bonbuns:
            break
        time.sleep(0.2)

for k, v in bonbuns.items():
    print(f"  {v['apt']}  bonbun={v['bonbun']} bubun={v['bubun']}  전용면적: {sorted(v['areas'])}")

assert bonbuns, "풍산아파트 데이터를 찾지 못했습니다"
main = list(bonbuns.values())[0]
BUN = main["bonbun"].zfill(4)
JI  = main["bubun"].zfill(4)
print(f"\n  사용: bonbun={BUN} ji={JI}")

# ─── 2. 상현동 bjdongCd 탐색 ──────────────────────────────────────────────────
print("\n=== STEP 2. 상현동 bjdongCd 탐색 ===")
SANGHYEON_BJDONG = None
for bjd in ["11000","10700","10800","10900","10600","10500","11100","11200","10400","10300","10200","10100"]:
    r = requests.get(f"{HUB}/getBrRecapTitleInfo", params={
        "serviceKey": KEY, "sigunguCd": "41465", "bjdongCd": bjd,
        "bun": BUN, "ji": JI, "numOfRows": 1, "pageNo": 1,
    }, timeout=15)
    items = xml_items(r.text)
    if items:
        plat = items[0].findtext("platPlc") or ""
        print(f"  bjdong={bjd}  platPlc={plat}  ← 발견!")
        SANGHYEON_BJDONG = bjd
        break
    time.sleep(0.2)

assert SANGHYEON_BJDONG, "bjdongCd를 찾지 못했습니다"

# ─── 3. getBrExposPubuseAreaInfo — 전체 호 면적 조회 ────────────────────────
print(f"\n=== STEP 3. getBrExposPubuseAreaInfo (bjdong={SANGHYEON_BJDONG}) ===")

all_items = []
page = 1
while True:
    r = requests.get(f"{HUB}/getBrExposPubuseAreaInfo", params={
        "serviceKey": KEY,
        "sigunguCd": "41465",
        "bjdongCd":  SANGHYEON_BJDONG,
        "bun": BUN, "ji": JI,
        "numOfRows": 1000, "pageNo": page,
    }, timeout=15)
    items = xml_items(r.text)
    all_items.extend(items)
    try:
        root = ElementTree.fromstring(r.text)
        total = int(root.findtext(".//totalCount") or 0)
    except:
        total = 0
    print(f"  page={page}  total={total}  parsed so far={len(all_items)}")
    if len(all_items) >= total or not items:
        break
    page += 1
    time.sleep(0.3)

# ─── 4. 평형별 공급면적 계산 ────────────────────────────────────────────────────
print(f"\n=== STEP 4. 평형별 공급면적 계산 ===")
# ho별로 grouping: (dongNm, hoNm) → {전유: float, 주거공용: float}
from collections import defaultdict

ho_areas = defaultdict(lambda: {"전유": 0.0, "주거공용": 0.0})
for item in all_items:
    d = {c.tag: (c.text or "").strip() for c in item}
    key = (d.get("dongNm",""), d.get("hoNm",""))
    area = float(d.get("area", 0) or 0)
    expos = d.get("exposPubuseGbCd","")
    attach = d.get("mainAtchGbCd","")
    purps = d.get("mainPurpsCdNm","")
    if purps != "아파트" and expos == "1":
        continue  # 아파트가 아닌 전유부 제외 (상가 등)
    if expos == "1":
        ho_areas[key]["전유"] += area
    elif expos == "2" and attach == "0":
        ho_areas[key]["주거공용"] += area

# 전용면적별로 공급면적 집계
exclu_to_supply = defaultdict(list)
for (dong, ho), v in ho_areas.items():
    exclu = round(v["전유"], 2)
    supply = round(v["전유"] + v["주거공용"], 2)
    if exclu > 0:
        exclu_to_supply[exclu].append(supply)

# 대표값 계산 (전용면적 기준 그룹)
print(f"\n{'전용면적':>12}  {'공급면적(대표)':>14}  {'공급평형':>8}  {'호수':>4}  {'전용평형(기존방식)':>16}")
print("-" * 70)

pyeong_results = {}
for exclu in sorted(exclu_to_supply.keys()):
    supplies = exclu_to_supply[exclu]
    rep_supply = round(sum(supplies) / len(supplies), 2)
    supply_pyeong = round(rep_supply * 0.3025)
    old_pyeong = round(exclu * 1.34 / 3.3058)
    print(f"  {exclu:>8.3f}㎡  {rep_supply:>10.2f}㎡  {supply_pyeong:>6}평  {len(supplies):>4}호  (기존 {old_pyeong}평)")
    pyeong_results[exclu] = supply_pyeong

print(f"\n  → 공급면적 기준 평형: {sorted(set(pyeong_results.values()))}평형")
print("\n=== 완료 ===")
