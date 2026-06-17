#!/usr/bin/env python3
"""
Market Brief Bot
  - Feature 1: 코인(BTC/ETH/XRP) + 환율 → Telegram
  - Feature 2: 선물지수(US500/Tech100/VIX/Nikkei/HangSeng) → Telegram
  - Feature 3: 아파트 신규 실거래 알림 → Telegram (telegram=True 동만)
  - Feature 4: 전체 동 검색용 JSON 생성 → search_data.json
"""

import os
import sys
import json
import time
import logging
import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

import holidays
import requests

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
DATA_GO_KR_KEY     = os.environ["DATA_GO_KR_KEY"]

APT_TRADE_URL  = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
BUILD_INFO_URL = "http://apis.data.go.kr/1613000/BldRgstService_v2/getBrRecapTitleInfo"
UPBIT_URL      = "https://api.upbit.com/v1/ticker"
COINGECKO_URL  = "https://api.coingecko.com/api/v3/simple/price"
YAHOO_URL      = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

MONTHS_BACK   = 6
RETRY_COUNT   = 4
RETRY_DELAYS  = [2, 4, 8, 16]
TELEGRAM_LIMIT = 3800

STATE_FILE       = Path("apt_state.json")
CACHE_FILE       = Path("building_cache.json")
SEARCH_JSON_FILE = Path("search_data.json")
LAST_RUN_FILE    = Path("last_run.txt")

# ── Region definitions ────────────────────────────────────────────────────────
# lawd : 시군구코드 5자리 (거래 조회)
# bjdong: 법정동코드 뒤5자리 (건축물대장, None이면 스킵)
# dong  : API 응답 umdNm 필터링값
REGIONS = [
    # ── Telegram 알림 ──
    {"city": "하남", "name": "망월동", "lawd": "41450", "bjdong": "10900", "dong": "망월동", "telegram": True},
    {"city": "용인", "name": "상현동", "lawd": "41465", "bjdong": "10700", "dong": "상현동", "telegram": True},
    {"city": "인천", "name": "연수동", "lawd": "28185", "bjdong": "10300", "dong": "연수동", "telegram": True},
    # ── 하남 검색 전용 ──
    {"city": "하남", "name": "신장동", "lawd": "41450", "bjdong": "10600", "dong": "신장동", "telegram": False},
    {"city": "하남", "name": "창우동", "lawd": "41450", "bjdong": "10300", "dong": "창우동", "telegram": False},
    {"city": "하남", "name": "덕풍동", "lawd": "41450", "bjdong": "10800", "dong": "덕풍동", "telegram": False},
    {"city": "하남", "name": "풍산동", "lawd": "41450", "bjdong": "11000", "dong": "풍산동", "telegram": False},
    {"city": "하남", "name": "감일동", "lawd": "41450", "bjdong": "11400", "dong": "감일동", "telegram": False},
    {"city": "하남", "name": "감이동", "lawd": "41450", "bjdong": "11500", "dong": "감이동", "telegram": False},
    {"city": "하남", "name": "학암동", "lawd": "41450", "bjdong": "11600", "dong": "학암동", "telegram": False},
    # bjdong 미확보 — 거래조회는 되지만 건축물대장 스킵
    {"city": "하남", "name": "선동",   "lawd": "41450", "bjdong": None,    "dong": "선동",   "telegram": False},
    {"city": "하남", "name": "미사동", "lawd": "41450", "bjdong": None,    "dong": "미사동", "telegram": False},
    {"city": "하남", "name": "위례동", "lawd": "41450", "bjdong": None,    "dong": "위례동", "telegram": False},
    # ── 시흥 ──
    {"city": "시흥", "name": "정왕동", "lawd": "41390", "bjdong": "13200", "dong": "정왕동", "telegram": False},
]


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def http_get(url: str, params: dict = None, timeout: int = 15) -> Optional[requests.Response]:
    """GET with exponential-backoff retry. Returns Response or None."""
    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            log.warning("GET %s attempt %d/%d failed: %s — retry in %ds",
                        url.split("?")[0], attempt + 1, RETRY_COUNT, exc, wait)
            if attempt < RETRY_COUNT - 1:
                time.sleep(wait)
    log.error("GET %s failed after %d attempts", url.split("?")[0], RETRY_COUNT)
    return None


