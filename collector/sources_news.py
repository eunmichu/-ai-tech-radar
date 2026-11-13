"""뉴스 수집 — Google 뉴스 RSS(한·영 검색어) + AI 전문 매체·연구소 RSS."""
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta

from . import config, util
from .classify import Classifier
from .feeds import parse_feed

GNEWS = {
    "ko": "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko",
    "en": "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
}


def _split_source(title: str) -> tuple[str, str]:
    """Google 뉴스 제목 '헤드라인 - 언론사' 에서 언론사를 떼어 낸다."""
    if " - " in title:
        head, _, src = title.rpartition(" - ")
        if head.strip() and 0 < len(src.strip()) <= 30:
            return head.strip(), src.strip()
    return title.strip(), ""


def _useful_summary(summary: str, title: str) -> str:
    """요약이 제목 반복(Google 뉴스 기본 description)이면 버린다."""
    s = util.clean_text(summary)
    if len(s) < 20:  # 매체명·링크 조각뿐인 요약
        return ""
    t = re.sub(r"\W+", "", title.lower())
    if re.sub(r"\W+", "", s.lower()).startswith(t[: max(8, len(t) // 2)]):
        return ""
    return s


def _make(title: str, url: str, source: str, date: datetime, summary: str, lang: str,
          clf: Classifier, now: datetime, via: str) -> dict:
    from .dedup import canon_url
    key = "url:" + canon_url(url)
    return {
        "key": key,
        "id": util.short_id(key),
        "type": "news",
        "title": title,
        "url": url,
        "source": source or urllib.parse.urlsplit(url).netloc.replace("www.", ""),
        "date": util.iso(min(date, now)),
        "summary": util.clip(summary, config.SUMMARY_MAX["news"]),
        "lang": lang,
        "cats": clf.classify(title, summary),
        "via": via,
    }


def collect_google_news(now: datetime, clf: Classifier) -> list[dict]:
    out: list[dict] = []
    errors = []
    for spec in config.GNEWS_QUERIES:
        q = f"{spec['q']} when:{config.GNEWS_WINDOW}"
        url = GNEWS[spec.get("lang", "ko")].format(q=urllib.parse.quote(q))
        try:
            rows = parse_feed(util.fetch(url))
        except Exception as e:  # noqa: BLE001 — 검색어 하나 실패는 건너뛴다
            errors.append(f"{spec['q']}: {e}")
            continue
        rows.sort(key=lambda r: util.parse_date(r["date"], "UTC") or now, reverse=True)
        for r in rows[: config.GNEWS_PER_QUERY]:
            if not r["title"] or not r["link"]:
                continue
            title, src_tail = _split_source(util.clean_text(r["title"]))
            source = r["source"] or src_tail
            date = util.parse_date(r["date"], "UTC") or now
            out.append(_make(title, r["link"], source, date,
                             _useful_summary(r["summary"], title),
                             "ko" if util.is_korean(title) else spec.get("lang", "ko"),
                             clf, now, "gnews"))
    if errors and not out:
        raise RuntimeError("모든 검색어 실패 — " + errors[0])
    if errors:
        print(f"  · Google 뉴스: 검색어 {len(errors)}개 실패 (첫 오류: {errors[0][:120]})")
    return out


def collect_feed(spec: dict, now: datetime, clf: Classifier) -> list[dict]:
    rows = parse_feed(util.fetch(spec["url"]))
    oldest = now - timedelta(days=config.FEED_LOOKBACK_DAYS)
    out = []
    for r in rows:
        title = util.clean_text(r["title"])
        if not title or not r["link"]:
            continue
        date = util.parse_date(r["date"], spec.get("tz", "UTC")) or now
        if date < oldest:
            continue
        summary = util.clean_text(r["summary"])
        out.append(_make(title, r["link"], spec["name"], date, summary,
                         "ko" if util.is_korean(title) else spec.get("lang", "en"),
                         clf, now, "feed"))
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[: config.FEED_PER_SOURCE]
