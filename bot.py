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

# ── Logging ───────────────────────────────────────────────────────────────────
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
YAHOO_URL2     = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"

MONTHS_BACK    = 6
RETRY_COUNT    = 4
RETRY_DELAYS   = [2, 4, 8, 16]
TELEGRAM_LIMIT = 3800

YAHOO_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

STATE_FILE          = Path("apt_state.json")
CACHE_FILE          = Path("building_cache.json")
SEARCH_JSON_FILE    = Path("search_data.json")
REPORTED_DATES_FILE = Path("reported_dates.json")
LAST_RUN_FILE       = Path("last_run.txt")

# ── Region definitions ────────────────────────────────────────────────────────
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
    {"city": "하남", "name": "선동",   "lawd": "41450", "bjdong": None,    "dong": "선동",   "telegram": False},
    {"city": "하남", "name": "미사동", "lawd": "41450", "bjdong": None,    "dong": "미사동", "telegram": False},
    {"city": "하남", "name": "위례동", "lawd": "41450", "bjdong": None,    "dong": "위례동", "telegram": False},
    # ── 시흥 ──
    {"city": "시흥", "name": "정왕동", "lawd": "41390", "bjdong": "13200", "dong": "정왕동", "telegram": False},
]


# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def http_get(url: str, params: dict = None, headers: dict = None,
             timeout: int = 15) -> Optional[requests.Response]:
    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            wait = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            log.warning("GET %s attempt %d/%d: %s — retry in %ds",
                        url.split("?")[0][:60], attempt + 1, RETRY_COUNT, exc, wait)
            if attempt < RETRY_COUNT - 1:
                time.sleep(wait)
    log.error("GET %s 최종 실패", url.split("?")[0][:60])
    return None


def yahoo_get(symbol: str) -> Optional[dict]:
    """Yahoo Finance 조회 (query1 → query2 fallback). meta dict 반환."""
    params = {"interval": "1d", "range": "5d"}
    for base in (YAHOO_URL, YAHOO_URL2):
        resp = http_get(base.format(symbol=symbol), params=params, headers=YAHOO_HEADERS)
        if not resp:
            continue
        try:
            result = resp.json()["chart"]["result"]
            if result:
                return result[0]["meta"]
        except Exception as exc:
            log.warning("Yahoo parse %s: %s", symbol, exc)
    return None


def send_telegram(text: str) -> bool:
    url    = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    resp   = http_get(url, params=params)
    if resp and resp.ok:
        return True
    log.error("Telegram 전송 실패: %s", resp.text if resp else "no response")
    return False


def send_telegram_chunked(text: str) -> bool:
    if len(text) <= TELEGRAM_LIMIT:
        return send_telegram(text)
    lines, chunk, parts = text.split("\n"), [], []
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
        y, m = today.year, today.month - i
        while m <= 0:
            m += 12; y -= 1
        result.append(f"{y}{m:02d}")
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
    try:
        val = int(str(amount).replace(",", ""))
        eok, man = val // 10000, val % 10000
        if eok and man:
            return f"{eok}억 {man:,}만원"
        if eok:
            return f"{eok}억원"
        return f"{val:,}만원"
    except Exception:
        return str(amount)


def to_pyeong(area_str: str) -> int:
    try:
        return round(float(area_str) * 1.34 / 3.3058)
    except Exception:
        return 0


def price_val(t: dict) -> int:
    try:
        return int(str(t.get("dealAmount", "0")).replace(",", ""))
    except Exception:
        return 0


def trade_date_int(t: dict) -> int:
    try:
        return int(f"{t.get('dealYear','0')}"
                   f"{int(t.get('dealMonth', 1)):02d}"
                   f"{int(t.get('dealDay', 1)):02d}")
    except Exception:
        return 0


def short_date(t: dict) -> str:
    """26.05.22 형태"""
    try:
        y = str(t.get("dealYear", ""))[-2:]
        m = int(t.get("dealMonth", 1))
        d = int(t.get("dealDay", 1))
        return f"{y}.{m:02d}.{d:02d}"
    except Exception:
        return ""


