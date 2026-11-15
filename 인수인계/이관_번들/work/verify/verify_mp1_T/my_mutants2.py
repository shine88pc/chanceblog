# Second round (verifier): doc-prose mutants that contradict the code but are not pinned phrases, plus source-edit confirmations of runtime-sweep survivors.
D = DOC

MY_MUTANTS = [
    M("P01", "문서 문장", "§5-1 끝의 마침표 허용 문장을 반대로", "끝의 마침표 하나는 허용합니다", "끝의 마침표는 허용하지 않습니다", D),
    M("P02", "문서 문장", "§5-1 소문자 m 허용 문장을 반대로", "처럼 M 이 소문자여도 `M075` 로 읽습니다", "처럼 M 이 소문자이면 거절합니다", D),
    M("P03", "문서 문장", "§6 조건 3 의 '건너뜀·중립·취소는 통과가 아님' 을 반대로", "건너뜀·중립·취소는 통과가 아님", "건너뜀·중립·취소도 통과로 봄", D),
    M("P04", "문서 문장", "§6 조건 8 의 최소 글자 수를 낮춤", "10자 이상의 구체적인 문장", "3자 이상의 구체적인 문장", D),
    M("P05", "문서 문장", "§7-3 의 미응답 규칙(참이거나 미응답)을 느슨하게", "하나라도 참이거나 미응답이면 운영자 전용", "하나라도 참이면 운영자 전용", D),
    M("P06", "문서 문장", "§10 pending 설명을 위반 허용으로", "위반은 없지만 3건 미만이거나", "위반이 있어도 3건 미만이거나", D),
    M("P07", "문서 문장", "§8 강제 push 금지를 허용으로(핀 낱말 '강제 push' 는 남음)", "- 강제 push 도 금지입니다.", "- 강제 push 는 허용합니다.", D),
    M("P08", "문서 문장", "§9 알림 항목 수 문장 7가지 → 6가지", "에 아래 7가지를 반드시 담습니다", "에 아래 6가지를 반드시 담습니다", D),
    M("P09", "문서 문장", "§4-1 답의 최소 글자·한글 수 문장을 느슨하게", "항목마다 8자 이상의 한글 문장(한글 4자 이상)이어야 하고", "항목마다 1자 이상이면 되고", D),
    M("P10", "문서 문장", "§1 '병합은 운영자만 합니다' 를 AI 병합으로 뒤집음", "지금까지처럼 병합은 운영자만 합니다.", "지금부터 병합은 AI 가 합니다.", D),
    M("P11", "문서 문장", "§9 되돌리는 PR 도 운영자가 병합 → AI 가 병합", "되돌리는 PR 도 운영자가 병합합니다", "되돌리는 PR 도 AI 가 병합합니다", D),
    M("P12", "문서 문장", "§11-2 7번 트리 해시 설계 원칙을 커밋 해시로 바꿈", "독립 검증 기록은 커밋이 아니라 트리 해시에 묶습니다", "독립 검증 기록은 트리가 아니라 커밋 해시에 묶습니다", D),
    # ---- source-edit confirmations of table entries without a dedicated test (see sweep) ----
    M("T01", "표 항목", "키 파일 확장자 .ppk 삭제", '".p12", ".pfx", ".jks", ".keystore", ".ppk", ".kdbx")', '".p12", ".pfx", ".jks", ".keystore", ".kdbx")'),
    M("T02", "표 항목", "키 파일 확장자 .kdbx 삭제", '".p12", ".pfx", ".jks", ".keystore", ".ppk", ".kdbx")', '".p12", ".pfx", ".jks", ".keystore", ".ppk")'),
    M("T03", "표 항목", "의존성 목록에서 pnpm-lock.yaml 삭제", "|pnpm-lock" + chr(92) + ".yaml|", "|"),
    M("T04", "표 항목", "공개 루트 파일에서 blogger_ko_history.json 삭제", '"history.json", "blogger_history.json", "blogger_ko_history.json", "naver_history.json"})', '"history.json", "blogger_history.json", "naver_history.json"})'),
    M("T05", "표 항목", "데스크톱 패키징 확장자 .msi 삭제", '".msix", ".msi", ".appxmanifest"', '".msix", ".appxmanifest"'),
    M("T06", "표 항목", "데스크톱 패키징 폴더 dist 삭제", '"release", "releases", "dist", "build", "pyinstaller"', '"release", "releases", "build", "pyinstaller"'),
    M("T07", "표 항목", "데스크톱 패키징 파일 manifest.in 삭제", '_PACKAGING_FILES = frozenset({"version", "version.txt", "manifest.in"})', '_PACKAGING_FILES = frozenset({"version", "version.txt"})'),
]
