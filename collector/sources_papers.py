"""논문 수집 — arXiv API(분야별 최신) + Hugging Face Daily Papers(주목 논문·추천수)."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from . import config, util
from .classify import Classifier

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARX = "{http://arxiv.org/schemas/atom}"
_ID = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?$")


def arxiv_id(s: str) -> str:
    m = _ID.search((s or "").strip().rstrip("/"))
    return m.group(1) if m else ""


def _paper(aid: str, title: str, summary: str, authors: list[str], date: datetime,
           primary: str, cats: list[str], clf: Classifier, now: datetime) -> dict:
    key = f"arxiv:{aid}"
    return {
        "key": key,
        "id": util.short_id(key),
        "type": "paper",
        "title": title,
        "url": f"https://arxiv.org/abs/{aid}",
        "source": "arXiv",
        "date": util.iso(min(date, now)),
        "summary": util.clip(summary, config.SUMMARY_MAX["paper"]),
        "lang": "en",
        "cats": clf.classify(title, summary, arxiv_primary=primary, arxiv_cats=cats),
        "authors": util.join_authors(authors),
        "arxiv": aid,
        "pdf": f"https://arxiv.org/pdf/{aid}",
        "acat": primary,
    }


def parse_arxiv(data: bytes, clf: Classifier, now: datetime) -> list[dict]:
    root = ET.fromstring(data)
    out = []
    for e in root.findall(f"{_ATOM}entry"):
        aid = arxiv_id(e.findtext(f"{_ATOM}id") or "")
        if not aid:
            continue
        title = util.clean_text(e.findtext(f"{_ATOM}title"))
        summary = util.clean_text(e.findtext(f"{_ATOM}summary"))
        authors = [a.findtext(f"{_ATOM}name") or "" for a in e.findall(f"{_ATOM}author")]
        date = util.parse_date(e.findtext(f"{_ATOM}published"), "UTC") or now
        pc = e.find(f"{_ARX}primary_category")
        primary = pc.attrib.get("term", "") if pc is not None else ""
        cats = [c.attrib.get("term", "") for c in e.findall(f"{_ATOM}category")]
        out.append(_paper(aid, title, summary, authors, date, primary, cats, clf, now))
    return out


def collect_arxiv(now: datetime, clf: Classifier) -> list[dict]:
    out: list[dict] = []
    errors = []
    for i, cat in enumerate(config.ARXIV_CATEGORIES):
        if i:
            time.sleep(config.ARXIV_DELAY)  # arXiv API 이용 지침: 요청 간 3초
        q = urllib.parse.urlencode({
            "search_query": f"cat:{cat}", "sortBy": "submittedDate",
            "sortOrder": "descending", "start": 0, "max_results": config.ARXIV_PER_CATEGORY})
        try:
            got = parse_arxiv(util.fetch(f"{config.ARXIV_API}?{q}", timeout=40), clf, now)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{cat}: {e}")
            continue
        out.extend(got)
    if errors and not out:
        raise RuntimeError("모든 분류 실패 — " + errors[0])
    if errors:
        print(f"  · arXiv: {len(errors)}개 분류 실패 ({errors[0][:120]})")
    return out


def parse_hf(data: bytes, clf: Classifier, now: datetime) -> list[dict]:
    rows = json.loads(data.decode("utf-8"))
    out = []
    for row in rows if isinstance(rows, list) else []:
        p = row.get("paper") or {}
        aid = arxiv_id(p.get("id", ""))
        if not aid:
            continue
        title = util.clean_text(p.get("title") or row.get("title"))
        abstract = util.clean_text(p.get("summary") or row.get("summary"))
        ai_sum = util.clean_text(p.get("ai_summary"))
        date = util.parse_date(p.get("publishedAt") or row.get("publishedAt"), "UTC") or now
        it = _paper(aid, title, abstract, [a.get("name", "") for a in p.get("authors") or []],
                    date, "", [], clf, now)
        it["cats"] = clf.classify(title, abstract + " " + " ".join(p.get("ai_keywords") or []))
        it["hf"] = True
        if ai_sum:
            it["hf_sum"] = util.clip(ai_sum, 220)
        it["upvotes"] = int(p.get("upvotes") or 0)
        if p.get("githubRepo"):
            it["code"] = p["githubRepo"]
        kws = [k for k in (p.get("ai_keywords") or []) if isinstance(k, str)][:8]
        if kws:
            it["kw"] = kws
        out.append(it)
    return out


def collect_hf(now: datetime, clf: Classifier) -> list[dict]:
    out: list[dict] = []
    errors = []
    for d in range(config.HF_DAYS):
        day = (now - timedelta(days=d)).strftime("%Y-%m-%d")
        try:
            out.extend(parse_hf(util.fetch(f"{config.HF_API}?date={day}&limit=100"), clf, now))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{day}: {e}")
    if errors and not out:
        raise RuntimeError(errors[0])
    return out
