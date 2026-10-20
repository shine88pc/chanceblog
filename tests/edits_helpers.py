"""이슈 수정 시스템 테스트용 임시 저장소 빌더."""
import json
import shutil
from pathlib import Path

import _bootstrap
from pipeline.edits import pages, spec as spec_mod

REAL = _bootstrap.ROOT
UNSPLASH = "https://images.unsplash.com/"

ABOUT = """---
layout: info
title: 소개와 편집 원칙
description: 기존 설명입니다.
permalink: /about/
---

문의는 old@example.com 으로 보내 주세요.

[소개 링크](https://old.example.com/a) 와 [다른 링크](https://old.example.com/a) 가 있습니다.

첫 번째 문단입니다. 이 문장은 그대로 유지되어야 합니다.

## 소제목

두 번째 문단입니다.
"""

CONTACT = """---
layout: info
title: 문의와 정정 요청
description: 문의 안내.
permalink: /contact/
---

글의 사실 오류를 알려 주세요.
"""

PRIVACY = """---
layout: info
title: 개인정보처리방침
description: 방침.
permalink: /privacy/
---

방침 본문입니다.
"""

CATEGORIES = """---
layout: page
title: 카테고리
permalink: /categories/
---

<ul><li>목록</li></ul>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-1234567890123456" crossorigin="anonymous"></script>
카테고리 본문 문장입니다.
"""


def post_text(title, image, lang="ko", published=True):
    pub = "" if published else "published: false\n"
    return (f"---\nlayout: post\n{pub}title: \"{title}\"\ncategory: \"KR - 테크\"\ntags: ['a', 'b']\nlang: {lang}\n"
            f"image: \"{image}\"\n---\n\n![설명]({image})\n\n# {title}\n\n본문 문장입니다.\n")


def img(n):
    return f"{UNSPLASH}photo-{n}?auto=format&fit=crop&w=1000&q=80"


POSTS = {
    "_posts/KR - 테크/2026-10-18-KR-111111.md": post_text("첫 번째 글 제목입니다", img("111")),
    "_posts/EN - Tech/2026-10-18-EN-111111.md": post_text("First post title", img("222"), "en"),
    "_posts/2026-10-19-KR-222222.md": post_text("두 번째 글 제목입니다", img("333")),
    "_posts/A/2026-10-20-KR-333333.md": post_text("같은 제목의 글입니다", img("444")),
    "_posts/B/2026-10-20-KR-444444.md": post_text("같은 제목의 글입니다", img("555")),
    "_posts/2026-10-20-KR-555555.md": post_text("비공개 글 제목입니다", img("666"), published=False),
}


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def make_edit_root(tmp, extra_pages=None):
    root = Path(tmp)
    (root / ".github" / "editorial").mkdir(parents=True)
    shutil.copy(REAL / ".github" / "editorial" / "edit-spec.yml", root / ".github" / "editorial")
    (root / ".github" / "ISSUE_TEMPLATE").mkdir(parents=True)
    for name in ("blog_control.yml", "page-edit.yml"):
        shutil.copy(REAL / ".github" / "ISSUE_TEMPLATE" / name, root / ".github" / "ISSUE_TEMPLATE")
    (root / "pipeline").mkdir()
    shutil.copy(REAL / "pipeline" / "blogs.json", root / "pipeline")
    shutil.copy(REAL / "_config.yml", root)
    for name, text in (("about.md", ABOUT), ("contact.md", CONTACT), ("privacy.md", PRIVACY), ("categories.md", CATEGORIES)):
        write(root, name, text)
    write(root, "index.html", "<html>landing adsbygoogle ca-pub-1234567890123456</html>")
    for rel, text in (extra_pages or {}).items():
        write(root, rel, text)
    for rel, text in POSTS.items():
        write(root, rel, text)
    write(root, "history.json", json.dumps([{"kr_image": img("999")}]))
    spec = spec_mod.load_spec(root)
    pages.write_registry(root, spec)
    return root


def page_body(page="about | 소개와 편집 원칙", edit="text_change | 문구 수정", before="", after="", crlf=True):
    body = (f"### 대상 페이지\n\n{page}\n\n### 수정 항목\n\n{edit}\n\n"
            f"### 변경 전 (선택)\n\n{before or '_No response_'}\n\n### 변경 후 / 요청 내용\n\n{after}\n")
    return body.replace("\n", "\r\n") if crlf else body


def image_body(target, prompt, crlf=True):
    body = f"### 게시글 주소 또는 제목\n\n{target}\n\n### 원하는 이미지 설명\n\n{prompt}\n"
    return body.replace("\n", "\r\n") if crlf else body


def issue(body, labels=("blog-control", "edit:page"), number=12, assoc="OWNER", login="shine88pc", title="[페이지 수정] x"):
    return {"number": number, "title": title, "body": body, "author_association": assoc,
            "user": {"login": login}, "labels": [{"name": n} for n in labels]}
