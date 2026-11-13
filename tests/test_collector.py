"""수집기 오프라인 테스트 — 네트워크 대신 tests/fixtures 의 응답을 끼워 전체 경로를 실행한다.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collector import __main__ as cli  # noqa: E402
from collector import config, dedup, feeds, sources_patents, store, util  # noqa: E402
from collector.classify import Classifier, load_taxonomy  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
NOW = datetime(2026, 11, 13, 6, 30, tzinfo=timezone.utc)  # 15:30 KST
KEY = "TESTKEY+/=abc"


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


class FakeNet:
    """URL 에 따라 고정 응답을 돌려주고 호출 기록을 남긴다."""

    EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, url: str, **_kw) -> bytes:
        self.calls.append(url)
        if "news.google.com" in url:
            return fixture("gnews_ko.xml")
        if "aitimes.com" in url:
            return fixture("aitimes.xml")
        if "theverge.com" in url:
            return fixture("verge_atom.xml")
        if "openai.com" in url:
            raise RuntimeError("https://openai.com/news/rss.xml 요청 실패: HTTP Error 503")
        if "export.arxiv.org" in url:
            return fixture("arxiv.xml")
        if "huggingface.co/api/daily_papers" in url:
            return fixture("hf.json")
        if "getAdvancedSearch" in url:
            return fixture("kipris_kr.xml")
        if "ForeignPatentAdvencedSearchService" in url:
            return fixture("kipris_foreign.xml")
        return self.EMPTY_RSS

    def count(self, part: str) -> int:
        return sum(1 for u in self.calls if part in u)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.net = FakeNet()
        self.patches = [
            mock.patch.object(util, "fetch", self.net),
            mock.patch.object(util, "now_utc", lambda: NOW),
            mock.patch.object(config, "ARXIV_DELAY", 0),
            mock.patch.object(config, "KIPRIS_DELAY", 0),
            mock.patch.object(config, "KIPRIS_KEY", KEY),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args: str) -> tuple[list[dict], dict]:
        with mock.patch("sys.stdout"):
            self.assertEqual(cli.main(["--data-dir", str(self.tmp), *args]), 0)
        items, meta = store.load(self.tmp)
        return items, meta

    def by(self, items, pred):
        found = [i for i in items if pred(i)]
        self.assertTrue(found, "조건에 맞는 항목이 없다")
        return found[0]

    def test_full_run(self):
        items, meta = self.run_cli("--force")
        counts = meta["counts"]
        self.assertEqual(counts, {"news": 5, "paper": 3, "patent": 3})

        # 뉴스: Google 뉴스 리디렉트 대신 언론사 직접 주소가 대표, 다른 매체는 '같은 소식'
        chip = self.by(items, lambda i: "온디바이스 AI 칩" in i["title"])
        self.assertTrue(chip["url"].startswith("https://www.aitimes.com/news/articleView.html?idxno=900001"))
        self.assertEqual([a["source"] for a in chip.get("also", [])], ["테스트경제"])
        self.assertIn("chip", chip["cats"])
        # 시간대 없는 국내 RSS 날짜는 KST 로 해석
        self.assertEqual(chip["date"], "2026-11-13T03:00:00Z")  # 가장 이른 보도 시각(Google 뉴스 03:00Z)
        # 오래된 RSS 항목은 버린다
        self.assertFalse(any("아주 오래된" in i["title"] for i in items))
        # Google 뉴스 기본 description(제목 반복)은 요약으로 쓰지 않는다
        law = self.by(items, lambda i: "기본법" in i["title"])
        self.assertEqual(law["summary"], "")
        self.assertEqual(law["source"], "테스트일보")
        self.assertIn("policy", law["cats"])
        atom = self.by(items, lambda i: "reasoning model" in i["title"])
        self.assertEqual(atom["date"], "2026-11-12T20:00:00Z")

        # 논문: arXiv 와 HF 가 같은 논문으로 합쳐지고 추천수가 붙는다
        p1 = self.by(items, lambda i: i.get("arxiv") == "2611.99001")
        self.assertTrue(p1["hf"])
        self.assertEqual(p1["upvotes"], 42)
        self.assertEqual(p1["acat"], "cs.CL")
        self.assertEqual(p1["authors"], "Author A, Author B, Author C 외 1명")
        self.assertEqual(p1["title"], "Test Paper: Efficient Agents for Tool Use")
        self.assertEqual(p1["code"], "https://github.com/example/test-agents")
        self.assertIn("agent", p1["cats"])
        self.assertEqual(p1["url"], "https://arxiv.org/abs/2611.99001")
        robot = self.by(items, lambda i: i.get("arxiv") == "2611.99002")
        self.assertIn("robot", robot["cats"])

        # 특허: 출원번호 기준 중복 제거, 번호 표기, Google Patents 링크
        kr = self.by(items, lambda i: i["type"] == "patent" and "양자화" in i["title"])
        self.assertEqual(kr["number"], "10-2026-0099001")
        self.assertEqual(kr["appno"], "10-2025-0099001")
        self.assertEqual(kr["url"], "https://patents.google.com/patent/KR20260099001A/ko")
        self.assertEqual(kr["authors"], "테스트전자주식회사 · 테스트대학교산학협력단")
        self.assertEqual(kr["date"], "2026-11-09T15:00:00Z")  # 공개일 11-10 KST 자정
        self.assertIn("ml", kr["cats"])
        reg = self.by(items, lambda i: i["type"] == "patent" and "의료" in i["title"])
        self.assertEqual(reg["number"], "10-2999001")
        self.assertEqual(reg["url"], "https://patents.google.com/patent/KR102999001B1/ko")
        self.assertIn("health", reg["cats"])
        us = self.by(items, lambda i: i.get("office") == "US")
        self.assertEqual(us["number"], "US 20269999001")
        self.assertIn("US20269999001A1", us["url"])

        # 소스 상태: 실패한 소스도 기록되고, 나머지는 계속 수집된다
        st = {s["name"]: s for s in meta["sources"]}
        self.assertFalse(st["OpenAI"]["ok"])
        self.assertTrue(st["AI타임스"]["ok"])
        self.assertTrue(st["KIPRIS 국내"]["ok"])
        # 키가 URL·로그·meta 어디에도 남지 않는다
        raw = (self.tmp / "meta.json").read_text(encoding="utf-8")
        self.assertNotIn(KEY, raw)
        # 파일 분할: 최근 7일 / 그 이전
        recent = json.loads((self.tmp / "items-recent.json").read_text(encoding="utf-8"))["items"]
        archive = json.loads((self.tmp / "items-archive.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(recent) + len(archive), len(items))
        cut = util.iso(NOW - timedelta(days=config.RECENT_DAYS))
        self.assertTrue(all(i["date"] >= cut for i in recent))
        self.assertEqual([i["office"] for i in archive], ["US"])  # 11-05 공개분은 7일 밖

    def test_rerun_is_idempotent(self):
        first, _ = self.run_cli("--force")
        again, _ = self.run_cli("--force")
        self.assertEqual(len(first), len(again))
        self.assertEqual(sorted(i["id"] for i in first), sorted(i["id"] for i in again))
        chip = self.by(again, lambda i: "온디바이스 AI 칩" in i["title"])
        self.assertEqual(len(chip.get("also", [])), 1)

    def test_interval_gating(self):
        self.run_cli("--force")
        n_arxiv, n_kipris = self.net.count("export.arxiv.org"), self.net.count("getAdvancedSearch")
        later = NOW + timedelta(hours=3)
        with mock.patch.object(util, "now_utc", lambda: later):
            _, meta = self.run_cli()
        self.assertEqual(self.net.count("export.arxiv.org"), n_arxiv)      # 논문은 6시간 주기 → 건너뜀
        self.assertEqual(self.net.count("getAdvancedSearch"), n_kipris)    # 특허는 24시간 주기 → 건너뜀
        self.assertEqual(meta["last_run"]["news"], util.iso(later))
        self.assertEqual(meta["last_run"]["paper"], util.iso(NOW))
        # 건너뛴 소스의 이전 상태는 유지된다
        self.assertIn("arXiv", {s["name"] for s in meta["sources"]})

    def test_no_kipris_key(self):
        with mock.patch.object(config, "KIPRIS_KEY", ""):
            items, meta = self.run_cli("--force")
        st = {s["name"]: s for s in meta["sources"]}
        self.assertFalse(st["KIPRIS 국내"]["ok"])
        self.assertIn("KIPRIS_KEY", st["KIPRIS 국내"]["error"])
        self.assertEqual(meta["counts"]["patent"], 0)
        self.assertGreater(meta["counts"]["news"], 0)

    def test_demo_then_real_starts_clean(self):
        _, meta = self.run_cli("--demo")
        self.assertTrue(meta["demo"])
        items, meta = self.run_cli("--force")
        self.assertFalse(meta["demo"])
        self.assertFalse(any("example.com/news" in i["url"] for i in items))


class UnitTest(unittest.TestCase):
    def setUp(self):
        self.clf = Classifier(load_taxonomy())

    def test_canon_url(self):
        a = dedup.canon_url("https://www.Example.com/a/b/?utm_source=x&id=3&fbclid=y#top")
        b = dedup.canon_url("http://example.com/a/b?id=3")
        self.assertEqual(a, b)

    def test_norm_title(self):
        self.assertEqual(dedup.norm_title("[단독] 엔비디아, 새 칩 공개 (종합) - 테스트일보"),
                         dedup.norm_title("엔비디아 새 칩 공개"))

    def test_similarity_threshold(self):
        idx = dedup.TitleIndex(0.55, 3)
        base = {"key": "a", "type": "news", "title": "삼성전자, 차세대 HBM4 양산 돌입…AI 반도체 공략"}
        idx.add(base, NOW)
        near = {"key": "b", "type": "news", "title": "삼성전자 차세대 HBM4 양산 돌입, AI반도체 시장 공략"}
        far = {"key": "c", "type": "news", "title": "SK하이닉스, HBM4 샘플 공급 시작"}
        self.assertEqual(idx.find(near, NOW), "a")
        self.assertIsNone(idx.find(far, NOW))
        self.assertIsNone(idx.find(near, NOW + timedelta(days=5)))  # 기간 밖은 비교하지 않는다

    def test_parse_dates(self):
        self.assertEqual(util.iso(util.parse_date("2026-11-13 07:00:00")), "2026-11-12T22:00:00Z")
        self.assertEqual(util.iso(util.parse_date("Thu, 12 Nov 2026 22:42:51 +0000")), "2026-11-12T22:42:51Z")
        self.assertEqual(util.iso(util.parse_date("2026-10-07T20:00:00.000Z")), "2026-10-07T20:00:00Z")
        self.assertEqual(util.iso(util.parse_date("20261110")), "2026-11-09T15:00:00Z")
        self.assertIsNone(util.parse_date("not a date"))

    def test_feed_with_html_entities(self):
        data = b'<rss><channel><item><title>A&nbsp;B &middot; C</title><link>https://x.y/1</link></item></channel></rss>'
        rows = feeds.parse_feed(data)
        self.assertEqual(util.clean_text(rows[0]["title"]), "A B · C")

    def test_classify(self):
        c = self.clf.classify
        self.assertIn("llm", c("KV Cache Compression for Serving Large Language Models"))
        self.assertEqual(c("정부, AI 기본법 시행령 입법예고")[0], "policy")
        self.assertIn("chip", c("엔비디아 차세대 GPU 공개"))
        self.assertIn("robot", c("Test", ipcs=["B25J 9/16"]))
        self.assertIn("vision", c("x", arxiv_primary="cs.CV"))
        self.assertEqual(c("오늘의 날씨"), ["etc"])
        self.assertNotIn("llm", c("Storage drag test"))  # 'rag' 가 단어 안에서 걸리지 않는다

    def test_redact(self):
        util.register_secret(KEY)
        msg = util.redact(f"http://x/y?accessKey={KEY} and ServiceKey=TESTKEY%2B%2F%3Dabc")
        self.assertNotIn(KEY, msg)
        self.assertNotIn("TESTKEY%2B%2F%3Dabc", msg)

    def test_trim(self):
        old = {"key": "o", "id": "o", "type": "news", "title": "t", "url": "u",
               "date": util.iso(NOW - timedelta(days=config.RETENTION_DAYS["news"] + 1))}
        new = dict(old, key="n", id="n", date=util.iso(NOW))
        self.assertEqual([i["key"] for i in store.trim([old, new], NOW)], ["n"])

    def test_kr_numbers(self):
        self.assertEqual(sources_patents.fmt_kr_no("1020240012345"), "10-2024-0012345")
        self.assertEqual(sources_patents.google_patents_kr("1020240012345", "", "x"),
                         "https://patents.google.com/patent/KR20240012345A/ko")


if __name__ == "__main__":
    unittest.main()
