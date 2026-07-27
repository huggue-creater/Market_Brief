#!/usr/bin/env python3
"""GitHub Actions에서 네이버 부동산 API 접근 가능성 테스트 (일회용).

목적: Actions(데이터센터 IP)에서
  - new.land / fin.land (개별 매물 상세 API) 가 뚫리는지
  - 뚫리면 토큰까지 얻어 실제 매물 목록을 받는지
확인. 결과를 로그로 남긴다. 커밋/발송 없음.
"""
import json
import re
import sys
import requests

sys.stdout.reconfigure(encoding="utf-8")

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

HSCP = "105286"     # 하남 망월동 미사강변센트리버(예시)
CORTAR = "4145010900"


def probe(method, url, label, **kw):
    try:
        r = requests.request(method, url, timeout=20, **kw)
        r.encoding = "utf-8"
        print(f"[{label}] {r.status_code} len={len(r.text)} "
              f"ct={r.headers.get('Content-Type','')[:30]}")
        print("   ", r.text[:300].replace("\n", " "))
        return r
    except Exception as exc:
        print(f"[{label}] BLOCKED/ERROR {type(exc).__name__}: {str(exc)[:120]}")
        return None


def main():
    print("=" * 70)
    print("네이버 부동산 API — GitHub Actions 접근 테스트")
    print("=" * 70)

    # ── 대조군: m.land 집계 (로컬에서 동작 확인됨) ──
    b = (f"itemId=&mapKey=&lgeo=&showR0=&rletTpCd=APT&tradTpCd=A1&z=14"
         f"&lat=37.564&lon=127.193&btm=37.53&lft=127.15&top=37.59&rgt=127.24"
         f"&cortarNo={CORTAR}")
    probe("GET", f"https://m.land.naver.com/cluster/ajax/complexList?{b}",
          "control m.land complexList",
          headers={"User-Agent": UA_PC, "Referer": "https://m.land.naver.com/"})

    # ── 본론 1: new.land 홈페이지 도달 여부 + 토큰 추출 ──
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA_PC, "Accept-Language": "ko-KR,ko;q=0.9"})
    token = ""
    r = probe("GET", "https://new.land.naver.com/", "new.land home",
              headers={"User-Agent": UA_PC})
    if r is not None and r.status_code == 200:
        # __NEXT_DATA__ / JS 번들에서 Bearer 토큰 탐색
        m = re.search(r'(Bearer\s+[A-Za-z0-9._~+/-]+=*)', r.text)
        if m:
            token = m.group(1)
            print("   >>> 토큰 추출 성공:", token[:30], "...")

    # ── 본론 2: new.land 개별 매물 API (토큰 유무 각각) ──
    api = (f"https://new.land.naver.com/api/articles/complex/{HSCP}"
           f"?realEstateType=APT&tradeType=A1&page=1&order=rank&complexNo={HSCP}"
           f"&priceType=RETAIL")
    h = {"User-Agent": UA_PC, "Referer": f"https://new.land.naver.com/complexes/{HSCP}",
         "Accept": "*/*"}
    probe("GET", api, "new.land articles (no token)", headers=h)
    if token:
        h2 = dict(h, Authorization=token)
        rr = probe("GET", api, "new.land articles (with token)", headers=h2)
        if rr is not None and rr.status_code == 200:
            try:
                arts = rr.json().get("articleList", [])
                print(f"   >>> 개별 매물 {len(arts)}건 수신!")
                if arts:
                    a = arts[0]
                    print("   샘플:", json.dumps({k: a.get(k) for k in [
                        "articleNo", "buildingName", "floorInfo", "direction",
                        "areaName", "area1", "dealOrWarrantPrc", "articleConfirmYmd"]},
                        ensure_ascii=False))
            except Exception as exc:
                print("   parse err", exc)

    # ── 본론 3: fin.land (신규 API) 도달 여부 ──
    probe("POST", "https://fin.land.naver.com/front-api/v1/complex/article/list",
          "fin.land article/list",
          headers={"User-Agent": UA_PC, "Content-Type": "application/json",
                   "Referer": f"https://fin.land.naver.com/complexes/{HSCP}"},
          json={"complexNumber": HSCP, "tradeTypes": ["A1"], "page": 1, "pageSize": 20})

    print("=" * 70)
    print("판정: new.land articles (with token) 가 200 + 매물수신이면 → 정밀 매칭 가능")
    print("      timeout/403 이면 → Actions도 차단, 집계 방식으로 폴백")
    print("=" * 70)


if __name__ == "__main__":
    main()
