"""편집 2 — §0-4 한 문장·§0-5 저녁 번호·§0-6 새 함정·새 §0-7·§1 큰 흐름·§2 표 다시 쓰기."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docedit import CRLF, Doc, read_block  # noqa: E402

WT = "C:/work/ai/improve_wt_worklog12"
BLK = "C:/work/ai/audit6/improve/worklog12/blocks/"
doc = Doc(WT + "/인수인계/작업내용.md")

# 0-4
doc.replace_once(
    "개인 PC 에 실제 데이터가 있는지는 여전히 미확인입니다. 데이터 폴더 이름은 그대로 두고",
    "개인 PC 에 실제 데이터가 있는지는 여전히 미확인입니다. 2026-11-13: 운영자가 개인 PC 에서 시험용 Package 로 시험지 0–6단계를 통과했다고 보고해(이슈 #190) 시험 블로그·시험 Seed·시험 초안·백업 같은 **시험 데이터**가 그 PC 에 생겼을 수 있고, 제한 사용 시작 보고(R-313)는 '그대로 이어 쓰기' 를 기본값으로 안내했습니다(지우려면 시험지 8단계 — 선택). 실제 운영 데이터가 있는지는 여전히 확인하지 못했습니다. 데이터 폴더 이름은 그대로 두고",
    "0-4 시험 데이터 문장")

# 0-5: 아침 값 표시 + 저녁 값 항목
doc.replace_once(
    "- 번호 현황(2026-11-13 아침 스냅샷 — 문서 작성 시점 값, 마지막으로 쓴 번호): 병합 알림은 `M062`",
    "- 번호 현황(2026-11-13 아침 스냅샷 — 문서 작성 시점 값, 마지막으로 쓴 번호 — 저녁 값은 바로 아래 항목): 병합 알림은 `M062`",
    "0-5 아침 항목 표시")
doc.insert_after_line("다음 확인 번호 `012` 는 아직 안 쓰인 번호입니다 — 총괄 판단 11-13 08:36).", read_block(BLK + "b09_s05_bullet.txt"), "0-5 저녁 번호 항목")

# 0-6 새 함정 + 0-7
tail_06 = "(`memfree.py` 로 확인 — 저장소 밖 도구로 작업 폴더 `W` 아래의 `audit6/n2/tools/memfree.py`)."
doc.insert_after_line(tail_06, read_block(BLK + "b10_s06_traps.txt"), "0-6 새 함정")
tail_trap = "열린 이슈 수로 '답 대기'를 판단하지 말고 요청 가지의 접수 알림(R-296·R-312 등)과 이 문서 §3 으로 봅니다."
doc.insert_after_line(tail_trap, read_block(BLK + "b11_s07.txt"), "0-7 새 절")

# §1: 새 첫 항목 + 옛 항목 표시
old_first = "- **(2026-11-13 아침 갱신) 큰 흐름 — 이 항목이 최신이고, 아래 항목 중 날짜가 앞선 것은 그 시점의 기록입니다**:"
doc.replace_once(old_first, read_block(BLK + "b12_s1_bullet.txt") + CRLF + "- **(2026-11-13 아침 갱신 — 이전 기록, 최신은 바로 위 항목) 큰 흐름**:", "§1 새 첫 항목")
doc.replace_once(
    "**지금 사용자가 할 일(2026-11-13 아침 갱신: 텔레그램 요청 기준 —",
    "**지금 사용자가 할 일(2026-11-13 아침 갱신 — 이전 기록, 최신은 바로 위 첫 항목 ⑦ 과 §4 18번: 텔레그램 요청 기준 —",
    "§1 사용자가 할 일 표시")

# §2: 표 다시 쓰기(옛 행 셋은 그대로 재사용)
start, end = doc.region("## 2. 지금 진행 중인 작업", "### 2-1. 이전 기록 — 2026-11-07 02시까지의 행")
old_lines = doc.text[start:end].split(CRLF)


def old_row(prefix):
    hits = [line for line in old_lines if line.startswith(prefix)]
    if len(hits) != 1:
        raise SystemExit("FAIL §2 옛 행 접두 %r 가 %d 개" % (prefix, len(hits)))
    return hits[0]


reuse_posts = old_row("| **공개 글·사이트 정비(작업 요청서 6 Phase 4 후속)** |")
reuse_blogger = old_row("| **Blogger(영문·한글, 일시정지 중)** |")
reuse_info = old_row("| **정보 수준 후속(블로그·앱, 묶어서 나중에)** |")
rows = [line for line in read_block(BLK + "b13_s2_rows.txt").split(chr(10)) if line.strip()]
if len(rows) != 7:
    raise SystemExit("FAIL §2 새 행 수 %d" % len(rows))
order = rows[:6] + [reuse_posts, reuse_blogger, reuse_info] + [rows[6]]
new_text = ("## 2. 지금 진행 중인 작업" + chr(10) + chr(10)
            + "(2026-11-13 저녁 스냅샷 — 아래 첫 표가 지금 상태입니다. 같은 내용을 '다음 행동' 중심으로 정리한 것이 §0-3 이고, 11-13 아침까지의 상세(켜는 변경 3종 승인·병합·패치 준비)는 §5 2026-11-13 에, 11-10 12시 40분 스냅샷의 행은 2-2 에, 11-07 02시까지의 옛 행은 2-1 에 이력으로 남겼습니다.)"
            + chr(10) + chr(10) + "| 작업 | 단계 | 다음 행동 |" + chr(10) + "|------|------|-----------|" + chr(10)
            + chr(10).join(order) + chr(10) + chr(10))
doc.replace_region("## 2. 지금 진행 중인 작업", "### 2-1. 이전 기록 — 2026-11-07 02시까지의 행", new_text, "§2 표 다시 쓰기")

doc.save()
