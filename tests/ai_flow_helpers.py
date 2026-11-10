"""AI 흐름 방어 시험 도우미: 합성 표식 글(실제 지역·수치가 아니다)과 임시 저장소 폴더.

표식 글의 모양은 구조화 Fact 조립기가 만든 글과 같게 짠다 — 제목에 값이 들어 있고(예: 실업률 3.5%), 태그·분류·설명이 있고, 공용 자체 이미지 한 장을 두 글이 같이 쓴다(감사 5-3).
머리말 맨 끝의 `provenance: "facts"` 한 줄이 표식이다. 대조군(표식 없는 글)은 같은 모양에 표식 줄만 없다.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import ai_guard

OWN_IMAGE = "https://example.invalid/assets/own-card.png"        # 모든 Fact 글이 같이 쓰는 자체 이미지(사진이 아니다 — FACT_PATH 후보 2-(b))

FACT_POSTS = (
    {"rel": "_posts/경제·일/2026-11-20-KR-100000.md", "title": "가상 지역 가 실업률 3.5%(2026년 3월 기준), 앞 기간보다 0.3%p 높아", "category": "경제·일",
     "tags": ["실업률", "가상 지역 가", "공개 통계", "숫자로 읽기"],
     "description": "가상 지역 가의 2026년 3월 실업률은 3.5%로 앞 기간보다 0.3%p 높았다. 이 글은 공개 자료의 값과 계산 결과만 옮겼다."},
    {"rel": "_posts/경제·일/2026-11-21-KR-100000.md", "title": "가상 지역 나 소비자물가 지수 103.4(2026년 3월 기준), 한 해 전보다 2.1% 높아", "category": "경제·일",
     "tags": ["소비자물가", "가상 지역 나", "공개 통계", "숫자로 읽기"],
     "description": "가상 지역 나의 2026년 3월 소비자물가 지수는 103.4로 한 해 전보다 2.1% 높았다. 이 글은 공개 자료의 값과 계산 결과만 옮겼다."},
)
# 대조군: 표식이 없는 보통 글(제목이 서로 많이 다르고 사진도 서로 다르다)
NORMAL_POSTS = (
    {"rel": "_posts/사회·정책/2026-11-01-KR-090000.md", "title": "도서관 이용 시간을 늘린 지역의 이용자 변화를 살펴본다", "category": "사회·정책", "tags": ["도서관", "지역"],
     "description": "도서관 개방 시간을 늘린 뒤 이용자가 어떻게 달라졌는지 자료를 읽어 보는 글이다.", "image": "https://images.unsplash.com/photo-1000000000001?auto=format&fit=crop&w=1000&q=80"},
    {"rel": "_posts/기술·미래/2026-11-02-KR-090000.md", "title": "반도체 장비 투자가 지역 일자리에 미치는 영향을 정리한다", "category": "기술·미래", "tags": ["반도체", "일자리"],
     "description": "반도체 장비 투자가 지역 일자리에 어떤 흐름으로 이어지는지 정리한 글이다.", "image": "https://images.unsplash.com/photo-1000000000002?auto=format&fit=crop&w=1000&q=80"},
)


def post_text(title, category, tags, description, image, marker=False, lang="ko", body="본문 문장입니다. 이 글은 시험용 가짜 글이며 실제 자료가 아닙니다.", newline="\n"):
    """머리말(+표식 줄) + 본문. 줄 끝을 newline 으로 쓴다(LF·CRLF 모두 시험한다)."""
    lines = ["---", "layout: post", "title: " + json.dumps(title, ensure_ascii=False), "category: " + json.dumps(category, ensure_ascii=False),
             "tags: " + json.dumps(tags, ensure_ascii=False), f"lang: {lang}", "image: " + json.dumps(image), "description: " + json.dumps(description, ensure_ascii=False)]
    if marker:
        lines.append('provenance: "facts"')
    lines += ["---", "", body, ""]
    return newline.join(lines)


def fact_text(index=0, marker=True, newline="\n"):
    post = FACT_POSTS[index]
    return post_text(post["title"], post["category"], post["tags"], post["description"], OWN_IMAGE, marker=marker, newline=newline)


def normal_text(index=0, newline="\n"):
    post = NORMAL_POSTS[index]
    return post_text(post["title"], post["category"], post["tags"], post["description"], post["image"], newline=newline)


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def history_entry(title, marker=False, date="2026-11-20", **extra):
    entry = {"date": date, "topic": title, "kr_title": title, "en_title": None, "kr_image": OWN_IMAGE, "en_image": None, "slot": 9, "lane": "economy", "source": "", "source_url": ""}
    entry.update(extra)
    if marker:
        entry["provenance"] = "facts"
    return entry


class RepoCase(unittest.TestCase):
    """임시 저장소 폴더 안으로 들어가(chdir) 도는 시험의 바탕: 방벽 캐시를 비우고, 끝나면 원래 폴더로 돌아온다. 운영 코드가 쓰는 상대 경로(_posts·history.json)가 이 폴더를 가리킨다.
    방벽은 '작업 폴더'와 '이 코드가 든 저장소'(ai_guard.CODE_ROOT)를 둘 다 훑는다 — 진짜 저장소에 표식 글이 한 편이라도 올라오면 그 글의 조각이 시험에 섞여 들어와 검사가 빨개진다(D-194).
    그래서 시험 동안에는 CODE_ROOT 도 같은 임시 폴더로 고정한다(끝나면 돌려놓는다). 이 성질은 tests/test_ai_guard.py 의 RepoStateIndependenceTest 가 못박는다."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.addCleanup(ai_guard.reset_cache)
        code_root = mock.patch.object(ai_guard, "CODE_ROOT", self.root)
        code_root.start()
        self.addCleanup(code_root.stop)
        ai_guard.reset_cache()

    def add_fact_posts(self, newline="\n"):
        for index, post in enumerate(FACT_POSTS):
            write(self.root, post["rel"], fact_text(index, newline=newline))

    def add_normal_posts(self):
        for index, post in enumerate(NORMAL_POSTS):
            write(self.root, post["rel"], normal_text(index))

    def set_history(self, entries):
        write(self.root, "history.json", json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
