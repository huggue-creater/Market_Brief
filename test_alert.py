#!/usr/bin/env python3
"""테스트: 각 지역 최신 거래 3건을 실제 알림 포맷으로 텔레그램 전송"""
import os, json, datetime, requests
from pathlib import Path

TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def send(text):
    resp = requests.get(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        params={"chat_id": CHAT_ID, "text": text},
        timeout=15,
    )
    ok = resp.json().get("ok")
    print("전송", "성공" if ok else f"실패: {resp.text}")

def fmt_krw(amount):
    eok, man = amount // 10000, amount % 10000
    if eok and man:
        return f"{eok}억 {man:,}만원"
    if eok:
        return f"{eok}억원"
    return f"{amount:,}만원"

data    = json.loads(Path("search_data.json").read_text(encoding="utf-8"))
today   = datetime.date.today().strftime("%Y-%m-%d")
regions = ["하남 망월동", "용인 상현동", "인천 연수동"]

for region in regions:
    deals = sorted(
        [d for d in data["deals"] if d["region"] == region and not d["canceled"]],
        key=lambda x: x["date"], reverse=True
    )[:3]

    if not deals:
        print(f"{region}: 데이터 없음")
        continue

    blocks = []
    for d in deals:
        block  = f"🏠 {d['apt']}\n"
        block += f"전용 {d['area']}㎡ ({d['pyeong']}평) · {d['floor']}층\n"
        block += f"거래가격 : {fmt_krw(d['amount'])}\n"
        block += f"거래일 : {d['date']}"
        blocks.append(block)

    msg = (
        f"[아파트 신규신고 - {region}]\n"
        f"{today} 기준 (테스트)\n\n"
        f"총 {len(deals)}건 신규\n\n"
        + "\n\n".join(blocks)
    )
    send(msg)
