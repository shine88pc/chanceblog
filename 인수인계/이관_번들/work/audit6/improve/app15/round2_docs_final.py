"""2차 지시 문서 고치기(결정 기록·변경 이력·설계 명세) — 옛 글이 정확히 한 번 나올 때만 바꾼다. 사용: python -X utf8 round2_docs_final.py <작업 폴더> [ap15|ap14|all]
숫자 자리 표시(`[[…]]`)는 마지막 점검 뒤 `round2_numbers.py` 가 실제 값으로 바꾼다 — 남아 있으면 안 된다(마지막에 `grep -rn '\\[\\[' docs CHANGELOG.md` 로 확인)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pairs import append_text, replace_once  # noqa: E402

ROOT = sys.argv[1]
WHICH = sys.argv[2] if len(sys.argv) > 2 else "all"
DEC, LOG, SPEC = "docs/DECISIONS.md", "CHANGELOG.md", "docs/UI_DESIGN_SPEC.md"


def ap15():
    # D-487 — 대비 설명 한 줄 + 남은 다섯 중 문장에 가까운 둘
    replace_once(ROOT, DEC,
                 "이 다섯의 대비(3.20)는 작은 글 기준 4.5 에 못 미치므로 이것까지 바꿀지는 운영자가 정할 일이다(남은 일).",
                 "이 다섯의 대비(3.20)는 작은 글 기준 4.5 에 못 미친다(대비는 글자와 바탕의 밝기 차이를 나타낸 수라서 클수록 잘 보이고, 4.5 이상이면 작은 글자도 편하게 읽힌다). 이것까지 바꿀지는 운영자가 정할 일이다(남은 일) — "
                 "다섯 가운데 **후보 상세의 값 칸**(`조회하지 못했어요`(`cand_trend_unavailable`)·`데이터 부족`(`cand_trend_missing`))은 값이 없을 때 나오는 말이라 점선·`평가 전` 보다 문장에 더 가까우니, 운영자가 정할 때 이 둘을 먼저 본다.")
    # D-487 — 시험 설명(역할 식 못박기·CI 에서 도는 것·실제 색) 과 변이 수
    replace_once(ROOT, DEC,
                 "새 시험 `tests/test_ui_sentence_color.py` 17개(PySide6 없이 도는 9개와 PySide6 가 있을 때 8개): 승인 때 숫자(3.20·5.43·1.72)를 실제 계산값과 견주고, 화면 소스에서 `muted` 역할이 빈 값 다섯 곳뿐이고 문장 일곱 곳이 `sub` 임을 AST 로 못박고(어느 쪽으로든 한 곳이 바뀌면 빨강), "
                 "실제 위젯의 역할과 스타일시트 색(흰 바탕 대비 4.5 이상)·입력 칸 테두리 색과 스타일시트 줄이 그대로임을 확인한다. 고치기 전 코드에서 17개 중 8개(PySide6 없을 때 2개)가 빨강이었다. "
                 "**변이 10개**가 모두 빨강(문장 한 곳을 다시 muted 로 세 곳·`sub` 역할 색을 흐린 글로·입력 칸 테두리에 새 진한 색·스타일시트 입력 칸 테두리를 보조 글 색으로·보조 글 토큰을 옅게·`sub` 의 글자 모양을 바꿔 배치가 달라짐·빈 값까지 문장 색으로 넘침 등)이고 원복 뒤 sha256 이 원본과 같다.",
                 "새 시험 `tests/test_ui_sentence_color.py` [[A15_TESTS]]개(PySide6 없이 도는 [[A15_FREE]]개 — PySide6 가 없는 CI 는 이것만 돈다 — 와 PySide6 가 있을 때 [[A15_QT]]개): 승인 때 숫자(3.20·5.43·1.72)를 실제 계산값과 견주고, "
                 "화면 소스의 라벨 호출 열두 곳(문장 일곱·빈 값 다섯)의 글자 역할 **식**(`ast.unparse` 글)을 표로 못박아 낱말이 바뀌거나 조건이 뒤집히면(`'sub' if missing else 'body'` ↔ 반대) 빨갛고, "
                 "`muted` 글자가 빈 값 다섯 밖에서 변수·`role=` 키워드·함수 기본값·튜플 속으로 새로 나오는 길과 역할을 변수로 넘기는 새 라벨 호출(역할을 받아 라벨을 만드는 부품 넷의 허용 목록 밖)을 막는다. "
                 "스타일시트 소스는 입력 칸 선택자 목록(덧붙은 규칙이 뒤에서 테두리를 덮지 못하게)·손으로 덧붙인 `sub`/`muted` 역할 규칙 없음·`setStyleSheet(` 호출이 `theme.py` 한 곳뿐임을 못박는다. "
                 "PySide6 가 있을 때는 만든 스타일시트에 역할 규칙이 하나이고(마지막 규칙이 이긴다) **위젯이 실제로 쓰는 글자 색**(팔레트)이 보조 글 색이며 빈 값은 흐린 글 색 그대로이고, 입력 칸을 실제로 그려 테두리 픽셀이 `#B8C7DA` 임을 확인한다. "
                 "고치기 전 코드(시작점 41ce292)에서 새 시험 [[A15_TESTS]]개 중 [[A15_PRE]]개(PySide6 없을 때 [[A15_PRE_FREE]]개)가 빨강이었다. "
                 "**변이 [[A15_MUT]]개**가 모두 빨강이다 — 1차의 10개(문장 한 곳을 다시 muted 로 세 곳·`sub` 역할 색을 흐린 글로·입력 칸 테두리에 새 진한 색·스타일시트 입력 칸 테두리를 보조 글 색으로·보조 글 토큰을 옅게·`sub` 의 글자 모양을 바꿔 배치가 달라짐·빈 값까지 문장 색으로 넘침 등)에 "
                 "2차 지시로 독립 검증 2 가 찾은 생존 변이(분기 뒤집기 NM1·요약이 늘 `sub` NM2·변수 역할 NM4·뒤에 덧붙은 `sub` 규칙 NM5·위젯별 스타일시트 NM10·뒤에 덧붙은 입력 칸 규칙 NM13 — 앞 다섯은 **PySide6 없이도** 빨강)와 새 규칙마다 둘 이상(R01–R10)을 더했다. 원복 뒤 sha256 이 원본과 같다.")
    # CHANGELOG — AP15 줄(대비 설명·시험 수)
    replace_once(ROOT, LOG,
                 "후보 상세·후보 카드·초안 작성의 안내·결과 문장 일곱 곳이 쓰던 흐린 글(흰 바탕 대비 3.2)을 이미 있던 보조 글 색(5.4)으로 읽히게 했다.",
                 "후보 상세·후보 카드·초안 작성의 안내·결과 문장 일곱 곳이 쓰던 흐린 글(흰 바탕 대비 3.2)을 이미 있던 보조 글 색(5.4)으로 읽히게 했다(대비는 글자와 바탕의 밝기 차이를 나타낸 수로, 클수록 잘 보이고 4.5 이상이면 작은 글자도 편하게 읽힌다).")
    replace_once(ROOT, LOG, "새 시험 `tests/test_ui_sentence_color.py` 17개. 사진은 다시 찍지 않았다(UI_VISUAL_QA 14절).",
                 "새 시험 `tests/test_ui_sentence_color.py` [[A15_TESTS]]개(PySide6 가 없는 CI 에서 도는 것 [[A15_FREE]]개 — 문장 일곱·빈 값 다섯의 글자 역할 식과 스타일시트 소스 규칙을 못박는다). 사진은 다시 찍지 않았다(UI_VISUAL_QA 14절).")
    # 설계 명세 12절 — 한 곳이 바뀌면 빨강 주장을 사실대로
    replace_once(ROOT, SPEC,
                 "빈 값 다섯의 대비(3.20)는 작은 글 기준(4.5)에 못 미친다. 승인 범위가 '문장'이라 그대로 두었고, 이것까지 바꿀지는 운영자가 정한다(남은 일).",
                 "빈 값 다섯의 대비(3.20)는 작은 글 기준(4.5)에 못 미친다(대비는 글자와 바탕의 밝기 차이를 나타낸 수로, 클수록 잘 보이고 4.5 이상이면 작은 글자도 편하게 읽힌다). 승인 범위가 '문장'이라 그대로 두었고, 이것까지 바꿀지는 운영자가 정한다(남은 일) — "
                 "다섯 가운데 후보 상세의 값 칸(`조회하지 못했어요`·`데이터 부족`)은 값이 없을 때 나오는 말이라 문장에 더 가깝다.")
    replace_once(ROOT, SPEC,
                 "- 시험: `tests/test_ui_sentence_color.py` — 값·화면 소스의 `muted`/`sub` 자리·실제 위젯·입력 칸 테두리(어느 쪽으로든 한 곳이 바뀌면 빨강).",
                 "- 시험: `tests/test_ui_sentence_color.py` — 값, 화면 소스의 라벨 호출 열두 곳의 글자 역할 식(낱말이 더해지거나 빠지거나 조건이 뒤집히면 빨강)과 `muted` 글자가 새로 나오는 길(변수·키워드·기본값), 스타일시트 소스의 입력 칸 선택자 목록, "
                 "실제 위젯이 쓰는 글자 색(팔레트)과 입력 칸 테두리 픽셀. PySide6 가 없는 CI 에서는 앞의 값·소스 시험만 돌고 실제 위젯·픽셀 시험은 PySide6 가 있는 PC 에서 돈다.")


def ap14():
    # D-488 — 속도 제한은 정해진 구간
    replace_once(ROOT, DEC,
                 "·1분에 30줄까지·쓰기·폴더 만들기·이름 바꾸기·폴더 해석이 실패해도 예외를 삼키고 그 줄만 버린다",
                 "·정해진 1분 구간마다 30줄까지(구간은 첫 줄이 쓰일 때 시작하고 경계에서는 짧은 시간에 더 나올 수 있다)·쓰기·폴더 만들기·이름 바꾸기·폴더 해석이 실패해도 예외를 삼키고 그 줄만 버린다")
    # D-488 — 돌려쓰기는 이름 바꾸기뿐
    replace_once(ROOT, DEC,
                 "(`errors.log`·`.1`·`.2`, 쓰면 한도를 넘을 때 먼저 돌린다 — 돌리기가 막히면 그 줄을 버려 한도를 넘기지 않는다)",
                 "(`errors.log`·`.1`·`.2`, 쓰면 한도를 넘을 때 먼저 돌린다 — 이름 바꾸기뿐이라 가장 오래된 `.2` 를 먼저 지우지 않고 덮어쓰며, 돌리기가 막히면 그 줄을 버려 한도를 넘기지 않고 옛 파일 셋도 그대로 둔다)")
    # D-488 — 시험은 켜지 않는다는 말이 사실이 아니었다
    replace_once(ROOT, DEC,
                 "— 예시 화면(`--sample`)·명령줄·시험은 켜지 않고 경계를 되돌리면(`uninstall`) 함께 꺼진다.",
                 "— 예시 화면(`--sample`)과 명령줄은 켜지 않고 경계를 되돌리면(`uninstall`) 함께 꺼진다(`--sample` 없이 `launcher.main` 을 끝까지 부르는 기존 시험 — `test_ui_launcher`·`test_single_instance`·`test_ui_backup_core` — 은 켜지지만 켜기만으로는 폴더 해석도 파일 만들기도 하지 않고 시험의 뒷정리가 끈다. "
                 "2차 확인 때 임시 기본 폴더에 `logs` 는 생기지 않았다).")
    # D-488 — ⑥ 한계와 후속 항목, D-32 는 원문 그대로
    replace_once(ROOT, DEC,
                 "코드 주석 셋(`boundary.py`·`app_state.py`·`launcher.py`). 위임 규칙 근거:",
                 "코드 주석 셋(`boundary.py`·`app_state.py`·`launcher.py`). ⑥ **기록이 닿지 않는 길(한계)과 후속 항목**(2차 지시로 문서에 못박음): 묶음 실행 파일의 시작 실패(`packaging/gui_entry.py` 의 `start_gui` 가 예외를 잡아 메시지 상자로 오류 종류 이름만 알리고 끝내 처리하지 못한 예외 훅까지 오지 않는다)·"
                 "작업 스레드가 삼키는 오류(`ui/core/jobs.py` 의 `Job._run` 이 `BaseException` 을 잡아 '작업 실패' 안내와 이름으로 바꾸고, 콜백 오류는 `Job._emit` 이 이름만 기억한다)·네이티브 충돌(충돌 덤프를 만들지 않는다)·데이터 폴더를 풀지 못하는 경우는 기록되지 않는다. "
                 "이 길들에 기록을 잇는 일(`start_gui` 와 `Job._run` 에서 `errorlog.record_exception` 한 줄씩)은 AP14 가 바꾸는 파일 목록 밖의 코드 변경이라 하지 않았고 **후속 항목**으로 남긴다 — 시험 `test_the_stated_limits_are_still_true_in_the_code` 가 그 길이 이어지면 빨개져 문서의 한계를 함께 고치게 한다. "
                 "D-32 의 옛 문장('파일을 쓰지 않는다')은 결정 기록이라 원문 그대로 두고 이 결정이 덮는다. 위임 규칙 근거:")
    # D-488 — 시험·변이·바뀐 기존 시험의 숫자와 내용
    replace_once(ROOT, DEC,
                 "새 시험 `tests/test_security_errorlog.py` 65개(모두 PySide6 없이 돈다):",
                 "새 시험 `tests/test_security_errorlog.py` [[A14_TESTS]]개(모두 PySide6 없이 돈다 — 2차 지시로 글자표 전수·가장 안쪽 여섯 위치·돌려쓰기에서 지우지 않음·한계 문서를 더했다):")
    replace_once(ROOT, DEC,
                 "백업과 복원·소스가 표준 라이브러리 몇 개와 `mask` 만 가져옴·네트워크 0·충돌 덤프 없음·문서. 고치기 전 코드에서는 새 모듈이 없어 시험 모듈 자체를 불러오지 못하고(ImportError), 사실을 읽는 시험 여섯(문서 넷·백업 목록 하나·launcher 소스 하나)은 그대로 빨강이다.",
                 "백업과 복원·소스가 표준 라이브러리 몇 개와 `mask` 만 가져옴·네트워크 0·충돌 덤프 없음·문서·**이름 글자표 전수**(클래스·파일·Qt 분류 이름에 U+0001 에서 U+024F 까지 전부와 방향 바꿈·줄 나눔·한글 등을 앞·가운데·끝에 끼워 시험이 따로 적은 정답과 견줌 — 소스의 글자표가 한 글자라도 넓어지면 빨강)·"
                 "**가장 안쪽 여섯 위치**(함수 열두 개가 부르는 사슬로 안쪽이 먼저이고 바깥이 잘림을 못박고 `MAX_FRAMES == 6` 을 고정)·**돌려쓰기는 이름 바꾸기뿐**(막혀도 옛 파일 셋이 그대로이고 한 단계만 막혀도 이어서 끝냄)·시각은 시계의 시간대와 상관없이 UTC·처리 중 오류의 추적은 같은 종류일 때만 빌림. "
                 "고치기 전 코드에서는 새 모듈이 없어 시험 모듈 자체를 불러오지 못한다(ImportError) — 새 모듈의 빈 껍데기만 두고 돌리면 [[A14_PRE]]개가 빨강이다(문서·백업 목록·launcher 소스를 읽는 시험과 기록기를 부르는 시험).")
    replace_once(ROOT, DEC,
                 "**변이 24개**(메시지를 그대로 기록",
                 "**변이 [[A14_MUT]]개**(1차 24개 — 메시지를 그대로 기록")
    replace_once(ROOT, DEC,
                 "처음 돌렸을 때 쓰기 실패 삼키기 한 곳을 놓쳐 `write` 단계를 직접 보는 시험을 더했다)가 모두 빨강이고 원복 뒤 sha256 이 원본과 같다.",
                 "처음 돌렸을 때 쓰기 실패 삼키기 한 곳을 놓쳐 `write` 단계를 직접 보는 시험을 더했다. 2차 지시: 독립 검증 1 이 찾은 생존 변이 V01(파일 글자표에 `@`)·V02(클래스 글자표에 공백)·V03(`fullmatch` → `match`)·V11(가장 바깥 여섯)·V12(`MAX_FRAMES` 10)·V13(잠금 기다림 1000초)·V14(시간대 변환 빠짐)·V18(추적을 종류 확인 없이 빌림)·V22(Qt 분류 이름 글자표 없음)·V23(Qt 줄 번호 범위 없음)을 모두 빨갛게 했고 나머지 V 원문과 새 규칙마다 둘 이상(N01–N24)을 더했다)가 모두 빨강이고 원복 뒤 sha256 이 원본과 같다.")
    replace_once(ROOT, DEC,
                 "**바뀐 기존 시험**(강화만): `tests/test_ui_core.py` 의 `test_the_docs_say_the_one_line_record_needs_a_console` — 문서가 더는 '로그 파일은 설치 파일 묶음에서 정한다' 고 말하지 않으므로 그 문장을 지키던 한 줄을 새 사실(작은 오류 기록 파일 `errors.log` 가 있다)을 지키는 한 줄로 바꿨고 '콘솔 실행 기준'·'표준 오류가 없는' 단언은 그대로다.",
                 "**바뀐 기존 시험**(강화만, 한 곳): `tests/test_ui_core.py` 의 `test_the_docs_say_the_one_line_record_needs_a_console` — 문서가 더는 '로그 파일은 설치 파일 묶음에서 정한다' 고 말하지 않으므로 그 문장을 지키던 단언 한 줄(1줄)을 새 사실(작은 오류 기록 파일 `errors.log` 가 있다)을 지키는 단언 두 줄(2줄)로 바꿨고 '콘솔 실행 기준'·'표준 오류가 없는' 단언은 그대로다.")
    # CHANGELOG — AP14 줄
    replace_once(ROOT, LOG, "새 시험 `tests/test_security_errorlog.py` 65개.",
                 "돌려쓰기는 이름 바꾸기뿐이라 막혀도 옛 파일을 잃지 않는다. 기록되지 않는 길(묶음 실행 파일의 시작 실패·작업 스레드가 삼키는 오류·네이티브 충돌·데이터 폴더를 풀지 못함)은 문서에 한계로 적었다(D-488 후속 항목). 새 시험 `tests/test_security_errorlog.py` [[A14_TESTS]]개.")


def reorder_changelog():
    """AP15 줄이 AP14 줄보다 먼저 오게(AP15 가 먼저 병합된다) — 두 줄의 자리만 바꾼다."""
    path = Path(ROOT) / LOG
    data = path.read_bytes()
    eol = b"\r\n" if data.count(b"\r\n") * 2 >= data.count(b"\n") else b"\n"
    lines = data.split(eol)
    first = [i for i, line in enumerate(lines) if line.startswith("- 앱이 처리하지 못한 오류의 이름과 코드 위치만".encode("utf-8"))]
    second = [i for i, line in enumerate(lines) if line.startswith("- 안내·결과 문장의 글 색을 흐린 글에서 보조 글로".encode("utf-8"))]
    if len(first) != 1 or len(second) != 1:
        raise SystemExit(f"변경 이력의 두 줄을 찾지 못했다: {first} {second}")
    a, b = first[0], second[0]
    if b == a + 1:
        lines[a], lines[b] = lines[b], lines[a]
        path.write_bytes(eol.join(lines))
        print("changelog 순서 바꿈: AP15 줄이 AP14 줄 앞으로")
    elif a == b + 1:
        print("changelog 순서는 이미 AP15 → AP14")
    else:
        raise SystemExit(f"두 줄이 붙어 있지 않다: {a} {b}")


if WHICH in ("ap15", "all"):
    ap15()
if WHICH in ("ap14", "all"):
    ap14()
if WHICH in ("order", "all"):
    reorder_changelog()
