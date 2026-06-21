#!/usr/bin/env python3
"""공급면적 취득 가능한 API 탐색 v6
- BldRgstHubService/getBrExposPubuseAreaInfo (전유공유면적현황)
- AptBasisInfoService1 (공동주택 기본정보)
- 풍산아파트 실거래 데이터로 확인
"""
import os, time
import requests
from xml.etree import ElementTree

KEY = os.environ["DATA_GO_KR_KEY"]
HUB  = "http://apis.data.go.kr/1613000/BldRgstHubService"
TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

def call(url, params, label):
    t0 = time.time()
    r = requests.get(url, params=params, timeout=15)
    elapsed = time.time() - t0
    print(f"\n[{label}] {elapsed:.2f}s  HTTP {r.status_code}")
    if r.status_code == 200:
        try:
            root = ElementTree.fromstring(r.text)
            code = root.findtext(".//resultCode") or ""
            msg  = root.findtext(".//resultMsg")  or ""
            items = root.findall(".//item")
            total = root.findtext(".//totalCount") or "0"
            print(f"  resultCode={code} | {msg} | totalCount={total} | 파싱={len(items)}건")
            if items:
                first = {c.tag: (c.text or "").strip() for c in items[0]}
                print(f"  필드: {list(first.keys())}")
                area_keys = [k for k in first if any(x in k.lower() for x in ["ar","area","area","supply","plat","전용","공급","면적"])]
                print(f"  면적 관련 키: { {k: first[k] for k in area_keys} }")
                return items, root
        except Exception as e:
            print(f"  파싱오류: {e}")
            print(f"  응답: {r.text[:300]}")
    else:
        print(f"  응답: {r.text[:300]}")
    return [], None

# ─── 1. 풍산아파트 실거래에서 위치 파악 ─────────────────────────────────────
print("=" * 60)
print("STEP 1. 풍산아파트 위치 파악 (실거래가 API)")
print("=" * 60)
REGIONS = [
    ("하남 망월동",       "41450", "202606"),
    ("용인수지 상현동",   "41465", "202606"),
    ("인천 연수 연수동",  "28185", "202606"),
    ("하남 망월동",       "41450", "202605"),
    ("용인수지 상현동",   "41465", "202605"),
]
pungsan = None
for label, lawd, ym in REGIONS:
    r = requests.get(TRADE_URL, params={
        "serviceKey": KEY, "LAWD_CD": lawd,
        "DEAL_YMD": ym, "numOfRows": 100, "pageNo": 1,
    }, timeout=15)
    root = ElementTree.fromstring(r.text)
    for item in root.findall(".//item"):
        apt = (item.findtext("aptNm") or "").strip()
        exclu = (item.findtext("excluUseAr") or "").strip()
        if "풍산" in apt:
            bonbun = (item.findtext("bonbun") or "").strip()
            bubun  = (item.findtext("bubun")  or "").strip()
            umd    = (item.findtext("umdNm")  or "").strip()
            print(f"  발견: {label} {umd} {apt}  전용={exclu}㎡  bonbun={bonbun}  bubun={bubun}")
            if not pungsan:
                pungsan = {"apt": apt, "lawd": lawd, "umd": umd,
                           "bonbun": bonbun.zfill(4), "bubun": bubun.zfill(4),
                           "exclu": exclu}

if not pungsan:
    print("  풍산아파트 실거래 없음 — 하남 망월동 첫 번째 아파트로 대체 테스트")
    r = requests.get(TRADE_URL, params={
        "serviceKey": KEY, "LAWD_CD": "41450",
        "DEAL_YMD": "202606", "numOfRows": 5, "pageNo": 1,
    }, timeout=15)
    root = ElementTree.fromstring(r.text)
    item = root.findall(".//item")[0]
    pungsan = {
        "apt":    (item.findtext("aptNm")     or "").strip(),
        "lawd":   "41450",
        "umd":    (item.findtext("umdNm")     or "").strip(),
        "bonbun": (item.findtext("bonbun")    or "0").zfill(4),
        "bubun":  (item.findtext("bubun")     or "0").zfill(4),
        "exclu":  (item.findtext("excluUseAr")or "").strip(),
    }

print(f"\n  사용할 데이터: {pungsan['apt']}  bonbun={pungsan['bonbun']} bubun={pungsan['bubun']}")

# ─── 2. getBrExposPubuseAreaInfo (전유공유면적현황) ──────────────────────────
print("\n" + "=" * 60)
print("STEP 2. BldRgstHubService/getBrExposPubuseAreaInfo")
print("=" * 60)

