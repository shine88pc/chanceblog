"""편집 10(사슬이 끝난 뒤에만 실행) — 마감 뒤 사건 R-321(M067 병합완료 확인 '정상', 20:24)을 '마지막 갱신 이후 추가' 줄에 더하고 '이후' 기준 번호를 R-322 로 올린다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docedit import Doc  # noqa: E402

doc = Doc("C:/work/ai/improve_wt_worklog12/인수인계/작업내용.md")
wl = Doc("C:/work/ai/improve_wt_worklog12/WORKLOG.md")
doc.replace_once("병합완료 확인과 앱 main 검사 결과는 이 문서를 고친 시점에 아직 없습니다.", "병합완료 확인 '정상' **R-321**(20:24)이 갔습니다(앱 main 검사가 끝난 뒤).", "M067 확인 R-321")
doc.replace_once("이후의 일은 요청 가지의 R-321 이후 파일과 세 저장소의 git 기록으로 확인합니다.", "이후의 일은 요청 가지의 R-322 이후 파일과 세 저장소의 git 기록으로 확인합니다.", "마지막 갱신 이후 추가 R-322")
doc.replace_once("실제로 보냈는지는 요청 가지의 마지막 요청 파일(R-321 이후)로 확인합니다.", "실제로 보냈는지는 요청 가지의 마지막 요청 파일(R-322 이후)로 확인합니다.", "0-7 R-322")
doc.replace_once("보내면 요청 가지의 R-321 이후 파일로 확인합니다 | 아직 안 물음 | T3 |", "보내면 요청 가지의 R-322 이후 파일로 확인합니다 | 아직 안 물음 | T3 |", "§3 45번 R-322")
doc.replace_once("이 선택을 따로 묻는 확인 요청은 R-320 까지 보낸 적이 없습니다.", "이 선택을 따로 묻는 확인 요청은 R-321 까지 보낸 적이 없습니다.", "0-7 R-321")
wl.replace_once("(요청 가지 R-321 이후 파일로 확인)", "(요청 가지 R-322 이후 파일로 확인)", "WORKLOG R-322")
wl.replace_once("(R-320 까지 없음 — 기억 기록은", "(R-321 까지 없음 — 기억 기록은", "WORKLOG R-321")
wl.replace_once("마감 뒤 사건(R-320 병합 부탁과 M067 병합)을 그 줄에 적음)", "마감 뒤 사건(R-320 병합 부탁·M067 병합·병합완료 확인 R-321)을 그 줄에 적음)", "WORKLOG 변경 사항 표 줄")
doc.save()
wl.save()
