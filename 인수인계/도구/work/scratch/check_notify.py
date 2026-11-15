"""알림 워크플로(ai-request.yml)가 주어진 R 번호 커밋에 대해 끝났는지 공개 웹 페이지로 확인한다(GitHub REST 호출 0회 — 시간당 60회 한도를 쓰지 않는다).
사용: python -X utf8 check_notify.py R-211
요청 파일을 요청 가지에 push 한 뒤 알림 워크플로 실행이 끝나기를 최대 110초 기다리며 8초마다 목록을 읽는다. 끝나면 실행 번호·상태·소요 시간·주석(refused·경고 같은 알림 거절 사유)을 한 줄로 보인다.
주석에 'refused' 나 경고가 없고 실행 시간이 8–11초이면 알림이 간 것으로 본다. 읽기 전용이고 비밀을 쓰지 않는다(공개 페이지만 읽는다)."""
import html
import re
import sys
import time
import urllib.request

REPO = "shine88pc/chanceblog"
BASE = f"https://github.com/{REPO}"
WORKFLOW_PAGE = "actions/workflows/ai-request.yml"
UA = {"User-Agent": "Mozilla/5.0 (chanceblog-check-notify)"}
WAIT_SECONDS = 110
POLL_SECONDS = 8
DONE = "WORKFLOW_RUN_STATUS_COMPLETED"


def fetch(url, ajax=False, timeout=40):
    """공개 웹 페이지를 글로 읽는다 — 실패하면 예외를 던지지 않고 `__ERR__ …` 글을 돌려준다."""
    headers = dict(UA)
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"__ERR__ {type(exc).__name__}: {exc}"


def text_of(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def annotations(run_id):
    """한 실행의 주석(검사 요약·경고) 글 — 공개 웹의 부분 페이지에서 읽는다."""
    raw = fetch(f"{BASE}/actions/runs/{run_id}/annotations_partial", ajax=True)
    txt = text_of(raw)
    txt = re.sub(r"Show (more|less)", "", txt)
    txt = re.sub(r"\"The ubuntu-latest label will migrate[^\"]*\"", "", txt)
    return re.sub(r"\s+", " ", txt).strip()


def find_run(page, tag):
    """워크플로 페이지 글에서 제목에 tag(예: `R-211`)가 든 첫 실행 — (실행 id, 상태, 결론|None, 소요 글, 실행 번호) 또는 None."""
    for match in re.finditer(r'"runNumber":(\d+),"id":"(\d+)"', page):
        seg = page[match.start(): match.start() + 1500]
        title = re.search(r'"title":"([^"]*)"', seg)
        status = re.search(r'"status":"([A-Z_]+)"', seg)
        if title and status and tag in title.group(1):
            concl = re.search(r'"conclusion":"([A-Z_]+)"', seg)
            dur = re.search(r'"timing":\{"kind":"[A-Z_]+","text":"([^"]*)"', seg)
            return (match.group(2), status.group(1), concl.group(1) if concl else None, dur.group(1) if dur else "", match.group(1))
    return None


def summary_line(last, notes):
    """끝난 실행 한 줄 — 상태·결론 앞의 고정 접두사를 떼어 짧게 보인다."""
    return "run #%s %s %s %s | annotations: %s" % (last[4], last[1].replace("WORKFLOW_RUN_STATUS_", ""), (last[2] or "").replace("WORKFLOW_RUN_CONCLUSION_", ""), last[3], notes[:160])


def main(argv=None, *, now=time.time, sleep=time.sleep):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(__doc__)
        return 2
    tag = argv[0]
    deadline = now() + WAIT_SECONDS
    last = None
    while now() < deadline:
        found = find_run(fetch(f"{BASE}/{WORKFLOW_PAGE}"), tag)
        if found:
            last = found
        if last and last[1] == DONE:
            print(summary_line(last, annotations(last[0])))
            return 0
        sleep(POLL_SECONDS)
    print("아직 끝나지 않음:", last)
    return 0                       # 옛 도구와 같다: 끝나지 않았어도 종료 코드는 0(읽은 줄이 결과다)


if __name__ == "__main__":
    sys.exit(main())