def send_telegram(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    resp = http_get(url, params=params)
    if resp and resp.ok:
        return True
    log.error("Telegram send failed: %s", resp.text if resp else "no response")
    return False


def send_telegram_chunked(text: str) -> bool:
    """Split long messages and send sequentially."""
    if len(text) <= TELEGRAM_LIMIT:
        return send_telegram(text)
    lines = text.split("\n")
    chunk, parts = [], []
    for line in lines:
        if sum(len(l) + 1 for l in chunk) + len(line) > TELEGRAM_LIMIT:
            parts.append("\n".join(chunk))
            chunk = [line]
        else:
            chunk.append(line)
    if chunk:
        parts.append("\n".join(chunk))
    ok = True
    for i, part in enumerate(parts):
        ok = send_telegram(part) and ok
        if i < len(parts) - 1:
            time.sleep(0.4)
    return ok


def get_ym_list(months_back: int) -> list:
    today = datetime.date.today()
    result = []
    for i in range(months_back):
        year  = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year  -= 1
        result.append(f"{year}{month:02d}")
    return result


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_krw(amount) -> str:
    """Convert int or comma-string to Korean '억/만' notation."""
    try:
        val = int(str(amount).replace(",", ""))
        eok = val // 10000
        man = val % 10000
        if eok and man:
            return f"{eok}억 {man:,}만"
        if eok:
            return f"{eok}억"
        return f"{val:,}만"
    except Exception:
        return str(amount)


def price_val(t: dict) -> int:
    try:
        return int(t.get("dealAmount", "0").replace(",", ""))
    except Exception:
        return 0


def trade_date_int(t: dict) -> int:
    try:
        return int(f"{t.get('dealYear','0')}"
                   f"{int(t.get('dealMonth', 1)):02d}"
                   f"{int(t.get('dealDay', 1)):02d}")
    except Exception:
        return 0


def trade_id(t: dict) -> str:
    return "|".join([
        t.get("umdNm", ""),
        t.get("aptNm", ""),
        t.get("dealYear", ""),
        t.get("dealMonth", ""),
        t.get("dealDay", ""),
        t.get("excluUseAr", ""),
        t.get("floor", ""),
        t.get("dealAmount", ""),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Feature 1 — Coin + FX
# ══════════════════════════════════════════════════════════════════════════════

def get_coin_fx_message() -> str:
    coins   = ["BTC", "ETH", "XRP"]
    cg_ids  = {"BTC": "bitcoin", "ETH": "ethereum", "XRP": "ripple"}

    # Upbit KRW
    krw_prices: dict = {}
    resp = http_get(UPBIT_URL, params={"markets": ",".join(f"KRW-{c}" for c in coins)})
    if resp:
        for item in resp.json():
            ticker = item["market"].replace("KRW-", "")
            krw_prices[ticker] = item["trade_price"]

    # CoinGecko USD
    usd_prices: dict = {}
    resp = http_get(COINGECKO_URL, params={"ids": ",".join(cg_ids.values()), "vs_currencies": "usd"})
    if resp:
        for ticker, cg_id in cg_ids.items():
            usd_prices[ticker] = resp.json().get(cg_id, {}).get("usd")

    # USD/KRW
    usdkrw = None
    resp = http_get(YAHOO_URL.format(symbol="USDKRW=X"), params={"interval": "1m", "range": "1d"})
    if resp:
        try:
            usdkrw = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
        except Exception:
            pass

    # JPY/KRW (via USDJPY)
    jpykrw = None
    resp = http_get(YAHOO_URL.format(symbol="JPY=X"), params={"interval": "1m", "range": "1d"})
    if resp and usdkrw:
        try:
            jpyusd = resp.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
            jpykrw = usdkrw / jpyusd  # KRW per 1 JPY
        except Exception:
            pass

    lines = ["📊 <b>코인 · 환율</b>"]
    for c in coins:
        krw = krw_prices.get(c)
        usd = usd_prices.get(c)
        if krw and usd and usdkrw:
            kimp = (krw / (usd * usdkrw) - 1) * 100
            sig  = "▲" if kimp >= 0 else "▼"
            lines.append(f"  {c}: ${usd:,.2f} | ₩{krw:,.0f} | 김프 {sig}{abs(kimp):.2f}%")
        elif krw:
            lines.append(f"  {c}: ₩{krw:,.0f}")
        else:
            lines.append(f"  {c}: 데이터 없음")

    if usdkrw:
        lines.append(f"  USD/KRW: {usdkrw:,.1f}")
    if jpykrw:
        lines.append(f"  100JPY/KRW: {jpykrw * 100:,.0f}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Feature 2 — Futures / Indices
# ══════════════════════════════════════════════════════════════════════════════

FUTURES = [
    ("ES=F",  "US500"),
    ("NQ=F",  "US Tech100"),
    ("^VIX",  "VIX"),
    ("^N225", "Nikkei225"),
    ("^HSI",  "Hang Seng"),
]

def get_futures_message() -> str:
    lines = ["📈 <b>선물 · 지수</b>"]
    for symbol, label in FUTURES:
        resp = http_get(YAHOO_URL.format(symbol=symbol), params={"interval": "1m", "range": "1d"})
        if not resp:
            lines.append(f"  {label}: 데이터 없음")
            continue
        try:
            meta  = resp.json()["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            prev  = (meta.get("chartPreviousClose")
                     or meta.get("previousClose")
                     or meta.get("regularMarketPreviousClose"))
            if prev:
                chg = price - prev
                pct = chg / prev * 100
                sig = "▲" if chg >= 0 else "▼"
                lines.append(f"  {label}: {price:,.2f} {sig}{abs(pct):.2f}%")
            else:
                lines.append(f"  {label}: {price:,.2f}")
        except Exception as exc:
            log.warning("Futures parse %s: %s", symbol, exc)
            lines.append(f"  {label}: 파싱 오류")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Apartment trade collection (shared by Feature 3 & 4)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_apt_trades_month(lawd: str, ym: str) -> list:
    """Fetch all pages for (lawd, YYYYMM). Returns list of trade dicts."""
    all_items = []
    page = 1
    while True:
        params = {
            "serviceKey": DATA_GO_KR_KEY,
            "LAWD_CD":    lawd,
            "DEAL_YMD":   ym,
            "numOfRows":  100,
            "pageNo":     page,
        }
        resp = http_get(APT_TRADE_URL, params=params)
        if not resp:
            log.error("  fetch_apt_trades lawd=%s ym=%s page=%d: HTTP 실패", lawd, ym, page)
            break
        try:
            root  = ElementTree.fromstring(resp.text)
            # 오류 응답 체크
            result_code = root.findtext(".//resultCode") or root.findtext(".//errMsg") or ""
            if "SERVICE_KEY" in result_code or "LIMITED" in result_code:
                log.error("  API 키 오류: %s", result_code)
                break
            items = root.findall(".//item")
            if not items:
                break
            for item in items:
                d = {child.tag: (child.text or "").strip() for child in item}
                all_items.append(d)
            total = int(root.findtext(".//totalCount") or "0")
            if page * 100 >= total:
                break
            page += 1
        except Exception as exc:
            log.error("  fetch_apt_trades parse lawd=%s ym=%s: %s", lawd, ym, exc)
            break
    return all_items


def collect_trades_for_region(region: dict, ym_list: list) -> list:
    """Collect & filter trades for one region across all months."""
    dong = region["dong"]
    lawd = region["lawd"]
    name = region["name"]
    all_trades = []
    for ym in ym_list:
        try:
            trades = fetch_apt_trades_month(lawd, ym)
            dong_trades = [t for t in trades if t.get("umdNm", "").strip() == dong]
            log.info("  %s: %s → %d건", name, ym, len(dong_trades))
            all_trades.extend(dong_trades)
        except Exception as exc:
            log.error("  %s %s 수집 오류: %s", name, ym, exc)
    return all_trades


# ══════════════════════════════════════════════════════════════════════════════
# Feature 3 — Apartment new-trade alerts
# ══════════════════════════════════════════════════════════════════════════════

def _build_telegram_apt_msg(region: dict, new_trades: list, known_ids: set, all_trades: list) -> str:
    name = region["name"]

    # Price history from PREVIOUSLY KNOWN non-cancelled trades only
    old_trades = [t for t in all_trades
                  if trade_id(t) in known_ids and t.get("cdealType") != "Y"]
    unit_old: dict = {}
    for t in sorted(old_trades, key=trade_date_int):
        key = (t.get("aptNm", ""), t.get("excluUseAr", ""))
        unit_old.setdefault(key, []).append(price_val(t))

    lines = [f"🏠 <b>{name} 신규 거래</b> ({len(new_trades)}건)"]
    for t in sorted(new_trades, key=trade_date_int):
        apt        = t.get("aptNm", "")
        area       = t.get("excluUseAr", "")
        floor_     = t.get("floor", "")
        price_s    = fmt_krw(t.get("dealAmount", ""))
        cur        = price_val(t)
        cancelled  = t.get("cdealType") == "Y"
        direct     = "직" in (t.get("dealingGbn") or "")
        date_s     = (f"{t.get('dealYear','')}."
                      f"{int(t.get('dealMonth', 1)):02d}."
                      f"{int(t.get('dealDay', 1)):02d}")

        key        = (apt, area)
        old_prices = unit_old.get(key, [])

        flags = []
        if cancelled:
            flags.append("❌취소")
        if direct:
            flags.append("🤝직거래")
        if not cancelled and old_prices and cur > max(old_prices):
            flags.append("🏆신고가")

        line = f"  [{date_s}] {apt} {area}㎡/{floor_}층 {price_s}"
        if flags:
            line += "  " + " ".join(flags)
        if not cancelled and old_prices:
            prev = old_prices[-1]
            diff = cur - prev
            sig  = "▲" if diff >= 0 else "▼"
            line += f"\n    ↳ 직전 {fmt_krw(prev)} 대비 {sig}{fmt_krw(abs(diff))}"

        lines.append(line)
    return "\n".join(lines)


def run_apartment_alerts(ym_list: list):
    state = load_json(STATE_FILE, {})

    for region in [r for r in REGIONS if r["telegram"]]:
        name = region["name"]
        log.info("[알림] %s 확인 중...", name)
        try:
            known_ids  = set(state.get(name, []))
            all_trades = collect_trades_for_region(region, ym_list)
            new_trades = [t for t in all_trades if trade_id(t) not in known_ids]
            log.info("  %s: 전체 %d건, 신규 %d건", name, len(all_trades), len(new_trades))

            if not known_ids:
                log.info("  %s: 첫 실행 — 상태 초기화 (알림 없음)", name)
            elif new_trades:
                msg = _build_telegram_apt_msg(region, new_trades, known_ids, all_trades)
                send_telegram_chunked(msg)

            # Merge all seen IDs into state
            new_ids = {trade_id(t) for t in all_trades}
            state[name] = list(set(state.get(name, [])) | new_ids)
        except Exception as exc:
            log.error("  %s 알림 오류: %s", name, exc)

    save_json(STATE_FILE, state)


# ══════════════════════════════════════════════════════════════════════════════
# Building registry cache
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_building_info(sigungu: str, bjdong: str) -> dict:
    """Returns {aptNm: {vlRat, bcRat}} or {} on failure."""
    params = {
        "serviceKey": DATA_GO_KR_KEY,
        "sigunguCd":  sigungu,
        "bjdongCd":   bjdong,
        "numOfRows":  200,
        "pageNo":     1,
    }
    resp = http_get(BUILD_INFO_URL, params=params)
    if not resp:
        return {}
    try:
        root   = ElementTree.fromstring(resp.text)
        result = {}
        for item in root.findall(".//item"):
            d     = {child.tag: (child.text or "").strip() for child in item}
            nm    = d.get("bldNm", "")
            if nm:
                result[nm] = {"vlRat": d.get("vlRat", ""), "bcRat": d.get("bcRat", "")}
        return result
    except Exception as exc:
        log.warning("Building parse sigungu=%s bjdong=%s: %s", sigungu, bjdong, exc)
        return {}


def update_building_cache() -> dict:
    cache = load_json(CACHE_FILE, {})
    changed = False
    for region in REGIONS:
        bjdong = region.get("bjdong")
        if not bjdong:
            log.info("  건축물대장: %s bjdong 없음, 스킵", region["name"])
            continue
        key = f"{region['lawd']}|{bjdong}"
        if key in cache:
            continue  # 실패(빈 dict) 포함 캐시 히트 → 재조회 안 함
        log.info("  건축물대장: %s 조회 중...", region["name"])
        data = _fetch_building_info(region["lawd"], bjdong)
        cache[key] = data  # 실패해도 {} 저장 → 다음 날 재조회 안 함
        changed = True
        log.info("  건축물대장: %s → %d개 단지", region["name"], len(data))
        time.sleep(0.3)
    if changed:
        save_json(CACHE_FILE, cache)
    return cache


# ══════════════════════════════════════════════════════════════════════════════
# Feature 4 — Search JSON generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_search_json(ym_list: list):
    log.info("=== 검색 JSON 생성 시작 ===")
    building_cache = update_building_cache()
    region_map     = {r["name"]: r for r in REGIONS}
    all_trades     = []

    for region in REGIONS:
        name = region["name"]
        log.info("[검색JSON] %s 수집 중...", name)
        try:
            trades = collect_trades_for_region(region, ym_list)
            log.info("  %s: %d건", name, len(trades))

            cache_key = f"{region['lawd']}|{region['bjdong']}" if region.get("bjdong") else None
            dong_bld  = building_cache.get(cache_key, {}) if cache_key else {}

            for t in trades:
                t["_city"]  = region["city"]
                t["_dong"]  = name
                t["_lawd"]  = region["lawd"]
                meta        = dong_bld.get(t.get("aptNm", ""), {})
                t["_vlRat"] = meta.get("vlRat", "")
                t["_bcRat"] = meta.get("bcRat", "")
            all_trades.extend(trades)
        except Exception as exc:
            log.error("  %s 검색JSON 오류: %s", name, exc)

    total = len(all_trades)
    log.info("전체 수집: %d건", total)

    if total == 0:
        log.warning("수집 0건 — 기존 JSON 보존 (덮어쓰지 않음)")
        return

    save_json(SEARCH_JSON_FILE, {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "months":       ym_list,
        "total":        total,
        "trades":       all_trades,
    })
    log.info("검색 JSON 저장 완료: %s (%d건)", SEARCH_JSON_FILE, total)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def is_holiday_or_weekend(dt: datetime.date) -> bool:
    if dt.weekday() >= 5:
        return True
    return dt in holidays.country_holidays("KR", years=dt.year)


def check_dup_run() -> bool:
    today = datetime.date.today().isoformat()
    if LAST_RUN_FILE.exists() and LAST_RUN_FILE.read_text().strip() == today:
        return True
    LAST_RUN_FILE.write_text(today)
    return False


def main():
    today = datetime.date.today()
    log.info("=== Market Brief 시작: %s ===", today)

    if is_holiday_or_weekend(today):
        log.info("공휴일/주말 — 스킵")
        sys.exit(0)

    if check_dup_run():
        log.info("오늘 이미 실행됨 — 스킵")
        sys.exit(0)

    ym_list = get_ym_list(MONTHS_BACK)
    log.info("조회 월: %s", ym_list)

    log.info("--- 코인/환율 ---")
    try:
        send_telegram_chunked(get_coin_fx_message())
    except Exception as exc:
        log.error("코인/환율 오류: %s", exc)

    log.info("--- 선물지수 ---")
    try:
        send_telegram_chunked(get_futures_message())
    except Exception as exc:
        log.error("선물지수 오류: %s", exc)

    log.info("--- 아파트 신규거래 알림 ---")
    try:
        run_apartment_alerts(ym_list)
    except Exception as exc:
        log.error("아파트 알림 오류: %s", exc)

    log.info("--- 검색 JSON 생성 ---")
    try:
        generate_search_json(ym_list)
    except Exception as exc:
        log.error("검색 JSON 오류: %s", exc)

    log.info("=== 완료 ===")


if __name__ == "__main__":
    main()
