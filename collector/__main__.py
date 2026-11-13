"""AI-Tech Radar 수집기 진입점.

    python -m collector                # 주기가 돌아온 유형만 수집(기본, Actions 용)
    python -m collector --force        # 주기와 상관없이 전부 수집
    python -m collector --only news    # 특정 유형만(news,paper,patent 쉼표 구분)
    python -m collector --demo         # 네트워크 없이 샘플 데이터 생성(화면 확인용)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path

from . import config, demo, sources_news, sources_papers, sources_patents, store, util
from .classify import Classifier, load_taxonomy

TYPES = ("news", "paper", "patent")


def _registry() -> list[tuple[str, str, callable]]:
    """(유형, 소스 이름, 수집 함수). 전문 매체 RSS 를 Google 뉴스보다 먼저 돌려
    같은 기사가 겹칠 때 언론사 직접 주소가 대표 링크가 되게 한다."""
    reg = []
    for spec in config.FEEDS:
        reg.append(("news", spec["name"], lambda now, clf, s=spec: sources_news.collect_feed(s, now, clf)))
    reg.append(("news", "Google 뉴스", sources_news.collect_google_news))
    reg.append(("paper", "arXiv", sources_papers.collect_arxiv))
    reg.append(("paper", "Hugging Face Papers", sources_papers.collect_hf))
    reg.append(("patent", "KIPRIS 국내", sources_patents.collect_kipris_kr))
    reg.append(("patent", "KIPRIS 해외", sources_patents.collect_kipris_foreign))
    return reg


def _due(meta: dict, now, force: bool, only: set[str] | None) -> list[str]:
    if only:
        return [t for t in TYPES if t in only]
    if force:
        return list(TYPES)
    due = []
    last = meta.get("last_run", {})
    for t in TYPES:
        prev = util.parse_iso(last.get(t))
        hours = config.INTERVAL_HOURS[t]
        # 10분 여유: 3시간 주기 실행이 몇 분 일찍 떠도 6·24시간 간격을 놓치지 않게
        if prev is None or now - prev >= timedelta(hours=hours) - timedelta(minutes=10):
            due.append(t)
    return due


def _summary_md(meta: dict, stats: dict, due: list[str]) -> str:
    lines = ["### AI-Tech Radar 수집 결과", "",
             f"- 수집 유형: {', '.join(due) or '없음(주기 미도래)'}",
             f"- 신규 {stats['new']} · 갱신 {stats['updated']} · 중복 병합 {stats['merged']}",
             f"- 누적: 뉴스 {meta['counts']['news']} · 논문 {meta['counts']['paper']} · 특허 {meta['counts']['patent']}",
             "", "| 소스 | 유형 | 상태 | 건수 | 메모 |", "|---|---|---|---:|---|"]
    for s in meta["sources"]:
        lines.append(f"| {s['name']} | {s['type']} | {'✅' if s['ok'] else '⚠️'} | {s.get('count', 0)} | "
                     f"{(s.get('error') or '').replace('|', '/')[:120]} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m collector", description="AI-Tech Radar 수집기")
    ap.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    ap.add_argument("--force", action="store_true", help="주기와 무관하게 모든 유형 수집")
    ap.add_argument("--only", default="", help="news,paper,patent 중 일부만 수집")
    ap.add_argument("--demo", action="store_true", help="샘플 데이터로 생성(네트워크 불필요)")
    args = ap.parse_args(argv)

    util.register_secret(config.KIPRIS_KEY)
    now = util.now_utc()
    taxonomy = load_taxonomy()
    clf = Classifier(taxonomy)
    items, meta = store.load(args.data_dir)
    if meta.get("demo") and not args.demo:
        print("이전 데이터가 샘플이라 비우고 실제 수집을 시작합니다.")
        items, meta = [], {}
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    if only and not only <= set(TYPES):
        ap.error(f"--only 는 {', '.join(TYPES)} 중에서 고르세요")

    prev_status = {s["name"]: s for s in meta.get("sources", [])}
    statuses: dict[str, dict] = {}
    incoming: list[dict] = []

    if args.demo:
        items, due = [], list(TYPES)
        incoming = demo.generate(now, clf)
        statuses["샘플 데이터"] = {"name": "샘플 데이터", "type": "demo", "ok": True,
                               "count": len(incoming), "error": None, "at": util.iso(now)}
    else:
        due = _due(meta, now, args.force, only)
        print(f"수집 유형: {', '.join(due) or '없음(주기 미도래 — 데이터만 다시 씀)'}")
        for typ, name, fn in _registry():
            if typ not in due:
                if name in prev_status:
                    statuses[name] = prev_status[name]
                continue
            try:
                got = fn(now, clf)
                incoming.extend(got)
                statuses[name] = {"name": name, "type": typ, "ok": True, "count": len(got),
                                  "error": None, "at": util.iso(now)}
                print(f"  ✓ {name}: {len(got)}건")
            except Exception as e:  # noqa: BLE001 — 소스 하나가 죽어도 나머지는 계속
                msg = util.redact(str(e))[:300]
                statuses[name] = {"name": name, "type": typ, "ok": False, "count": 0,
                                  "error": msg, "at": util.iso(now)}
                print(f"  ✗ {name}: {msg}")

    items, stats = store.merge(items, incoming, now)
    items = store.trim(items, now)

    last_run = dict(meta.get("last_run", {}))
    for t in due:
        last_run[t] = util.iso(now)
    counts = {t: sum(1 for i in items if i["type"] == t) for t in TYPES}
    meta = {
        "generated": util.iso(now),
        "demo": bool(args.demo),
        "last_run": last_run,
        "counts": counts,
        "recent_days": config.RECENT_DAYS,
        "retention_days": config.RETENTION_DAYS,
        "sources": list(statuses.values()),
    }
    store.save(args.data_dir, items, meta, now)
    print(f"신규 {stats['new']} · 갱신 {stats['updated']} · 중복 병합 {stats['merged']} · "
          f"오래되어 제외 {stats['stale']} → 누적 {counts}")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(_summary_md(meta, stats, due))
    return 0


if __name__ == "__main__":
    sys.exit(main())
