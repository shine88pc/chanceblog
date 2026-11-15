"""편집 1 — 머리·§0 머리말·0-1 덧붙임·0-2(15번 정정·17·18번 추가)·0-3 다시 쓰기. 작업 폴더의 인수인계/작업내용.md 한 파일."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docedit import CRLF, Doc, crlf, read_block  # noqa: E402

WT = "C:/work/ai/improve_wt_worklog12"
BLK = "C:/work/ai/audit6/improve/worklog12/blocks/"
doc = Doc(WT + "/인수인계/작업내용.md")

# 1. 머리 '마지막 갱신'
doc.replace_once(
    "> 마지막 갱신: **2026-11-13 09시 08분(KST) — 11-10 12시 40분 이후 사흘치 현행화",
    read_block(BLK + "b01_header_last.txt") + "11-10 12시 40분 이후 사흘치 현행화",
    "머리 마지막 갱신")

# 2. 머리 기준
doc.replace_once(
    "갱신자: Claude · 기준: 블로그(이 저장소) `main` 6c39942",
    read_block(BLK + "b02_header_base.txt"),
    "머리 기준")

# 3. §0 제목 괄호
doc.replace_once(
    "0-1·0-2·0-3·0-4·0-5·0-6 은 2026-11-13 09시 08분 갱신)",
    "0-1·0-2·0-3·0-4·0-5·0-6 은 2026-11-13 09시 08분 갱신을 거쳐 같은 날 @@END_HM@@ 에 다시 갱신 — 새 0-7 은 소통 방식이 바뀐 뒤의 '혼자 이어 가는 길')",
    "§0 제목 괄호")

# 4. §0 맨 위 안내(옛 '상황' 문단 앞)
anchor = "> **상황**: 운영자가 이 작업을 해 온 PC 에서 **다른 PC 로 옮깁니다**"
doc.replace_once(anchor, read_block(BLK + "b04_top_note.txt") + CRLF + CRLF + anchor, "§0 맨 위 안내")

# 5. 0-1 표 뒤 덧붙임(표의 마지막 행 바로 뒤에 빈 줄과 문단)
doc.insert_after_line("| AGENT_RUNBOOK J3 |", read_block(BLK + "b05_s01_note.txt"), "0-1 덧붙임")

# 6. 0-2 15번 끝 문장 정정
doc.replace_once(
    "**11-12 19:40 에 보류**했습니다(§3 40번 — 재촉하지 않음).",
    "**11-12 19:40 에 보류**했다가(§3 40번 — 재촉하지 않음) 11-13 오후에 운영자가 스스로 Package 를 다시 만들어 시험하고 0–6단계 통과를 이슈 #190 으로 보고했습니다(§3 42번).",
    "0-2 15번 정정")

# 7. 0-2 17·18번 추가(16번 줄 바로 뒤)
doc.insert_after_line("급한 일은 운영자가 이슈로 직접 올리기로 했습니다.", read_block(BLK + "b06_s02_items.txt"), "0-2 17·18번")

# 8. 0-3 다시 쓰기 — 옛 행 일부는 그대로 재사용한다
start, end = doc.region("### 0-3. 진행 중인 일과 다음 행동", "### 0-4. 이전 PC 에만 있던 원문")
old_region = doc.text[start:end]
old_lines = old_region.split(CRLF)


def old_row(prefix):
    hits = [line for line in old_lines if line.startswith(prefix)]
    if len(hits) != 1:
        raise SystemExit("FAIL 옛 행 접두 %r 가 %d 개" % (prefix, len(hits)))
    return hits[0]


reuse = {
    "fact": old_row("| **계산 글(Fact) 경로·허용 목록·방어·관문·워치독(블로그"),
    "noaa": old_row("| **NOAA 우주날씨 제공처(확인 요청 007 조건 ②의 첫 제공처)** |"),
    "posts": old_row("| **공개 글·사이트 정비(작업 요청서 6 Phase 4 후속, 블로그"),
    "blogger": old_row("| **Blogger(영문·한글)** |"),
    "root": old_row("| **루트 저장소(사용자 사이트 루트)** |"),
    "naver": old_row("| **네이버·티스토리(중단)** |"),
    "followup": old_row("| **블로그 후속(11-07 표에서 이어받은 별건"),
    "info": old_row("| **정보 수준 후속(블로그·앱 — 묶어서 나중에)** |"),
}
root_old = "열린 PR 없음(11-13 07:13 확인)"
if reuse["root"].count(root_old) != 1:
    raise SystemExit("FAIL 루트 행의 확인 문구를 못 찾음")
reuse["root"] = reuse["root"].replace(root_old, "열린 PR 없음(11-13 07:13 확인, @@T_REF@@ 다시 확인)")

new_rows = [line for line in read_block(BLK + "b07_rows.txt").split(chr(10)) if line.strip()]
keyed = {}
for line in new_rows:
    for key, prefix in (("pause", "| **일시정지와 제한 재개 순서**"), ("shadow", "| **그림자 실행 2·3회차"), ("improve", "| **개선 자체 진행"),
                        ("s2c", "| **계산 글이 얇다는 위험"), ("flips", "| **켜는 변경 3종(T3, 블로그) — 모두 병합·확인 끝"),
                        ("app", "| **데스크톱 앱("), ("confirm", "| **확인 요청 현황(009–014)"), ("worklog", "| **문서 현행화(이 갱신 WORKLOG12"),
                        ("risk", "| **알려 둔 위험(일정은 모두 추정)")):
        if line.startswith(prefix):
            if key in keyed:
                raise SystemExit("FAIL 새 행 중복 " + key)
            keyed[key] = line
if len(keyed) != 9 or len(new_rows) != 9:
    raise SystemExit("FAIL 새 행 수가 9 가 아님: %d / %d" % (len(keyed), len(new_rows)))

order = [keyed["pause"], keyed["shadow"], keyed["improve"], keyed["s2c"], keyed["flips"], reuse["fact"], reuse["noaa"], reuse["posts"],
         reuse["blogger"], reuse["root"], reuse["naver"], keyed["app"], keyed["confirm"], keyed["worklog"], reuse["followup"], reuse["info"], keyed["risk"]]

new_region = (read_block(BLK + "b07_intro.txt") + chr(10) + chr(10)
              + "| 묶음 | 현재 | 다음 행동 |" + chr(10) + "|---|---|---|" + chr(10)
              + chr(10).join(order) + chr(10) + chr(10))
doc.replace_region("### 0-3. 진행 중인 일과 다음 행동", "### 0-4. 이전 PC 에만 있던 원문", new_region, "0-3 다시 쓰기")

doc.save()
