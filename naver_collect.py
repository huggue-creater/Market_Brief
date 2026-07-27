#!/usr/bin/env python3
"""네이버 부동산 매물 수집 + 변동 분석 (로컬 전용).

수집: curl_cffi(Chrome 지문 모방) + new.land 앱토큰으로 하남 6개 동의
      아파트 매매 매물(호가·동·층·향·면적)을 전량 수집.
분석: 전일 스냅샷과 diff → 신규등록 / 재등록 / 거래예상(사라진 매물).
      사라진 매물을 오늘 신규 중 동·평형·향 일치로 매칭하면 재등록,
      없으면 '거래 예상'(마지막 호가 = 거래 추정가).

출력:
  naver_snapshot.json  현재 전체 매물 상태(first_seen/last_seen 포함, 커밋)
  naver_events.json    최신 변동 이벤트(브리핑·대시보드가 소비)

※ 반드시 가정용 IP(로컬 PC)에서 실행. 데이터센터 IP는 네이버가 차단함.
"""
import datetime
import json
import logging
import re
import socket
import sys
import time
from pathlib import Path

# ── IPv4 강제 (이 회선에서 IPv6는 new.land 차단) ──
_orig_gai = socket.getaddrinfo
socket.getaddrinfo = lambda *a, **k: [r for r in _orig_gai(*a, **k)
                                      if r[0] == socket.AF_INET]

from curl_cffi import requests as cr  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

KST = datetime.timezone(datetime.timedelta(hours=9))

SNAPSHOT_FILE = Path("naver_snapshot.json")
EVENTS_FILE   = Path("naver_events.json")

# 하남 6개 동 (법정동코드 10자리 = lawd(5)+bjdong(5))
DONGS = {
    "망월동": "4145010900",
    "선동":   "4145011200",
    "신장동": "4145010600",
    "풍산동": "4145011000",
    "창우동": "4145010300",
    "덕풍동": "4145010800",
}

TOKEN_SEED_COMPLEX = "105286"  # 토큰 추출용 아무 단지
BASE = "https://new.land.naver.com"


# ══════════════════════════════════════════════════════════════════
# 수집
# ══════════════════════════════════════════════════════════════════

def new_session() -> cr.Session:
    return cr.Session(impersonate="chrome", timeout=20)


def get_token(sess: cr.Session) -> str:
    r = sess.get(f"{BASE}/complexes/{TOKEN_SEED_COMPLEX}",
                 headers={"Referer": f"{BASE}/"})
    m = re.search(r'token"\s*:\s*"(eyJ[A-Za-z0-9._-]+)', r.text)
    if not m:
        title = re.search(r"<title>([^<]*)</title>", r.text)
        raise RuntimeError(f"토큰 추출 실패 (봇차단? title={title.group(1) if title else '?'})")
    return m.group(1)


def fetch_complexes(sess: cr.Session, token: str, cortar: str) -> list:
    r = sess.get(f"{BASE}/api/regions/complexes",
                 params={"cortarNo": cortar,
                         "realEstateType": "APT:PRE:ABYG:JGC", "order": ""},
                 headers={"Authorization": f"Bearer {token}", "Referer": f"{BASE}/"})
    if r.status_code != 200:
        log.warning("  단지목록 %s http=%s", cortar, r.status_code)
        return []
    return r.json().get("complexList", [])


def fetch_articles(sess: cr.Session, token: str, complex_no: str) -> list:
    """단지의 매매(A1) 매물 전량(페이지네이션)."""
    out, page = [], 1
    while True:
        r = sess.get(f"{BASE}/api/articles/complex/{complex_no}",
                     params={"realEstateType": "APT:PRE:ABYG:JGC", "tradeType": "A1",
                             "page": page, "order": "rank", "complexNo": complex_no,
                             "priceType": "RETAIL"},
                     headers={"Authorization": f"Bearer {token}",
                              "Referer": f"{BASE}/complexes/{complex_no}"})
        if r.status_code != 200:
            log.warning("    매물 %s p%d http=%s", complex_no, page, r.status_code)
            break
        d = r.json()
        out.extend(d.get("articleList", []))
        if not d.get("isMoreData"):
            break
        page += 1
        time.sleep(0.3)
    return out


def parse_price(s: str) -> int:
    """'12억 8,000' → 128000(만원). '12억' → 120000. '9,500' → 9500."""
    if not s:
        return 0
    s = s.replace(" ", "")
    eok = 0
    man = 0
    if "억" in s:
        parts = s.split("억")
        eok = int(re.sub(r"[^0-9]", "", parts[0]) or 0)
        rest = re.sub(r"[^0-9]", "", parts[1]) if len(parts) > 1 else ""
        man = int(rest) if rest else 0
    else:
        man = int(re.sub(r"[^0-9]", "", s) or 0)
    return eok * 10000 + man


def normalize(dong: str, cx: dict, a: dict) -> dict:
    return {
        "dong": dong,
        "complexNo": str(cx.get("complexNo", "")),
        "complexName": cx.get("complexName", ""),
        "building": a.get("buildingName", ""),      # 동
        "floor": a.get("floorInfo", ""),            # "4/26" / "중/30"
        "direction": a.get("direction", ""),        # 향
        "areaName": a.get("areaName", ""),          # 평형 타입 "84A"
        "area": a.get("area1", ""),                 # 공급면적 ㎡
        "priceText": a.get("dealOrWarrantPrc", ""),
        "price": parse_price(a.get("dealOrWarrantPrc", "")),
        "confirmYmd": a.get("articleConfirmYmd", ""),
        "feature": a.get("articleFeatureDesc", ""),
        "realtor": a.get("realtorName", ""),
    }


