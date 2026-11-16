"""병합완료 확인 요청 파일 만들기(운영자 요청 2026-11-12) — 운영자가 병합 부탁을 병합한 뒤 '제대로 됐는지'만 짧게 알리는 `kind: merged` 요청 파일을 요청함에 쓴다.
(진행 현황 번호 P### 를 먹지 않는 별도 종류다 — 폰에는 정상이면 `[M050] 병합완료 확인 - 정상` 한 줄, 이상이면 그 줄 + 사유 한 줄 + 요청 열기 단추가 간다.)

사용: python -X utf8 make_merged_notice.py <R-번호|auto> <M번호> <정상|이상> ["이상 사유 한 줄"] [--folder 요청함 폴더] [--repo git 저장소|none] [--date YYYY-MM-DD] [--verify-with 저장소 작업 폴더 | --no-verify]
  R-번호   새 요청 번호 `R-266`. `auto` 면 요청함 폴더와 모든 원격 가지(origin/main·origin/ai/*)·로컬 가지의 `인수인계/요청함/` 파일 번호의 최댓값 + 1(make_info_request.py 를 부르는 쪽이 정하는 J3 와 같은 방법).
           번호를 직접 줄 때도 요청함 폴더나 어느 가지에든 같은 번호의 파일이 있으면 만들지 않는다.
  M번호    확인하는 **병합 부탁의 알림 번호**(`M050` 꼴, 표준 표기 — `M50`·`M0500` 은 거절). 요청함 폴더에 `kind: merge`·`no: M050` 인 요청 파일이 있어야 한다(짝 없는 병합완료 확인은 만들지 않는다).
           같은 M 번호의 병합완료 확인(`kind: merged`)이 이미 요청함 폴더나 어느 가지에 있으면 만들지 않는다. 이상을 알린 뒤 고친 결과(정상)는 둘째 병합완료 확인이 아니라 다른 알림(`info`)으로 보낸다 —
           알림은 push 에서 새로 더해진 파일만 고르므로 파일을 고치거나 이름만 바꿔서는 다시 가지 않는다.
  결과     `정상` 또는 `이상`. 이상이면 사유 한 줄이 필요하다(100자 이하, 줄 바꿈·링크 주소·물결표·비밀 모양·보이지 않는 글자·`병합완료 확인` 글자 금지, 앞뒤 공백 금지 — 값은 앞뒤 공백을 잘라 읽는다).
           정상은 사유를 생략하면 summary 가 `정상` 이다(주면 60자 이하). 사유에 도메인·전화번호·해시태그·광고 번호 모양의 글을 쓰지 않는다(폰이 링크·전화·태그로 바꿔 걸 수 있다).
           `정상`·`이상` 은 AI 가 병합이 끝난 뒤 **직접 확인한 결과를 적는 값**이다 — 이 도구는 병합 결과를 검사하지 않는다.
쓰는 곳: `--folder`(기본 `<이 파일이 있는 폴더>/wt_r30/인수인계/요청함`) 아래 `R-nnn_merged-m050.md`. 앞머리는 id·kind·title·summary·created·no·result 일곱 칸뿐이다(긴급도·pr·work·진행 현황 칸 없음) —
  title 은 정확히 `[M050] 병합완료 확인 - 정상` 이고 본문은 한 줄이다. 읽는 규칙은 pipeline/operator_loop.py(parse_request·notice_problem)·검증기 REQ-1 과 같다.
기본 검증(D2): 파일을 쓰기 **전에** 요청 가지 작업 폴더(`<이 파일이 있는 폴더>/wt_r30`)의 **그 코드 그대로**(pipeline.operator_loop 의 parse_request 엄격 읽기 + 짝·하나뿐 규칙 merged_pairing_problems)로 읽어 본다.
  그 코드가 `merged` 를 모르거나(요청 가지가 이 기능이 병합된 main 을 합치기 전 — 올려도 알림이 조용히 사라진다) 읽지 못하면 **파일을 만들지 않고** `요청 가지에 main 을 합치기 전입니다 — 먼저 합치세요` 로 멈춘다.
  `--verify-with 폴더` 는 다른 코드 폴더로 읽고, `--no-verify` 는 이 검증을 건너뛴다(시험 전용 — 실제 요청에는 쓰지 않는다).
이 도구는 네트워크를 쓰지 않는다 — 읽기 전에 요청 가지 작업 폴더(wt_r30)에서 `git fetch origin` 을 먼저 한다(가져오지 않은 가지의 번호·짝은 모른다). 푸시·커밋은 하지 않는다.
**병합 확인은 다른 요청과 따로 push 한다**(한 푸시에서는 3통까지만 보내고 나머지는 마지막 통의 `… 외 N건` 한 줄로만 알린다 — 다른 요청과 함께 올려 뒤로 밀리면 정상·이상 내용이 폰에 가지 않는다).
종료 코드: 0 만들었다 · 1 만들지 않았다(이유를 말한다) · 2 사용법 오류."""
import argparse
import datetime
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import next_notice_no as nn
import notice_tools as nt

