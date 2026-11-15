# Third round (verifier): hygiene guards (tilde, web address, Liquid, local path, invisible char, secret shape) and register row — do the guards bite?
URLTEXT = "https" + ":" + "//example.org/x"
FAKE = "AI" + "za" + "A" * 35

MY_MUTANTS = [
    A("H01", "위생", "문서 끝에 ASCII 물결표 추가", DOC, "\n물결 ~ 표시\n"),
    A("H02", "위생", "문서 끝에 웹 주소 추가", DOC, "\n" + URLTEXT + "\n"),
    A("H03", "위생", "문서 끝에 Liquid 이중 중괄호 추가", DOC, "\n{{ site.title }}\n"),
    A("H04", "위생", "문서 끝에 이 PC 경로 모양 추가", DOC, "\nC:/work/x\n"),
    A("H05", "위생", "문서 끝에 너비 없는 글자 추가", DOC, "\n" + chr(0x200B) + "\n"),
    A("H06", "위생", "모듈 끝에 ASCII 물결표 주석 추가", MOD, "\n# ~\n"),
    A("H07", "위생", "모듈 끝에 비밀 모양 주석 추가", MOD, "\n# " + FAKE + "\n"),
    A("H08", "위생", "모듈 끝에 웹 주소 주석 추가", MOD, "\n# " + URLTEXT + "\n"),
    M("H09", "대장", "결함 대장 D-346 행 번호를 D-348 로", "| **D-346** | 정보 |", "| **D-348** | 정보 |", "docs/DEFECT_REGISTER.md"),
    A("H10", "위생", "문서 끝에 마크다운 링크 모양 추가", DOC, "\n[x](y)\n"),
]