def collect_all(sess: cr.Session, token: str) -> dict:
    """{articleNo: detail} 전체."""
    articles = {}
    for dong, cortar in DONGS.items():
        cxs = fetch_complexes(sess, token, cortar)
        log.info("[%s] 단지 %d개", dong, len(cxs))
        for cx in cxs:
            cno = str(cx.get("complexNo", ""))
            if not cno:
                continue
            arts = fetch_articles(sess, token, cno)
            for a in arts:
                ano = str(a.get("articleNo", ""))
                if ano:
                    articles[ano] = normalize(dong, cx, a)
            time.sleep(0.25)
    return articles


# ══════════════════════════════════════════════════════════════════
# 변동 분석
# ══════════════════════════════════════════════════════════════════

def match_key(a: dict) -> tuple:
    """재등록 매칭 키: 같은 단지·동·평형·향(층 제외 — 층 표기가 바뀌기도 함)."""
    return (a["complexNo"], a["building"], a["areaName"], a["direction"])


def analyze(prev_articles: dict, today: dict, today_str: str) -> dict:
    prev_ids = set(prev_articles)
    today_ids = set(today)
    added_ids = today_ids - prev_ids
    removed_ids = prev_ids - today_ids

    # 재등록 매칭: 사라진 매물 ↔ 오늘 신규 (같은 key)
    added_by_key: dict = {}
    for aid in added_ids:
        added_by_key.setdefault(match_key(today[aid]), []).append(aid)

    reregistered, likely_sold = [], []
    matched_added = set()

    for rid in removed_ids:
        r = prev_articles[rid]
        pool = added_by_key.get(match_key(r), [])
        cand = next((x for x in pool if x not in matched_added), None)
        if cand:
            matched_added.add(cand)
            n = today[cand]
            reregistered.append({
                **{k: r[k] for k in ("dong", "complexName", "building",
                                     "floor", "direction", "areaName")},
                "oldPrice": r["price"], "oldPriceText": r["priceText"],
                "newPrice": n["price"], "newPriceText": n["priceText"],
                "newArticleNo": cand, "oldArticleNo": rid,
            })
        else:
            first = r.get("first_seen", today_str)
            dom = (datetime.date.fromisoformat(today_str)
                   - datetime.date.fromisoformat(first)).days
            likely_sold.append({
                "dong": r["dong"], "complexName": r["complexName"],
                "building": r["building"], "floor": r["floor"],
                "direction": r["direction"], "areaName": r["areaName"],
                "area": r["area"], "lastPrice": r["price"],
                "lastPriceText": r["priceText"], "confirmYmd": r["confirmYmd"],
                "firstSeen": first, "daysOnMarket": dom, "articleNo": rid,
            })

    new_listings = [today[aid] for aid in added_ids if aid not in matched_added]

    return {
        "date": today_str,
        "counts": {
            "total": len(today), "new": len(new_listings),
            "reregistered": len(reregistered), "likelySold": len(likely_sold),
        },
        "likelySold": sorted(likely_sold, key=lambda x: -x["lastPrice"]),
        "reregistered": reregistered,
        "newListings": new_listings,
    }


def merge_snapshot(prev_articles: dict, today: dict, today_str: str) -> dict:
    """first_seen 계승하며 오늘 스냅샷 구성."""
    out = {}
    for ano, a in today.items():
        prev = prev_articles.get(ano)
        a = dict(a)
        a["first_seen"] = prev.get("first_seen", today_str) if prev else today_str
        a["last_seen"] = today_str
        out[ano] = a
    return out


# ══════════════════════════════════════════════════════════════════

def main():
    today_str = datetime.datetime.now(KST).date().isoformat()
    log.info("=== 네이버 매물 수집 시작: %s ===", today_str)

    prev = {}
    if SNAPSHOT_FILE.exists():
        prev = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8")).get("articles", {})
    first_run = not prev

    sess = new_session()
    token = get_token(sess)
    log.info("토큰 확보 OK")

    today = collect_all(sess, token)
    log.info("수집 완료: 매물 %d건", len(today))
    if not today:
        log.error("수집 0건 — 스냅샷 보존, 종료")
        return

    if first_run:
        log.info("첫 실행 — 변동 분석 생략(기준 스냅샷만 저장)")
        events = {"date": today_str, "firstRun": True,
                  "counts": {"total": len(today), "new": 0,
                             "reregistered": 0, "likelySold": 0},
                  "likelySold": [], "reregistered": [], "newListings": []}
    else:
        events = analyze(prev, today, today_str)
        c = events["counts"]
        log.info("변동: 신규 %d · 재등록 %d · 거래예상 %d",
                 c["new"], c["reregistered"], c["likelySold"])

    snapshot = {
        "collected_at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "articles": merge_snapshot(prev, today, today_str),
    }
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    EVENTS_FILE.write_text(json.dumps(events, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    log.info("저장 완료: %s, %s", SNAPSHOT_FILE, EVENTS_FILE)


if __name__ == "__main__":
    main()
