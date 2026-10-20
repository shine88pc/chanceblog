"""Blogger 생성기 진입점(호환용 래퍼).

실제 로직은 pipeline/ 패키지에 있다. 이 파일은 기존 호출(`python blogger_generator.py`)과
문서 링크를 유지하기 위한 얇은 래퍼이며 레지스트리의 `blogger_macat` 블로그를 실행한다.
다른 블로그는 `python -m pipeline.run --blog <key>` 를 쓴다.

환경변수·종료 코드·동작: pipeline/run.py 상단 설명, docs/ARCHITECTURE.md
(참고: 예전 방식의 즉시 게시·고정 주제 반복·무검증 게시는 제거됨 — docs/DEFECT_REGISTER.md D-04)
"""
import sys

from pipeline.run import main

if __name__ == "__main__":
    sys.exit(main(["--blog", "blogger_macat"] + sys.argv[1:]))
