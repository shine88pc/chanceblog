"""허용 경로 접두어 경계: 확장자가 있는 파일 경로는 완전 일치만 받는다(BP-S1-12, 결함 D-420). 네트워크 없이 돈다.

배경: path_matches 는 접두어가 `/` 로 끝나지 않으면 `경로 == 접두어` 또는 `경로가 접두어 + "/" 로 시작`을 받았다 — 허용 경로 `/products/noaa-scales.json` 에 `/products/noaa-scales.json/anything` 이 통과했다.
어댑터가 요청 경로를 제품 파일 하나로 못박고(생성 주소는 어댑터가 만든다) NOAA 쪽에서는 404 일 뿐이라 실제 요청으로 이어지지는 않았지만, 파일 이름 뒤에 경로가 이어질 수는 없으므로 닫는다.
기존 허용 경로는 전부 그대로 통과한다(레지스트리의 모든 허용 경로 대조).
"""
import datetime
import unittest

import _bootstrap  # noqa: F401
from pipeline import egress
from pipeline import source_registry as sr

TODAY = datetime.date(2026, 11, 23)
NOAA_HOST = "services.swpc.noaa.gov"


class PathMatchesFilePrefixTest(unittest.TestCase):
    def test_a_file_path_prefix_accepts_only_the_exact_path(self):
        for prefix in ("/products/noaa-scales.json", "/en/rss.xml", "/n1/rss/dai-quo/0-eng.atom", "/openapi/index/index.jsp", "/brd/m_580/view.do", "/press/2026/10/20261018-1_j.html"):
            with self.subTest(prefix=prefix):
                self.assertTrue(sr.path_matches(prefix, (prefix,)))
                for tail in ("/anything", "/", "/x/y", "/..", "x", ".evil", "2"):
                    self.assertFalse(sr.path_matches(prefix + tail, (prefix,)), prefix + tail)

    def test_the_audit_probe_case(self):
        self.assertFalse(sr.path_matches("/products/noaa-scales.json/anything", ("/products/noaa-scales.json",)))
        self.assertTrue(sr.path_matches("/products/noaa-scales.json", ("/products/noaa-scales.json",)))

    def test_directory_and_extensionless_prefixes_keep_the_old_boundary_rule(self):
        cases = [("/feed", ("/feed",), True), ("/feed/x", ("/feed",), True), ("/feedback", ("/feed",), False), ("/api/x", ("/api/",), True), ("/api", ("/api/",), True),
                 ("/node/2/rss_en", ("/node/2/rss_en",), True), ("/node/2/rss_en/x", ("/node/2/rss_en",), True), ("/noaa-scales-explanation/x", ("/noaa-scales-explanation",), True),
                 ("/v1.0/items", ("/v1.0",), True),                                   # 글자로 시작하지 않는 '확장자' 는 버전 조각이다 — 파일이 아니다
                 ("/data/v2/x", ("/data/v2",), True), ("/", (), True), ("/anything", (), True)]
        for path, prefixes, expected in cases:
            with self.subTest(path=path, prefixes=prefixes):
                self.assertEqual(sr.path_matches(path, prefixes), expected)

    def test_a_mixed_prefix_list_still_matches_when_any_prefix_does(self):
        prefixes = ("/products/noaa-scales.json", "/news/", "/feed")
        self.assertTrue(sr.path_matches("/products/noaa-scales.json", prefixes))
        self.assertFalse(sr.path_matches("/products/noaa-scales.json/anything", prefixes))
        self.assertTrue(sr.path_matches("/news/a", prefixes))
        self.assertTrue(sr.path_matches("/feed/a", prefixes))


class RegistryPathsTest(unittest.TestCase):
    def setUp(self):
        self.registry = sr.load_registry(today=TODAY)

    def all_prefixes(self):
        found = []
        for provider in self.registry.providers():
            for access in provider.access:
                for prefix in access.paths:
                    found.append((provider.provider_id, access, prefix))
        return found

    def test_every_allowed_path_of_the_real_registry_still_passes_as_itself(self):
        found = self.all_prefixes()
        self.assertGreater(len(found), 50)
        for provider_id, access, prefix in found:
            with self.subTest(provider=provider_id, prefix=prefix):
                self.assertTrue(sr.path_matches(prefix.rstrip("/") or "/", access.paths) or prefix == "/", prefix)
                self.assertTrue(sr.path_matches(prefix, access.paths), prefix)

    def test_directory_prefixes_still_accept_a_child_and_file_prefixes_do_not(self):
        files, directories = 0, 0
        for provider_id, access, prefix in self.all_prefixes():
            with self.subTest(provider=provider_id, prefix=prefix):
                if prefix.endswith("/"):
                    directories += 1
                    self.assertTrue(sr.path_matches(prefix + "child", access.paths), prefix)
                elif sr._FILE_LIKE_PREFIX.search(prefix):
                    files += 1
                    self.assertFalse(sr.path_matches(prefix + "/child", (prefix,)), prefix)
                else:
                    self.assertTrue(sr.path_matches(prefix + "/child", (prefix,)), prefix)          # 확장자 없는 접두어는 이전과 같다
        self.assertGreater(files, 15)                                                                 # 파일 경로가 실제로 많다(탐지가 빈 그릇이 아니다)
        self.assertGreater(directories, 10)

    def test_the_gate_allows_the_noaa_product_files_and_denies_a_tail_after_them(self):
        noaa = self.registry.get("noaa_swpc_json")
        paths = [prefix for access in noaa.access for prefix in access.paths]
        self.assertIn("/products/noaa-scales.json", paths)
        for path in paths:
            with self.subTest(path=path):
                egress.check_url(f"https://{NOAA_HOST}{path}", "fact", self.registry)                       # 정확한 경로는 통과(예외가 나면 실패)
                with self.assertRaises(egress.EgressDenied):
                    egress.check_url(f"https://{NOAA_HOST}{path}/anything", "fact", self.registry)


if __name__ == "__main__":
    unittest.main()
