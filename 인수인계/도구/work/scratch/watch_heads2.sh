#!/bin/bash
# 두 저장소(블로그·데스크톱)의 main 머리가 바뀌면 한 줄씩 알린다 — git ls-remote 만 쓰는 가벼운 감시.
# watch_heads.sh 와 같되 스스로 끝난다: 30분 감시기가 만료돼도 이 스크립트가 고아로 남아 1분마다 GitHub 를 부르지 않도록
# 1750초(약 29분) 뒤 스스로 종료한다(2026-11-11 17:08, 고아 19개를 PID 로 정리한 뒤 추가).
BLOG=https://github.com/shine88pc/chanceblog.git
DESK=https://github.com/shine88pc/chanceblog-desktop.git
head_of() { git ls-remote "$1" refs/heads/main 2>/dev/null | cut -c1-7; }
pb=$(head_of $BLOG); pd=$(head_of $DESK)
echo "가벼운 감시 시작: 블로그 main ${pb:-?} · 데스크톱 main ${pd:-?}"
END=$((SECONDS+1750))
while [ "$SECONDS" -lt "$END" ]; do
  sleep 60
  cb=$(head_of $BLOG); cd_=$(head_of $DESK)
  if [ -n "$cb" ] && [ "$cb" != "$pb" ]; then
    echo "[블로그] main 이 움직임: ${pb:-?} -> $cb ($(date '+%H:%M'))"
    pb=$cb
  fi
  if [ -n "$cd_" ] && [ "$cd_" != "$pd" ]; then
    echo "[데스크톱] main 이 움직임: ${pd:-?} -> $cd_ ($(date '+%H:%M'))"
    pd=$cd_
  fi
done
echo "가벼운 감시 종료(수명 만료) — 다시 무장하세요"
