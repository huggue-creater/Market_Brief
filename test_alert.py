#!/usr/bin/env python3
"""테스트: 각 지역 최신 3건을 실제 봇 포맷으로 텔레그램 전송"""
import sys
sys.path.insert(0, ".")

from bot import (
    collect_trades_for_region, get_ym_list, trade_id, trade_date_int,
    _build_telegram_apt_msg, send_telegram_chunked, REGIONS, MONTHS_BACK,
)

ym_list = get_ym_list(MONTHS_BACK)

for region in [r for r in REGIONS if r["telegram"]]:
    name = region["name"]
    print(f"[{name}] 수집 중...")

    all_trades = collect_trades_for_region(region, ym_list)
    valid = sorted(
        [t for t in all_trades if t.get("cdealType") != "Y"],
        key=trade_date_int,
    )

    if len(valid) < 4:
        print(f"  {name}: 데이터 부족 ({len(valid)}건)")
        continue

    # 최신 3건 → 신규, 나머지 → 이력(직전 실거래/이전 최고가 계산용)
    new_trades = valid[-3:]
    known_ids  = {trade_id(t) for t in valid[:-3]}

    msg = _build_telegram_apt_msg(region, new_trades, known_ids, all_trades)
    send_telegram_chunked(msg)
    print(f"  {name}: 전송 완료")