sigungu = pungsan["lawd"]
# bjdongCd 파악 (lawd_cd 기준 법정동 코드 — 망월동=10900, 상현동=11000, 연수동=10200)
BJDONG_MAP = {"41450": "10900", "41465": "11000", "28185": "10200"}
bjdong = BJDONG_MAP.get(sigungu, "10900")

items, _ = call(f"{HUB}/getBrExposPubuseAreaInfo", {
    "serviceKey": KEY,
    "sigunguCd": sigungu,
    "bjdongCd":  bjdong,
    "bun":       pungsan["bonbun"],
    "ji":        pungsan["bubun"],
    "numOfRows": 200,
    "pageNo":    1,
}, "getBrExposPubuseAreaInfo")

if items:
    print(f"\n  [전체 항목 상위 20건]")
    for item in items[:20]:
        d = {c.tag: (c.text or "").strip() for c in item}
        print(f"    {d}")
    # 전용면적 매칭
    target = pungsan["exclu"]
    matched = [{c.tag: (c.text or "").strip() for c in item}
               for item in items
               if (item.findtext("excluUseAr") or "").strip() == target
               or (item.findtext("area") or "").strip() == target]
    print(f"\n  [전용 {target}㎡ 매칭: {len(matched)}건]")
    for m in matched[:5]:
        print(f"    {m}")

time.sleep(0.5)

# ─── 3. AptBasisInfoService1 — 공동주택 기본정보 ────────────────────────────
print("\n" + "=" * 60)
print("STEP 3. AptBasisInfoService1/getAptBasisInfo1  (공동주택기본정보)")
print("=" * 60)

BASIS_URL = "http://apis.data.go.kr/1613000/AptBasisInfoService1/getAptBasisInfo1"
items2, _ = call(BASIS_URL, {
    "serviceKey": KEY,
    "kaptAddr":   pungsan["umd"],
    "numOfRows":  20,
    "pageNo":     1,
}, "AptBasisInfoService1 (주소 검색)")

if items2:
    for item in items2[:5]:
        d = {c.tag: (c.text or "").strip() for c in item}
        if "풍산" in d.get("kaptName","") or True:
            print(f"  → 단지명={d.get('kaptName','')}  kaptCode={d.get('kaptCode','')}")
            print(f"     공급면적 관련: { {k:v for k,v in d.items() if 'ar' in k.lower() or 'area' in k.lower() or 'Ar' in k} }")

time.sleep(0.5)

# ─── 4. AptBasisInfoService1/getAptHouseInfo (단지코드로 타입별 면적) ────────
print("\n" + "=" * 60)
print("STEP 4. AptBasisInfoService1/getAptHouseInfo  (타입별 면적)")
print("=" * 60)

# 이전 결과에서 kaptCode 추출 시도
kaptCode = None
if items2:
    for item in items2:
        d = {c.tag: (c.text or "").strip() for c in item}
        if "풍산" in d.get("kaptName",""):
            kaptCode = d.get("kaptCode","")
            break
    if not kaptCode:
        kaptCode = {c.tag: (c.text or "").strip() for c in items2[0]}.get("kaptCode","")

HOUSE_URL = "http://apis.data.go.kr/1613000/AptBasisInfoService1/getAptHouseInfo"
if kaptCode:
    print(f"  kaptCode={kaptCode}")
    items3, _ = call(HOUSE_URL, {
        "serviceKey": KEY,
        "kaptCode":   kaptCode,
        "numOfRows":  50,
        "pageNo":     1,
    }, "getAptHouseInfo")
    if items3:
        for item in items3:
            d = {c.tag: (c.text or "").strip() for c in item}
            print(f"  타입: {d}")
else:
    print("  kaptCode 없음 — 스킵")

time.sleep(0.5)

# ─── 5. BldRgstHubService 남은 엔드포인트 탐색 ──────────────────────────────
print("\n" + "=" * 60)
print("STEP 5. BldRgstHubService 추가 엔드포인트 시도")
print("=" * 60)

extra_eps = [
    "getBrExposAreaInfo",
    "getBrUnitExposAreaInfo",
    "getBrHsprcInfo",
]
base_params = {
    "serviceKey": KEY,
    "sigunguCd": sigungu,
    "bjdongCd":  bjdong,
    "bun":       pungsan["bonbun"],
    "ji":        pungsan["bubun"],
    "numOfRows": 10,
    "pageNo":    1,
}
for ep in extra_eps:
    call(f"{HUB}/{ep}", base_params, ep)
    time.sleep(0.3)

print("\n=== 완료 ===")
