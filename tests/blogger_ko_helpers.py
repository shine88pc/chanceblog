"""한글 Blogger(kcyoon, 레지스트리 키 blogger_kcyoon) 러너 시험 공용 도구(작업 D).

임시 저장소는 실제 레지스트리의 사본이다(test_run.make_root): 영문 Blogger 는 실제 영문 프로필 그대로이고, 한글 Blogger 의 mode 만 시험이 정한다(실제 레지스트리에서는 off).
시크릿 값은 가짜다. 실제 Blogger·Gemini 호출은 없다(가짜 게시자·스텁 LLM).
"""
import json
import random
import tempfile
import unittest
from pathlib import Path

import _bootstrap
from pipeline import registry
from pipeline import run as run_mod
from pipeline.publishers.base import PublishResult
from pipeline.stubs import stub_llm
from test_run import NOW, FakePublisher, make_root

REAL = _bootstrap.ROOT
KO = "blogger_kcyoon"
EN = "blogger_macat"
KO_URL = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), KO)["url"]
EN_URL = registry.get_blog(registry.load_registry(REAL / "pipeline" / "blogs.json"), EN)["url"]
# 한글 Blogger 가 읽는 이름(영문의 BLOGGER_* 와 겹치지 않는다) — 값은 가짜
KO_NAMES = ("BLOGGER_KO_BLOG_ID", "BLOGGER_KO_CLIENT_ID", "BLOGGER_KO_CLIENT_SECRET", "BLOGGER_KO_REFRESH_TOKEN")
EN_NAMES = ("BLOGGER_BLOG_ID", "BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")
KO_VALUES = {"BLOGGER_KO_BLOG_ID": "5550001110" + "00000001", "BLOGGER_KO_CLIENT_ID": "555000111000-" + "kofakeclientid",
             "BLOGGER_KO_CLIENT_SECRET": "ko-fake-client-" + "secret-value-0101", "BLOGGER_KO_REFRESH_TOKEN": "ko-fake-refresh-" + "token-value-0102"}
EN_VALUES = {"BLOGGER_BLOG_ID": "7654321098" + "765432101", "BLOGGER_CLIENT_ID": "123456789012-" + "fakeclientid",
             "BLOGGER_CLIENT_SECRET": "fake-client-" + "secret-value-0001", "BLOGGER_REFRESH_TOKEN": "fake-refresh-" + "token-value-0002"}
GEMINI = "fake-gemini-" + "key-value-0003"
KO_ENV = {"GEMINI_API_KEY": GEMINI, **KO_VALUES}
EN_ENV = {"GEMINI_API_KEY": GEMINI, **EN_VALUES}
# 공용 워크플로가 러너에 넘기는 모양(역할 이름): 래퍼가 한글 시크릿 이름을 역할로 바꿔 넘긴 결과
KO_WORKFLOW_ENV = {"PIPELINE_SECRET_LLM_API_KEY": GEMINI, "PIPELINE_SECRET_BLOG_ID": KO_VALUES["BLOGGER_KO_BLOG_ID"],
                   "PIPELINE_SECRET_CLIENT_ID": KO_VALUES["BLOGGER_KO_CLIENT_ID"], "PIPELINE_SECRET_CLIENT_SECRET": KO_VALUES["BLOGGER_KO_CLIENT_SECRET"],
                   "PIPELINE_SECRET_REFRESH_TOKEN": KO_VALUES["BLOGGER_KO_REFRESH_TOKEN"]}


def make_pair_root(tmp, ko_mode="draft", en_mode="off", en_lang="en"):
    """영문(실제 영문 프로필)·한글(실제 한글 AI·도구 프로필)이 함께 있는 임시 저장소. ko_mode·en_mode 만 시험이 정한다."""
    root = make_root(tmp, mode=en_mode, lang=en_lang)
    path = root / "pipeline" / "blogs.json"
    reg = json.loads(path.read_text(encoding="utf-8"))
    for blog in reg["blogs"]:
        if blog["key"] == KO:
            blog["mode"] = ko_mode
    path.write_text(json.dumps(reg, ensure_ascii=False), encoding="utf-8")
    return root


def ko_publisher(**kwargs):
    kwargs.setdefault("blog_url", KO_URL)
    kwargs.setdefault("result", PublishResult(post_id="ko1", url=KO_URL + "2026/10/x.html"))
    return FakePublisher(**kwargs)


class KoreanRunBase(unittest.TestCase):
    MODE = "draft"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_pair_root(self._tmp.name, ko_mode=self.MODE)

    def go(self, env=None, llm=stub_llm, publisher=None, extra=(), now=NOW, seed=1, root=None, blog=KO):
        out = []
        publisher = publisher if publisher is not None else ko_publisher()
        code = run_mod.run(["--blog", blog, "--root", str(root or self.root), *extra], environ={} if env is None else env, now=now, llm=llm,
                           publisher_factory=lambda b, environ: publisher, rng=random.Random(seed), out=out.append)
        return code, "\n".join(out)

    def history(self, name="blogger_ko_history.json", root=None):
        path = Path(root or self.root) / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def drafts(self, folder="_blogger_ko_drafts"):
        path = self.root / folder
        return sorted(path.glob("*.md")) if path.exists() else []
