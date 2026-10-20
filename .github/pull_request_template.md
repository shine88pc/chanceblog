## 변경 요약
(무엇을, 왜)

- 대상: Chance_Blog / Blogger / 공통
- 변경 등급: T0 / T1 / T2 / T3 — T3이면 사용자 승인(날짜·요지):
- 작성 AI: / 검증 AI: (T2 이상은 서로 다른 세션)

## 완료 정의 (`docs/ENGINEERING_GUIDE.md` §7)
- [ ] 최신 main 위에서 작업했다 (`git pull --rebase`)
- [ ] 최소 diff — 관련 없는 변경·파일 통째 덮어쓰기가 없다
- [ ] 새/변경 로직에 테스트(성공+실패 경로)가 있고 네트워크 없이 통과한다
- [ ] `python scripts/validate_repo.py` 오류 0건
- [ ] `python -m unittest discover -s tests` 통과
- [ ] (워크플로) `actionlint` 0건 / (블로그 동작) `--dry-run` 통과
- [ ] diff에 비밀·내부 정보·로컬 경로가 없다
- [ ] 광고 표면 파일을 바꿨다면 `Ad-Surface-Approved:` 표시가 있다
- [ ] 문서·레지스트리와 코드가 일치한다 / `WORKLOG.md` 기록

## 검증 증거
(실행한 명령과 결과. 실행하지 못한 검증은 "실행 필요"로 적는다)
