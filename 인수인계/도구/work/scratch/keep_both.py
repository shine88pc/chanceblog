"""squash_onto.py 가 남긴 충돌 표시(<<<<<<< / ======= / >>>>>>>)를 '양쪽 절을 모두 남기는' 방식으로 푼다(총괄 전용).
쓰는 때: 두 갈래가 같은 문서 끝에 각자 새 절을 덧붙여 생긴 충돌(문서)만 — 코드 충돌에는 쓰지 않는다.
사용: py -3.12 -X utf8 C:/work/ai/scratch/keep_both.py <작업 나무> <파일1> [<파일2> ...]
하는 일: 각 파일의 충돌 덩어리마다 앞쪽(HEAD) 줄 뒤에 빈 줄 하나를 두고 뒤쪽 줄을 이어 붙이고 표시 줄을 지운다. 줄 끝(CRLF/LF)은 파일 그대로.
  두 쪽에 같은 줄이 겹치면(덧붙이기만이 아니라는 신호) 경고를 내고 해당 파일은 건드리지 않는다(--force 면 그래도 푼다).
끝에 `git add` 는 하지 않는다 — 결과를 눈으로 본 뒤 직접 한다."""
import sys


def resolve(path, force=False):
    raw = open(path, "rb").read().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    out, ours, theirs, state, hunks = [], [], [], 0, 0
    for ln in lines:
        if state == 0 and ln.startswith("<<<<<<< "):
            state, ours, theirs = 1, [], []
            continue
        if state == 1 and ln == "=======":
            state = 2
            continue
        if state == 2 and ln.startswith(">>>>>>> "):
            both = set(x for x in ours if x.strip()) & set(x for x in theirs if x.strip())
            if both and not force:
                # 표 머리·구분선처럼 흔한 줄은 겹쳐도 덧붙이기일 수 있다 — 사람이 보게 경고만 내고 멈춘다
                print(f"경고: {path} 충돌 덩어리 {hunks + 1} 의 두 쪽에 같은 줄이 {len(both)}개 있다 — 덧붙이기만이 아닐 수 있어 풀지 않았다(--force 로 강제).")
                for x in list(both)[:3]:
                    print("   겹침:", x[:100])
                return False
            out.extend(ours)
            if ours and ours[-1].strip():
                out.append("")
            out.extend(theirs)
            state, hunks = 0, hunks + 1
            continue
        if state == 1:
            ours.append(ln)
        elif state == 2:
            theirs.append(ln)
        else:
            out.append(ln)
    if state != 0:
        print(f"오류: {path} 충돌 표시가 닫히지 않았다")
        return False
    txt = nl.join(out)
    if "<<<<<<<" in txt or ">>>>>>>" in txt:
        print(f"오류: {path} 에 충돌 표시가 남았다")
        return False
    open(path, "wb").write(txt.encode("utf-8"))
    print(f"해결: {path} (덩어리 {hunks}개, 줄 끝 {nl!r})")
    return True


def main(argv):
    force = "--force" in argv
    args = [a for a in argv if a != "--force"]
    if len(args) < 2:
        print(__doc__)
        return 2
    tree, files = args[0], args[1:]
    ok = True
    for f in files:
        ok = resolve(f"{tree}/{f}", force) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
