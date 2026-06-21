#!/usr/bin/env python3
"""미사동/선동/위례동 bjdong 코드 탐색"""
import os, time, requests
from xml.etree import ElementTree

KEY  = os.environ["DATA_GO_KR_KEY"]
HUB  = "http://apis.data.go.kr/1613000/BldRgstHubService"
TRADE_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

TARGETS = [
    {"dong": "미사동",  "lawd": "41450", "label": "하남시 미사동"},
    {"dong": "선동",    "lawd": "41450", "label": "하남시 선동"},
    {"dong": "위례동",  "lawd": "41450", "label": "하남시 위례동"},
]

CANDIDATE_BJDONGS = [
    "10100","10200","10300","10400","10500","10600","10700",
    "10800","10900","11000","11100","11200","11300","11700",
    "11800","11900","12000","12100","12200","12300","12400","12500",
]

def xml_items(text):
    try:
        root = ElementTree.fromstring(text)
        return root.findall(".//item")
    except:
        return []

def get_bonbun(lawd, dong):
    """실거래가 API에서 해당 동의 건물 bonbun 조회"""
    for ym in ["202606","202605","202604","202603","202602","202601",
               "202512","202511","202510","202509","202508","202507",
               "202506","202505","202504","202503","202502","202501",
               "202412","202411","202410","202409"]:
        r = requests.get(TRADE_URL, params={
            "serviceKey": KEY, "LAWD_CD": lawd,
            "DEAL_YMD": ym, "numOfRows": 100, "pageNo": 1,
        }, timeout=15)
        for item in xml_items(r.text):
            umd = (item.findtext("umdNm") or "").strip()
            if umd == dong:
                bun = (item.findtext("bonbun") or "").strip()
                ji  = (item.findtext("bubun")  or "").strip()
                apt = (item.findtext("aptNm")  or "").strip()
                if bun:
                    return bun, ji, apt, ym
        time.sleep(0.15)
    return None, None, None, None

def find_bjdong(lawd, bun, ji):
    """getBrRecapTitleInfo로 bjdong 탐색"""
    for bjd in CANDIDATE_BJDONGS:
        r = requests.get(f"{HUB}/getBrRecapTitleInfo", params={
            "serviceKey": KEY, "sigunguCd": lawd, "bjdongCd": bjd,
            "bun": bun.zfill(4), "ji": (ji or "0").zfill(4),
            "numOfRows": 1, "pageNo": 1,
        }, timeout=15)
        items = xml_items(r.text)
        if items:
            plat = items[0].findtext("platPlc") or ""
            vl   = items[0].findtext("vlRat") or ""
            bc   = items[0].findtext("bcRat") or ""
            return bjd, plat, vl, bc
        time.sleep(0.15)
    return None, None, None, None

print("=" * 60)
for t in TARGETS:
    print(f"\n[{t['label']}]")
    bun, ji, apt, ym = get_bonbun(t["lawd"], t["dong"])
    if not bun:
        print(f"  !! {t['dong']} 거래 없음 (더 오래된 데이터 필요)")
        continue
    print(f"  건물: {apt}  bonbun={bun} bubun={ji}  (데이터:{ym})")

    bjd, plat, vl, bc = find_bjdong(t["lawd"], bun, ji)
    if bjd:
        print(f"  ✓ bjdongCd = {bjd}")
        print(f"    platPlc  = {plat}")
        print(f"    vlRat={vl}  bcRat={bc}")
    else:
        print(f"  ✗ bjdong 코드를 찾지 못했습니다 (후보 없음)")

print("\n완료")
