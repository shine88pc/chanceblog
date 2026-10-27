"""임시 브랜치(ai/claude/tg-note-*)에서 메모 파일의 글을 텔레그램으로 한 통 보낸다. main 에 병합하지 않는 일회용이다.

사용: python tg_note/send.py tg_note/58_review.txt
메모 형식: `# 제목`·`## 소제목` 줄은 굵게, 나머지는 글자 그대로(HTML 이스케이프), `[버튼] 라벨 | 주소` 줄은 버튼(pipeline.notify 의 허용 주소만).
토큰·채팅 ID 는 환경변수(TELEGRAM_BOT_TOKEN·TELEGRAM_CHAT_ID)에서만 읽고 어디에도 쓰지 않는다 — 전송은 pipeline.notify.Notifier 가 하며
토큰 비노출·통 수 상한·실패 격리 규칙을 그대로 따른다. 시크릿이 없거나 전송이 실패해도 종료 코드는 0(::notice::·::warning:: 한 줄).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import notify  # noqa: E402


def load(path):
    """메모 파일 → (HTML 본문, [(라벨, 주소), ...])."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    lines, buttons = [], []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("[버튼]"):
            label, _, url = line[len("[버튼]"):].partition("|")
            buttons.append((label.strip(), url.strip()))
        elif line.startswith("## "):
            lines.append("<b>" + notify.escape_html(line[3:]) + "</b>")
        elif line.startswith("# "):
            lines.append("<b>" + notify.escape_html(line[2:]) + "</b>")
        else:
            lines.append(notify.escape_html(line))
    return "\n".join(lines).strip(), buttons


def main(argv=None, environ=None, notifier=None, out=print):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        out("사용법: python tg_note/send.py <메모 파일>")
        return 2
    text, buttons = load(argv[0])
    result = (notifier or notify.Notifier(environ)).send_message(text, parse_mode="HTML", buttons=buttons)
    if result.sent:
        out("::notice::텔레그램 메모를 보냈습니다")
    elif result.reason == notify.DISABLED:
        out("::notice::텔레그램 시크릿이 없어 메모를 보내지 않았습니다")
    else:
        out(f"::warning::텔레그램 메모를 보내지 못했습니다 — {notify.describe(result)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
