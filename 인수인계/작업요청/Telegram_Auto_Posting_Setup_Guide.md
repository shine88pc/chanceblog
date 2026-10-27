# 🤖 GitHub Actions & 텔레그램 봇 알림 연동 가이드

> **확인 메모(2026-10-27, Claude)**: 시크릿 이름은 구현(`pipeline/notify.py`, 작업 TG)과 같습니다. 아래 샘플 코드·워크플로는 **쓰지 않습니다** — `requests` 는 Chance 워크플로에 설치돼 있지 않고, `parse_mode: Markdown` 은 AI 가 만든 제목의 `_`·`*`·`[` 때문에 400 오류가 날 수 있으며, `print(f"…{e}")` 는 요청 예외 문자열에 `…/bot<토큰>/sendMessage` 주소가 들어가 공개 Actions 로그로 토큰이 샐 수 있습니다. 구현·운영 안내는 `.github/editorial/TELEGRAM_SETUP.md`(작업 TG)를 따릅니다. 공개 저장소라 이 문서의 채팅 ID 값은 지웠습니다.

구글 블로거(Blogger) API 연동 및 GitHub Actions 포스팅 파이프라인 완료 시, 텔레그램 봇(`@chance_auto_post_bot`)을 통해 실시간 알림을 수신하기 위한 설정 가이드입니다.

---

## 1. 비밀 변수 (GitHub Secrets) 정보

GitHub 저장소의 **[Settings] ➔ [Secrets and variables] ➔ [Actions]** 경로로 이동하여 아래 두 키 값을 등록합니다.

* **`TELEGRAM_BOT_TOKEN`**: `@BotFather`에게 받은 API 토큰
* **`TELEGRAM_CHAT_ID`**: 내 텔레그램 채팅 ID(숫자) — 값은 저장소에 쓰지 않고 GitHub Secrets 에만 둔다

---

## 2. Python 알림 발송 코드 (`generator.py` 연동)

자동화 파이프라인 실행 완료 시 메시지를 전송하는 Python 함수 예시입니다.

```python
import os
import requests

def send_telegram_alert(message: str) -> None:
    """텔레그램 봇을 이용해 메시지를 전송합니다."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("[Telegram] Secrets 정보가 설정되지 않아 알림을 건너뜁니다.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        print("[Telegram] 알림 발송 완료!")
    except Exception as e:
        print(f"[Telegram] 알림 발송 실패: {e}")

if __name__ == "__main__":
    # 예시: 자동 포스팅 작업 완료 시 호출
    send_telegram_alert("🚀 *Chance_Blog* 새 포스팅 발행이 완료되었습니다!")
```

---

## 3. GitHub Actions 워크플로 설정 (`.github/workflows/deploy.yml`)

워크플로 실행 시 GitHub Secrets를 파이썬 환경변수로 전달하도록 설정합니다.

```yaml
name: Auto Posting Workflow

on:
  schedule:
    - cron: '0 0 * * *'  # 매일 정해진 시간에 실행
  workflow_dispatch:      # 수동 실행 허용

jobs:
  build-and-post:
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Run Auto Post Generator
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          python generator.py
```