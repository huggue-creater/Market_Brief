# Market Brief — Claude Code Context

## 프로젝트 개요
평일 아침 06:20 KST GitHub Actions 자동 실행:
1. 텔레그램 3개 메시지 발송 (코인+환율 / 선물지수 / 아파트 신규신고)
2. `search_data.json` 생성 → `inject_data.py`로 `index.html`에 주입 → GitHub Pages 배포

- **레포**: https://github.com/huggue-creater/Market_Brief (public)
- **Pages URL**: https://huggue-creater.github.io/Market_Brief/
- **텔레그램 봇**: @market_brief_bot (chat_id: 7870789612)

---

## 행동 규칙
- 보안에 심각한 위험이 아닌 일반 명령은 확인 묻지 말고 바로 실행
- 대화는 한국어로

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `bot.py` | 메인 스크립트 (텔레그램 + API 크롤링 + JSON 생성) |
| `inject_data.py` | `search_data.json` → `index.html` 주입 |
| `index.html` | GitHub Pages 아파트 실거래 검색 SPA |
| `search_data.json` | 생성된 실거래 데이터 (Actions가 커밋) |
| `apt_state.json` | 아파트 신고 상태 추적 (중복 알림 방지) |
| `building_cache.json` | 건축물대장 API 캐시 |
| `last_run.txt` | 중복 실행 방지용 날짜 기록 |
| `.github/workflows/market_brief.yml` | GitHub Actions 워크플로우 |

---

## GitHub Secrets

| Secret | 용도 |
|--------|------|
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 7870789612 |
| `DATA_GO_KR_KEY` | data.go.kr API 키 (아파트 실거래 + 건축물대장) |

---

## 아파트 감시 지역
```python
REGIONS = [
    ("경기", "하남시", "망월동",  "41450"),
    ("경기", "용인시수지구", "상현동", "41465"),
    ("인천", "연수구", "연수동",   "28185"),
]
```
법정동코드: 하남 41450, 용인수지 41465, 인천연수 28185

---

## 주요 API

| 데이터 | API |
|--------|-----|
| 코인 (KRW 시세+24h) | Upbit REST |
| 코인 (USD 시세+24h) | CoinGecko |
| 환율 (USD/JPY) | Yahoo Finance (YAHOO_HEADERS 필수, query2 fallback) |
| 선물지수 (US500/Tech100/VIX/Nikkei/HangSeng) | Yahoo Finance |
| 아파트 실거래 | data.go.kr 국토교통부 실거래가 API (XML) |
| 건축물대장 | data.go.kr 건축물대장 API (준공연도, 용적률, 건폐율) |

**Yahoo Finance 주의**: `User-Agent` 헤더 없으면 403. `query1` 실패 시 `query2` fallback.

---

## search_data.json 형식
```json
{
  "generated_at": "YYYY-MM-DD HH:MM:SS",
  "months": ["202606","202605",...],
  "total": 500,
  "deals": [
    {
      "region": "하남 망월동",
      "apt": "미사역파크론",
      "area": 84.9917,
      "pyeong": 26,
      "floor": "24",
      "amount": 153000,
      "date": "2026-06-04",
      "direct": false,
      "canceled": false
    }
  ],
  "meta": {
    "미사역파크론": {"buildYear": 2020, "vlRat": "250", "bcRat": "20"}
  }
}
```
- `amount`: 만원 단위 정수
- `pyeong`: 공급평형 기준 (`area × 1.34 ÷ 3.3058` 반올림) — 59㎡→24평, 74㎡→30평, 84㎡→34평

---

## inject_data.py 마커
```html
// %%SEARCH_DATA_START%%
const SEARCH_DATA = null;
// %%SEARCH_DATA_END%%
```
Actions 실행 후 `null` 자리에 실제 JSON 주입됨.

---

## index.html 디자인 시스템
News 레포(huggue-creater/News) 스타일 그대로:
- 색상: `--paper:#F5F2EC` / `--ink:#1F1D1A` / `--seal:#B23A2E` / `--blue:#2F5A8F`
- 레이아웃: 타임라인 (날짜 원형 + 카드)
- SVG 스파크라인 (외부 라이브러리 없음)
- 시 칩 필터 + 동 멀티셀렉트 드롭다운
- 카드 클릭 → 이전 거래 이력 / 단지명 클릭 → 상세 뷰

---

## GitHub Actions 워크플로우
```
cron: '20 21 * * 0-4'   # 06:20 KST Mon-Fri (UTC Sun-Thu)
```
실행 순서: python bot.py → python inject_data.py → git commit → git push

---

## 알려진 이슈 / 주의사항
- **텔레그램 직접 테스트 불가**: 이 PC의 ISP가 api.telegram.org 차단. Actions에서는 정상 작동.
- **첫 실행 보호**: `apt_state.json`에 해당 지역이 없으면 알림 생략 (과거 데이터 폭탄 방지)
- **공휴일 처리**: 한국 공휴일은 Actions cron이 자동 스킵하지 않음 (추후 개선 가능)
- **last_run.txt 리셋**: 같은 날 재실행하려면 이 파일을 `2000-01-01`으로 변경 후 커밋
- **building_cache.json**: API 실패 시에도 `{}` 저장해서 재시도 방지 — 캐시 초기화 필요 시 `{}` 로 리셋