def trade_id(t: dict) -> str:
    return "|".join([
        t.get("umdNm", ""), t.get("aptNm", ""),
        t.get("dealYear", ""), t.get("dealMonth", ""), t.get("dealDay", ""),
        t.get("excluUseAr", ""), t.get("floor", ""), t.get("dealAmount", ""),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Feature 1 — 코인 + 환율
# ══════════════════════════════════════════════════════════════════════════════

COIN_NAMES = {"BTC": "비트코인", "ETH": "이더리움", "XRP": "리플"}
CG_IDS     = {"BTC": "bitcoin", "ETH": "ethereum", "XRP": "ripple"}

def get_coin_fx_message() -> str:
    coins = ["BTC", "ETH", "XRP"]

    # Upbit: 현재가 + 24h 변동
    upbit_data: dict = {}
    resp = http_get(UPBIT_URL, params={"markets": ",".join(f"KRW-{c}" for c in coins)})
    if resp:
        for item in resp.json():
            ticker = item["market"].replace("KRW-", "")
            upbit_data[ticker] = item  # trade_price, signed_change_rate, change

    # CoinGecko: USD 현재가 + 24h 변동
    usd_data: dict = {}
    resp = http_get(COINGECKO_URL, params={
        "ids": ",".join(CG_IDS.values()),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    })
    if resp:
        raw = resp.json()
        for ticker, cg_id in CG_IDS.items():
            if cg_id in raw:
                usd_data[ticker] = raw[cg_id]

    # 환율
    usdkrw, jpykrw = None, None
    meta_usd = yahoo_get("USDKRW=X")
    if meta_usd:
        usdkrw = meta_usd.get("regularMarketPrice")
    meta_jpy = yahoo_get("JPY=X")
    if meta_jpy and usdkrw:
        jpyusd = meta_jpy.get("regularMarketPrice")
        if jpyusd:
            jpykrw = usdkrw / jpyusd

    lines = []
    for c in coins:
        up  = upbit_data.get(c, {})
        usd = usd_data.get(c, {})

        krw_price = up.get("trade_price")
        krw_rate  = up.get("signed_change_rate", 0)  # 0.0033 형태
        krw_chg   = up.get("change", "EVEN")          # "RISE"/"FALL"/"EVEN"

        usd_price = usd.get("usd")
        usd_rate  = usd.get("usd_24h_change", 0)

        krw_arrow = "▲" if krw_chg == "RISE" else ("▼" if krw_chg == "FALL" else "-")
        usd_arrow = "▲" if (usd_rate or 0) >= 0 else "▼"

        lines.append(f"[{COIN_NAMES[c]}]")

        if krw_price:
            lines.append(f"🇰🇷 {krw_arrow} {krw_price:,.0f} ({krw_rate*100:+.2f}%)")
        else:
            lines.append("🇰🇷 데이터 없음")

        if usd_price:
            lines.append(f"🇺🇸 {usd_arrow} {usd_price:,.2f} ({usd_rate:+.2f}%)")
        else:
            lines.append("🇺🇸 데이터 없음")

        if krw_price and usd_price and usdkrw:
            kimp = (krw_price / (usd_price * usdkrw) - 1) * 100
            lines.append(f"김프 : ({kimp:+.2f}%)")

        lines.append("")  # 빈 줄

    if usdkrw:
        lines.append(f"달러환율: {usdkrw:,.2f}원")
    if jpykrw:
        lines.append(f"엔화환율(100엔) : {jpykrw * 100:,.2f}원")

    return "\n".join(lines).strip()


# ══════════════════════════════════════════════════════════════════════════════
# Feature 2 — 선물지수
# ══════════════════════════════════════════════════════════════════════════════

FUTURES = [
    ("ES=F",  "🇺🇸 US 500"),
    ("NQ=F",  "🇺🇸 US Tech 100"),
    ("^VIX",  "📊 S&P 500 VIX"),
    ("^N225", "🇯🇵 Nikkei 225"),
    ("^HSI",  "🇭🇰 Hang Seng"),
]

def get_futures_message() -> str:
    lines = ["[선물지수]"]
    for symbol, label in FUTURES:
        meta = yahoo_get(symbol)
        if not meta:
            lines.append(f"\n{label}\n데이터 없음")
            continue
        try:
            price = meta["regularMarketPrice"]
            prev  = (meta.get("chartPreviousClose")
                     or meta.get("previousClose")
                     or meta.get("regularMarketPreviousClose"))
            lines.append(f"\n{label}")
            if prev:
                chg = price - prev
                pct = chg / prev * 100
                sig = "▲" if chg >= 0 else "▼"
                lines.append(f"{price:,.2f} {sig} {abs(chg):+,.2f} ({pct:+.2f}%)")
            else:
                lines.append(f"{price:,.2f}")
        except Exception as exc:
            log.warning("Futures parse %s: %s", symbol, exc)
            lines.append(f"\n{label}\n파싱 오류")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Apartment trade collection
# ══════════════════════════════════════════════════════════════════════════════

def fetch_apt_trades_month(lawd: str, ym: str) -> list:
    all_items, page = [], 1
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
            log.error("  fetch_apt_trades lawd=%s ym=%s page=%d 실패", lawd, ym, page)
            break
        try:
            root  = ElementTree.fromstring(resp.text)
            items = root.findall(".//item")
            if not items:
                break
            for item in items:
                d = {c.tag: (c.text or "").strip() for c in item}
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
    dong, lawd, name = region["dong"], region["lawd"], region["name"]
    all_trades = []
    for ym in ym_list:
        try:
            trades      = fetch_apt_trades_month(lawd, ym)
            dong_trades = [t for t in trades if t.get("umdNm", "").strip() == dong]
            log.info("  %s: %s → %d건", name, ym, len(dong_trades))
            all_trades.extend(dong_trades)
        except Exception as exc:
            log.error("  %s %s 오류: %s", name, ym, exc)
    return all_trades


# ══════════════════════════════════════════════════════════════════════════════
# Feature 3 — 아파트 신규거래 알림
# ══════════════════════════════════════════════════════════════════════════════

def _build_telegram_apt_msg(region: dict, new_trades: list,
                             known_ids: set, all_trades: list) -> str:
    city = region["city"]
    name = region["name"]
    today = datetime.date.today().strftime("%Y-%m-%d")

    # 기존(알려진) 비취소 거래의 가격·날짜 이력 구축
    # unit_history: (apt, area) → [(price_int, short_date_str, trade)]  (날짜순)
    unit_history: dict = {}
    for t in sorted(
        [t for t in all_trades if trade_id(t) in known_ids and t.get("cdealType") != "Y"],
        key=trade_date_int
    ):
        key = (t.get("aptNm", ""), t.get("excluUseAr", ""))
        unit_history.setdefault(key, []).append((price_val(t), short_date(t)))

    new_high_count = 0
    blocks = []

    for t in sorted(new_trades, key=trade_date_int):
        apt       = t.get("aptNm", "")
        area      = t.get("excluUseAr", "")
        floor_    = t.get("floor", "")
        cur       = price_val(t)
        cancelled = t.get("cdealType") == "Y"
        direct    = "직" in (t.get("dealingGbn") or "")
        pyeong    = to_pyeong(area)

        key     = (apt, area)
        history = unit_history.get(key, [])  # [(price, date), ...]

        # 이전 최고가 / 직전 실거래
        prev_max_price, prev_max_date = None, None
        prev_last_price, prev_last_date = None, None
        if history:
            prev_last_price, prev_last_date = history[-1]
            max_entry = max(history, key=lambda x: x[0])
            prev_max_price, prev_max_date = max_entry

        is_new_high = (not cancelled) and (prev_max_price is None or cur > prev_max_price)
        if is_new_high:
            new_high_count += 1

        apt_label = f"🏠 {apt}"
        if is_new_high:
            apt_label += " 🔥 신고가"
        elif cancelled:
            apt_label += " ❌ 취소"
        if direct and not cancelled:
            apt_label += " 🤝 직거래"

        block = [apt_label]
        block.append(f"전용 {area}㎡ ({pyeong}평) · {floor_}층")
        block.append(f"거래가격 : {fmt_krw(cur)}")
        block.append(f"계약일 : {short_date(t)}")

        if prev_last_price and prev_last_date:
            block.append(f"직전 실거래 : {fmt_krw(prev_last_price)} ({prev_last_date})")

        if prev_max_price and prev_max_date:
            block.append(f"이전 최고가 : {fmt_krw(prev_max_price)} ({prev_max_date})")
            if not is_new_high and cur > 0:
                pct = cur / prev_max_price * 100
                block.append(f"전고점 대비 : {pct:.1f}%")

        blocks.append("\n".join(block))

    total = len(new_trades)
    header = (f"[아파트 신규신고 - {city} {name}]\n"
              f"{today} 기준\n\n"
              f"총 {total}건 신규" +
              (f" · 🔥 신고가 {new_high_count}건" if new_high_count else ""))

    return header + "\n\n" + "\n\n".join(blocks)


def run_apartment_alerts(ym_list: list):
    state          = load_json(STATE_FILE, {})
    reported_dates = load_json(REPORTED_DATES_FILE, {})
    today_str      = datetime.date.today().isoformat()

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
                for t in new_trades:
                    reported_dates[trade_id(t)] = today_str

            new_ids    = {trade_id(t) for t in all_trades}
            state[name] = list(set(state.get(name, [])) | new_ids)
        except Exception as exc:
            log.error("  %s 알림 오류: %s", name, exc)

    save_json(STATE_FILE, state)
    save_json(REPORTED_DATES_FILE, reported_dates)


# ══════════════════════════════════════════════════════════════════════════════
# Building registry cache
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_building_info(sigungu: str, bjdong: str) -> dict:
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
            d  = {c.tag: (c.text or "").strip() for c in item}
            nm = d.get("bldNm", "")
            if nm:
                result[nm] = {"vlRat": d.get("vlRat", ""), "bcRat": d.get("bcRat", "")}
        return result
    except Exception as exc:
        log.warning("Building parse %s/%s: %s", sigungu, bjdong, exc)
        return {}


def update_building_cache() -> dict:
    cache, changed = load_json(CACHE_FILE, {}), False
    for region in REGIONS:
        bjdong = region.get("bjdong")
        if not bjdong:
            continue
        key = f"{region['lawd']}|{bjdong}"
        if key in cache:
            continue
        log.info("  건축물대장: %s 조회...", region["name"])
        cache[key] = _fetch_building_info(region["lawd"], bjdong)
        changed = True
        time.sleep(0.3)
    if changed:
        save_json(CACHE_FILE, cache)
    return cache


# ══════════════════════════════════════════════════════════════════════════════
# Feature 4 — 검색 JSON 생성
# ══════════════════════════════════════════════════════════════════════════════

def generate_search_json(ym_list: list):
    log.info("=== 검색 JSON 생성 ===")

    reported_dates = load_json(REPORTED_DATES_FILE, {})

    existing = load_json(SEARCH_JSON_FILE, {})
    existing_reported: dict = {}
    for d in existing.get("deals", []):
        area_v = d.get("area", 0.0)
        k = f"{d.get('apt','')}|{d.get('date','')}|{area_v:.4f}|{d.get('amount',0)}|{d.get('floor','')}"
        if d.get("reported_date"):
            existing_reported[k] = d["reported_date"]
    today_str = datetime.date.today().isoformat()

    building_cache = update_building_cache()
    all_deals: list = []
    meta_map:  dict = {}  # aptNm → {buildYear, vlRat, bcRat}

    for region in REGIONS:
        name         = region["name"]
        city         = region["city"]
        region_label = f"{city} {name}"
        log.info("[검색JSON] %s...", name)
        try:
            trades    = collect_trades_for_region(region, ym_list)
            cache_key = f"{region['lawd']}|{region['bjdong']}" if region.get("bjdong") else None
            dong_bld  = building_cache.get(cache_key, {}) if cache_key else {}

            for t in trades:
                apt      = t.get("aptNm", "")
                area_str = t.get("excluUseAr", "0")
                try:
                    area = round(float(area_str), 4)
                except Exception:
                    area = 0.0

                try:
                    amount = int(t.get("dealAmount", "0").replace(",", ""))
                except Exception:
                    amount = 0

                y = t.get("dealYear", "2000")
                m = t.get("dealMonth", "1").zfill(2)
                d = t.get("dealDay",   "1").zfill(2)
                deal_date = f"{y}-{m}-{d}"
                deal_key  = f"{apt}|{deal_date}|{area:.4f}|{amount}|{t.get('floor', '')}"
                reported_date = (
                    reported_dates.get(trade_id(t)) or
                    existing_reported.get(deal_key) or
                    deal_date
                )

                all_deals.append({
                    "region":        region_label,
                    "apt":           apt,
                    "area":          area,
                    "pyeong":        to_pyeong(area_str),
                    "floor":         t.get("floor", ""),
                    "amount":        amount,
                    "date":          deal_date,
                    "reported_date": reported_date,
                    "direct":        "직" in (t.get("dealingGbn") or ""),
                    "canceled":      t.get("cdealType") == "Y",
                })

                # 단지 메타 (최초 1회만 저장)
                if apt and apt not in meta_map:
                    by = t.get("buildYear", "")
                    bld = dong_bld.get(apt, {})
                    meta_map[apt] = {
                        "buildYear": int(by) if by.isdigit() else None,
                        "vlRat":     bld.get("vlRat", ""),
                        "bcRat":     bld.get("bcRat", ""),
                    }

            log.info("  %s: %d건", name, len(trades))
        except Exception as exc:
            log.error("  %s 오류: %s", name, exc)

    total = len(all_deals)
    if total == 0:
        log.warning("수집 0건 — 기존 JSON 보존")
        return

    save_json(SEARCH_JSON_FILE, {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "months":       ym_list,
        "total":        total,
        "deals":        all_deals,
        "meta":         meta_map,
    })
    log.info("검색 JSON 저장: %d건", total)


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

    log.info("--- 아파트 알림 ---")
    try:
        run_apartment_alerts(ym_list)
    except Exception as exc:
        log.error("아파트 알림 오류: %s", exc)

    log.info("--- 검색 JSON ---")
    try:
        generate_search_json(ym_list)
    except Exception as exc:
        log.error("검색 JSON 오류: %s", exc)

    log.info("=== 완료 ===")


if __name__ == "__main__":
    main()