HERE = Path(__file__).resolve().parent
LABEL = "병합완료 확인"
RESULTS = ("정상", "이상")
SUMMARY_LIMITS = {"정상": 60, "이상": 100}
NO_RE = re.compile(r"M(?:(?!000)[0-9]{3}|[1-9][0-9]{3})")                 # 병합 요청의 표준 알림 번호(pipeline/notify.NOTICE_NO_RE 의 M 꼴)
REQUEST_RE = re.compile(r"R-([0-9]{3})")
NAME_NUMBER_RE = re.compile(r"R-([0-9]{3})_")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
LINK_RE = re.compile(r"(?i)\b(?:https?|ftp|tg)://|www\.")
LABEL_COMPACT = "".join(LABEL.split())                                      # 사유에 이 글자(공백 없이)가 있으면 거절 — 코드(operator_loop.MERGED_LABEL_COMPACT)와 같은 규칙
BAD_CATEGORIES = nt.BAD_CATEGORIES


class Refuse(Exception):
    """만들지 않는 이유(사람에게 그대로 보인다)."""


def title_of(no, result):
    return f"[{no}] {LABEL} - {result}"


def reason_problem(text, limit):
    """사유·요약 한 줄을 요청 파일(과 폰)에 쓸 수 있는가 — 쓸 수 있으면 빈 글, 아니면 이유."""
    if not isinstance(text, str) or not text.strip():
        return "비어 있다"
    if text != text.strip():
        return "앞뒤에 공백이 있다"
    if len(text) > limit:
        return f"{len(text)}자라 {limit}자를 넘는다"
    for position, char in enumerate(text, 1):
        if char in nt.INVISIBLE or unicodedata.category(char) in BAD_CATEGORIES:
            return f"줄 바꿈·제어 문자·보이지 않는 글자가 있다(U+{ord(char):04X}, {position}번째 글자)"
    if text[0] == text[-1] and text[0] in "\"'" and len(text) >= 2:
        return "같은 따옴표로 시작하고 끝난다 — 읽을 때 따옴표가 벗겨져 쓴 글과 달라진다"
    if "~" in text:
        return "물결표(~)가 있다 — 마크다운이 두 개를 취소선으로 처리해 숫자가 붙어 보인다('–'나 '에서'로 쓴다)"
    if LINK_RE.search(text):
        return "링크 주소가 있다(요청 파일에 링크를 쓰지 않는다)"
    if LABEL_COMPACT in "".join(text.split()):
        return f"`{LABEL}` 글자가 있다 — 폰의 둘째 줄이 제목 줄처럼 읽혀 코드가 거절한다(사유에는 무엇이 이상한지만 쓴다)"
    if nt.looks_secret(text):
        return "비밀(키·토큰)로 보이는 글이 있다"
    return ""


