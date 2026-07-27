@echo off
REM ── 네이버 매물 수집 로컬 런처 (Windows 작업 스케줄러용) ──
REM   반드시 가정용 IP(이 PC)에서 실행. 수집 후 스냅샷/이벤트 커밋·푸시.
REM   작업 스케줄러: "작업 실행을 위해 컴퓨터의 절전 모드 해제" 체크 권장.

cd /d "%~dp0"

echo [%date% %time%] 네이버 매물 수집 시작
python naver_collect.py
if errorlevel 1 (
  echo [ERROR] 수집 실패 - 커밋 생략
  exit /b 1
)

git add naver_snapshot.json naver_events.json
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "chore: 네이버 매물 스냅샷 %date%"
  git push
  echo [%date% %time%] 커밋/푸시 완료
) else (
  echo 변동 없음 - 커밋 생략
)