def folder_files(folder):
    """요청함 폴더의 요청 파일 → [(이름, kind 값들, no 값들)] (읽을 수 없는 파일은 건너뛴다)."""
    found = []
    for path in sorted(Path(folder).iterdir()):
        if not path.is_file() or nn.NAME_RE.fullmatch(path.name) is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found.append((path.name, nn.front_values(text, "kind"), nn.front_values(text, "no")))
    return found


def scan_refs(repo):
    """origin/main·origin/ai/*·로컬 가지 모든 가지의 요청함 파일 → [(이름, 가지, kind 값들, no 값들)]. next_notice_no.read_git 과 같은 방법(`git for-each-ref` 한 번 +
    `git cat-file --batch` 두 번, 같은 커밋·같은 파일은 한 번만)이고 번호 칸이 없는 파일도 센다."""
    groups = {}
    for sha, kind, refname in sorted(nn.list_refs(repo, local=True), key=nn._ref_order):
        if kind == "commit":
            groups.setdefault(sha, []).append(nn.display_ref(refname))
    commits = list(groups)
    entries, names = {}, {}
    for sha, (kind, body) in zip(commits, nn.batch_read(repo, [f"{sha}:{nn.REQUEST_DIR}" for sha in commits]), strict=True):
        if kind != "tree":
            continue
        try:
            files = [(name, digest) for name, digest in nn.tree_files(body, len(sha) // 2) if nn.NAME_RE.fullmatch(name)]
        except ValueError:
            continue
        entries[sha] = files
        for name, digest in files:
            names.setdefault(digest, (name, groups[sha][0]))
    digests = sorted(names)
    info = {}
    for digest, (kind, body) in zip(digests, nn.batch_read(repo, digests), strict=True):
        text = body[:nn.READ_LIMIT].decode("utf-8", "replace") if kind == "blob" else ""
        info[digest] = (nn.front_values(text, "kind"), nn.front_values(text, "no"))
    return [(name, groups[sha][0], *info[digest]) for sha in commits for name, digest in sorted(entries.get(sha, ()))]


def request_number(name):
    found = NAME_NUMBER_RE.match(name)
    return int(found.group(1)) if found else 0


def decide_request_number(wanted, folder_found, ref_found):
    """새 요청 번호 글(`R-266`)과 설명. wanted 가 `auto` 면 최댓값 + 1, 아니면 모양·겹침을 본다. 만들 수 없으면 Refuse."""
    used = {request_number(name) for name, *_ in folder_found} | {request_number(name) for name, *_ in ref_found}
    used.discard(0)
    if wanted == "auto":
        top = max(used, default=0)
        if top >= 999:
            raise Refuse(f"요청 번호가 상한(R-999)에 닿았다(지금 최댓값 R-{top:03d})")
        return f"R-{top + 1:03d}", f"요청함 폴더와 모든 가지의 최댓값 R-{top:03d} + 1"
    found = REQUEST_RE.fullmatch(wanted)
    if found is None:
        raise Refuse(f"요청 번호가 `R-266` 꼴이 아니다(또는 auto): {wanted!r}")
    number = int(found.group(1))
    if number < 1:
        raise Refuse(f"요청 번호 {wanted} 는 범위 밖이다(R-001 부터)")
    if number in used:
        raise Refuse(f"요청 번호 {wanted} 를 쓸 수 없다 — 요청함 폴더나 어느 가지에 이미 있다(요청 번호는 모든 가지에서 겹치지 않아야 한다)")
    return wanted, f"직접 준 번호(요청함 폴더와 모든 가지에 없음, 지금 최댓값 R-{max(used, default=0):03d})"


def build_text(request_id, no, result, summary, created):
    body = ("정상 — 병합이 제대로 됐습니다(폰에는 위 제목 한 줄만 갑니다)." if result == "정상" else f"이상 — {summary}")
    return "\n".join(["---", f"id: {request_id}", "kind: merged", f"title: {title_of(no, result)}", f"summary: {summary}", f"created: {created}", f"no: {no}", f"result: {result}", "---", "", body, ""])


MAIN_FIRST = "요청 가지에 main 을 합치기 전입니다 — 먼저 합치세요"
VERIFY_SCRIPT = """import json
import sys
sys.path.insert(0, sys.argv[1])
try:
    from pipeline import operator_loop as ol
except Exception as exc:
    print("IMPORT " + type(exc).__name__ + ": " + str(exc)[:200])
    sys.exit(3)
data = json.load(sys.stdin)
labels = getattr(getattr(ol, "notify", None), "REQUEST_KIND_LABELS", {})
if "merged" not in labels or not hasattr(ol, "merged_pairing_problems"):
    print("UNKNOWN_KIND")
    sys.exit(4)
files = dict(data["files"])
files[data["name"]] = data["text"]
entries = []
for name in sorted(files):
    try:
        entries.append((name, ol.parse_request(name, files[name], strict=True)))
    except ol.RequestError as exc:
        if name == data["name"]:
            print("PARSE " + exc.code + " " + ol.problem_text(exc.code))
            sys.exit(5)
bad = [code for name, code in ol.merged_pairing_problems(entries) if name == data["name"]]
if bad:
    print("PAIR " + bad[0] + " " + ol.problem_text(bad[0]))
    sys.exit(6)
request = dict(entries)[data["name"]]
print(request.kind, request.no, dict(request.fields).get("result"), request.notice_error or "-")
"""


def verify_with(code_root, folder, name, text):
    """요청 가지 작업 폴더(code_root)의 **자기 코드**로 방금 만든 파일을 엄격하게(strict) 읽어 본다 — 그 코드의 pipeline.operator_loop.parse_request 와 짝·하나뿐 규칙(merged_pairing_problems, 검증기 REQ-1 이
    부르는 함수)을 요청함 폴더의 기존 파일과 함께 돌린다. 그 코드가 `merged` 를 모르면 MAIN_FIRST 로, 읽지 못하면 이유와 함께 Refuse(파일은 만들어지기 전이다). 별도 프로세스라 이 도구의 모듈과 섞이지 않는다."""
    code_root = Path(code_root)
    if not (code_root / "pipeline" / "operator_loop.py").is_file():
        raise Refuse(f"요청 가지 작업 폴더의 코드를 찾지 못했다: {code_root} — `--verify-with 폴더` 로 코드가 든 작업 폴더를 주거나(시험이면 `--no-verify`)")
    existing = {}
    for path in sorted(Path(folder).iterdir()):
        if path.is_file() and nn.NAME_RE.fullmatch(path.name) is not None:
            try:
                existing[path.name] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
    payload = json.dumps({"name": name, "text": text, "files": existing}, ensure_ascii=False).encode("utf-8")
    try:
        done = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", VERIFY_SCRIPT, str(code_root)], input=payload, capture_output=True, timeout=120, check=False, cwd=str(code_root))
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refuse(f"요청 가지 코드로 읽어 보지 못했다({type(exc).__name__}) — 만들지 않는다") from None
    out = done.stdout.decode("utf-8", "replace").strip()
    if done.returncode == 4:
        raise Refuse(f"{MAIN_FIRST} (그 코드({code_root})는 병합완료 확인 `kind: merged` 를 모른다 — 지금 올리면 알림이 조용히 사라진다)")
    if done.returncode:
        err_lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = out or (err_lines[-1] if err_lines else f"종료 코드 {done.returncode}")
        raise Refuse(f"요청 가지 코드({code_root})가 파일을 엄격하게 읽지 못했다: {detail[:300]}")
    return out


def make(request, no, result, reason, folder, repo, created, code_root=None):
    """검사를 모두 통과하면 파일을 쓰고 (경로, 설명 줄들)을 돌려준다. 아니면 Refuse. code_root 가 있으면 파일을 쓰기 전에 그 작업 폴더의 코드로 엄격하게 읽어 본다(None 이면 건너뜀 —
    main() 은 기본으로 요청 가지 작업 폴더를 넘기고 `--no-verify` 일 때만 None 을 넘긴다)."""
    if NO_RE.fullmatch(no) is None:
        raise Refuse(f"M 번호 모양이 아니다: {no!r} — 확인하는 병합 부탁의 알림 번호 `M050` 꼴(`M` + 세 자리 `001`–`999` 또는 네 자리 `1000`–`9999`, 앞에 0 을 더 붙인 `M0500` 은 번호가 아니다)")
    if result not in RESULTS:
        raise Refuse(f"결과는 `정상` 또는 `이상` 이어야 한다: {result!r}")
    if DATE_RE.fullmatch(created) is None:
        raise Refuse(f"날짜 모양이 아니다: {created!r}")
    try:
        datetime.date.fromisoformat(created)
    except ValueError:
        raise Refuse(f"없는 날짜다: {created!r}") from None
    if result == "이상" and (reason is None or not reason.strip()):
        raise Refuse("이상이면 무엇이 이상한지 사유 한 줄이 필요하다")
    summary = reason if reason is not None else "정상"
    problem = reason_problem(summary, SUMMARY_LIMITS[result])
    if problem:
        raise Refuse(f"summary(사유) 를 쓸 수 없다 — {problem}")
    folder = Path(folder)
    if not folder.is_dir():
        raise Refuse(f"요청함 폴더가 없다: {folder} — wt_r30 이 요청 가지로 준비돼 있는지 확인한다(인수인계/도구/README.md §1)")
    in_folder = folder_files(folder)
    in_refs = scan_refs(repo) if repo is not None else []
    # 짝 규칙: 같은 M 번호의 병합 부탁(`kind: merge`)이 이 요청함 폴더(= 요청 파일이 올라갈 트리)에 있어야 한다
    pairs = [name for name, kinds, nos in in_folder if kinds == ["merge"] and no in nos]
    if not pairs:
        elsewhere = sorted({f"{name} @ {ref}" for name, ref, kinds, nos in in_refs if kinds == ["merge"] and no in nos})
        hint = f" (다른 가지에는 있다: {', '.join(elsewhere[:3])} — 요청 가지를 그 가지와 합친 뒤 다시 한다)" if elsewhere else ""
        raise Refuse(f"짝이 되는 병합 부탁(`kind: merge`, `no: {no}`)이 요청함 폴더에 없다 — 짝 없는 병합완료 확인은 만들지 않는다{hint}")
    if len(pairs) > 1:
        raise Refuse(f"`no: {no}` 인 병합 부탁이 요청함 폴더에 둘 이상이다({', '.join(pairs)}) — 알림 번호가 겹쳐 있어 만들지 않는다")
    # 중복 규칙: 같은 M 번호의 병합완료 확인은 하나뿐이다(폴더 + 모든 가지)
    twins = sorted({name for name, kinds, nos in in_folder if kinds == ["merged"] and no in nos} | {f"{name} @ {ref}" for name, ref, kinds, nos in in_refs if kinds == ["merged"] and no in nos})
    if twins:
        raise Refuse(f"{no} 의 병합완료 확인이 이미 있다({', '.join(twins[:3])}) — 둘째는 만들지 않는다(이상을 알린 뒤 고친 결과는 다른 알림(info)으로 보낸다 — 알림은 새로 더해진 파일만 고르므로 파일을 고쳐서는 다시 가지 않는다)")
    request_id, how = decide_request_number(request, in_folder, in_refs)
    name = f"{request_id}_merged-{no.lower()}.md"
    if nn.NAME_RE.fullmatch(name) is None:
        raise Refuse(f"요청 파일 이름이 `R-001_짧은-영문-설명.md` 모양이 아니다: {name}")
    target = folder / name
    if target.exists():
        raise Refuse(f"이미 있다: {target}")
    text = build_text(request_id, no, result, summary, created)
    if "~" in text or LINK_RE.search(text):
        raise Refuse("만든 글에 물결표나 링크 주소가 있다(도구 오류) — 만들지 않는다")
    fields = nt.read_front(text)
    if (fields.get("id"), fields.get("kind"), fields.get("no"), fields.get("result"), fields.get("title")) != (request_id, "merged", no, result, title_of(no, result)):
        raise Refuse("만든 앞머리를 다시 읽은 값이 어긋난다(도구 오류) — 만들지 않는다")
    lines = [f"짝 병합 부탁: {pairs[0]} (kind: merge, no: {no})", f"요청 번호: {request_id} ({how})", f"제목: {title_of(no, result)}"]
    if code_root is not None:
        lines.append(f"요청 가지 코드로 엄격하게 읽기({Path(code_root).name}): " + verify_with(code_root, folder, name, text))
    else:
        lines.append("엄격하게 읽기 건너뜀(--no-verify — 시험 전용)")
    target.write_text(text, encoding="utf-8", newline="\n")
    lines.insert(0, f"파일 {name} | 줄 수 {text.count(chr(10))} | summary {len(summary)}자")
    lines.append("다음: 이 파일만 따로 commit·push 한다(한 푸시 3통 상한 — 다른 요청과 함께 올리면 뒤로 밀려 `… 외 N건` 한 줄로만 갈 수 있다)")
    return target, lines


def main(argv=None, *, workspace=None):
    parser = argparse.ArgumentParser(prog="make_merged_notice.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("request", help="새 요청 번호 R-266, 또는 auto(모든 가지의 최댓값 + 1)")
    parser.add_argument("no", help="확인하는 병합 부탁의 알림 번호 M050")
    parser.add_argument("result", help="정상 또는 이상")
    parser.add_argument("reason", nargs="?", default=None, help="이상일 때 사유 한 줄(정상이면 생략)")
    parser.add_argument("--folder", help="요청함 폴더(기본: <W>/wt_r30/인수인계/요청함)")
    parser.add_argument("--repo", help="원격 가지를 읽을 git 저장소(기본: <W>/wt_r30, none 이면 읽지 않는다)")
    parser.add_argument("--date", help="created 날짜(기본: 오늘)")
    check = parser.add_mutually_exclusive_group()
    check.add_argument("--verify-with", dest="verify_with", help="엄격하게 읽어 볼 코드가 든 저장소 작업 폴더(기본: <W>/wt_r30 — 요청 가지 작업 폴더)")
    check.add_argument("--no-verify", dest="no_verify", action="store_true", help="요청 가지 코드로 읽어 보는 기본 검증을 건너뜀(시험 전용)")
    args = parser.parse_args(argv)
    work = Path(workspace) if workspace is not None else HERE
    folder = Path(args.folder) if args.folder else work / "wt_r30" / "인수인계" / "요청함"
    repo = None if args.repo == "none" else (Path(args.repo) if args.repo else work / "wt_r30")
    created = args.date or datetime.date.today().isoformat()
    try:
        if repo is not None and not repo.is_dir():
            raise Refuse(f"git 저장소 폴더가 없다: {repo} (--repo none 으로 원격 가지 읽기를 건너뛸 수 있다)")
        try:
            code_root = None if args.no_verify else (Path(args.verify_with) if args.verify_with else work / "wt_r30")
            target, lines = make(args.request, args.no, args.result, args.reason, folder, repo, created, code_root)
        except nn.ScanError as exc:
            raise Refuse(f"git 에서 가지의 요청 파일을 읽지 못했다: {exc}") from None
    except Refuse as exc:
        print(f"만들지 않았다: {exc}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
