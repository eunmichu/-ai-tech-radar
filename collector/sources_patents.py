"""특허 수집 — KIPRIS Plus 국내(공개·등록 공보) + 해외(US·EP·JP·CN).

API 규약은 GitHub Actions 러너에서 실제 응답으로 확인된 것을 따른다.

              국내                              해외
  경로        /kipo-api/kipi/patUtiModInfo...   /openapi/rest/ForeignPatentAdvenced...
  키 파라미터 ServiceKey                        accessKey
  분류        ipcNumber                         ipc
  항목 태그   <item>                            <searchResult>
  성공 표시   resultCode=00                     resultCode 가 '빈 값'
  쪽넘김      pageNo + numOfRows                currentPage(=시작 위치!) + docsCount

KIPRIS 는 초당 호출 수를 넘기면 권한이 정지되므로 요청 사이에 간격을 둔다.
키는 환경변수(KIPRIS_KEY, GitHub Secret)로만 받고 로그에는 가려서 남긴다.
"""
from __future__ import annotations

import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from . import config, util
from .classify import Classifier, norm_ipc


def _txt(node: ET.Element, tag: str) -> str:
    return util.clean_text(node.findtext(tag) or "")


def _date(v: str) -> datetime | None:
    digits = "".join(ch for ch in (v or "") if ch.isdigit())[:8]
    return util.parse_date(digits, "Asia/Seoul") if len(digits) == 8 else None


def _ipcs(v: str) -> list[str]:
    out = []
    for part in re.split(r"[|,]", v or ""):
        c = norm_ipc(part)
        if c and c not in out:
            out.append(c)
    return out[:8]


def fmt_kr_no(n: str) -> str:
    """'1020240012345' → '10-2024-0012345'"""
    d = re.sub(r"\D", "", n or "")
    return f"{d[:2]}-{d[2:6]}-{d[6:]}" if len(d) == 13 else (n or "")


def fmt_kr_reg(n: str) -> str:
    """등록번호 '1029990010000' → '10-2999001'"""
    d = re.sub(r"\D", "", n or "")
    return f"{d[:2]}-{d[2:9]}" if len(d) == 13 and d.startswith("10") else (n or "")


def google_patents_kr(open_no: str, reg_no: str, fallback: str) -> str:
    """국내 공보 → Google Patents 문헌 주소(공개 A, 등록 B1). KIPRIS 상세는 외부에서 직접 열리지 않는다."""
    o = re.sub(r"\D", "", open_no or "")
    r = re.sub(r"\D", "", reg_no or "")
    if len(r) == 13 and r.startswith("10"):
        return f"https://patents.google.com/patent/KR{r[:9]}B1/ko"
    if len(o) == 13 and o.startswith("10"):
        return f"https://patents.google.com/patent/KR{o[2:6]}{o[6:]}A/ko"
    return "https://patents.google.com/?q=" + urllib.parse.quote(fallback) + "&hl=ko"


def _get_xml(url: str) -> ET.Element:
    raw = util.fetch(url, headers={"Accept": "application/xml"})
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        head = raw[:100].decode("utf-8", "replace").replace("\n", " ")
        raise RuntimeError(f"XML 이 아닌 응답(경로·키 확인): {head}") from None


def _window(now: datetime, days: int) -> str:
    end = now.astimezone(util.KST).date()
    return f"{(end - timedelta(days=days)).strftime('%Y%m%d')}~{end.strftime('%Y%m%d')}"


def _patent(*, key: str, title: str, url: str, date: datetime, summary: str, applicant: str,
            number: str, appno: str, office: str, ipcs: list[str], status: str,
            clf: Classifier, now: datetime) -> dict:
    return {
        "key": key,
        "id": util.short_id(key),
        "type": "patent",
        "title": title,
        "url": url,
        "source": f"KIPRIS {office}" if office != "KR" else "KIPRIS",
        "date": util.iso(min(date, now)),
        "summary": util.clip(summary, config.SUMMARY_MAX["patent"]),
        "lang": "ko" if util.is_korean(title) else "en",
        "cats": clf.classify(title, summary, ipcs=ipcs),
        "authors": applicant,
        "number": number,
        "appno": appno,
        "office": office,
        "ipc": ipcs[:4],
        "status": status,
    }


# ── 국내 ─────────────────────────────────────────────────────────
def _kr_item(it: ET.Element, clf: Classifier, now: datetime) -> dict | None:
    appno = _txt(it, "applicationNumber")
    open_no = _txt(it, "openNumber")
    reg_no = _txt(it, "registerNumber")
    pub_no = _txt(it, "publicationNumber")
    number = open_no or pub_no or reg_no or appno
    if not (appno or number):
        return None
    title = _txt(it, "inventionTitle") or number
    date = (_date(_txt(it, "openDate")) or _date(_txt(it, "publicationDate"))
            or _date(_txt(it, "registerDate")) or now)
    applicant = " · ".join(p.strip() for p in _txt(it, "applicantName").split("|") if p.strip())
    status = _txt(it, "registerStatus") or ("등록" if reg_no else "공개")
    appkey = re.sub(r"\D", "", appno) or number
    return _patent(
        key=f"pat:KR:{appkey}",
        title=title, url=google_patents_kr(open_no, reg_no, number), date=date,
        summary=_txt(it, "astrtCont"), applicant=applicant,
        number=fmt_kr_reg(reg_no) if status.startswith("등록") and reg_no else fmt_kr_no(number),
        appno=fmt_kr_no(appno), office="KR", ipcs=_ipcs(_txt(it, "ipcNumber")),
        status=status, clf=clf, now=now)


def _kr_query(params: dict, clf: Classifier, now: datetime) -> list[dict]:
    got: list[dict] = []
    page = 1
    while len(got) < config.KIPRIS_PER_QUERY:
        q = dict(params, patent="true", utility="false",
                 numOfRows=str(config.KIPRIS_ROWS), pageNo=str(page),
                 ServiceKey=config.KIPRIS_KEY)
        url = f"{config.KIPRIS_BASE}/{config.KIPRIS_SERVICE}/getAdvancedSearch?" + urllib.parse.urlencode(q)
        root = _get_xml(url)
        code = (root.findtext(".//resultCode") or "").strip()
        if code and code not in ("00", "0"):
            raise RuntimeError(f"resultCode={code} {(root.findtext('.//resultMsg') or '').strip()}")
        rows = root.findall(".//item")
        for it in rows:
            one = _kr_item(it, clf, now)
            if one:
                got.append(one)
        if len(rows) < config.KIPRIS_ROWS:
            break
        page += 1
        time.sleep(config.KIPRIS_DELAY)
    return got


def collect_kipris_kr(now: datetime, clf: Classifier) -> list[dict]:
    if not config.KIPRIS_KEY:
        raise RuntimeError("KIPRIS_KEY 가 없습니다(저장소 Secret 에 등록하면 특허가 수집됩니다)")
    window = _window(now, config.KIPRIS_LOOKBACK_DAYS)
    queries = [{"ipcNumber": p, "openDate": window} for p in config.KIPRIS_IPC]
    queries += [{"astrtCont": k, "openDate": window} for k in config.KIPRIS_KEYWORDS]
    out: dict[str, dict] = {}
    errors = []
    for q in queries:
        try:
            for it in _kr_query(q, clf, now):
                out.setdefault(it["key"], it)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{q.get('ipcNumber') or q.get('astrtCont')}: {util.redact(e)}")
        time.sleep(config.KIPRIS_DELAY)
    if errors and not out:
        raise RuntimeError("모든 질의 실패 — " + errors[0])
    if errors:
        print(f"  · KIPRIS 국내: {len(errors)}개 질의 실패 ({errors[0][:120]})")
    return list(out.values())


# ── 해외 ─────────────────────────────────────────────────────────
def _fr_item(n: ET.Element, clf: Classifier, now: datetime) -> dict | None:
    lit = _txt(n, "ltrtno")
    num = _txt(n, "openNumber") or _txt(n, "publishrNo") or _txt(n, "registerNo") or lit
    if not num:
        return None
    office = _txt(n, "countryCode") or "?"
    appno = _txt(n, "applicationNo")
    title = _txt(n, "inventionName") or num
    date = _date(_txt(n, "openDate")) or _date(_txt(n, "registerDate")) or now
    appkey = re.sub(r"[^0-9A-Za-z]", "", appno) or num
    return _patent(
        key=f"pat:{office}:{appkey}",
        title=title,
        url="https://patents.google.com/?q=" + urllib.parse.quote(lit or num),
        date=date, summary="", applicant=" · ".join(
            p.strip() for p in _txt(n, "applicant").split("|") if p.strip()),
        number=f"{office} {num}", appno=appno, office=office,
        ipcs=_ipcs(_txt(n, "ipc")), status="등록" if _txt(n, "registerNo") else "공개",
        clf=clf, now=now)


def collect_kipris_foreign(now: datetime, clf: Classifier) -> list[dict]:
    if not config.KIPRIS_KEY:
        raise RuntimeError("KIPRIS_KEY 가 없습니다")
    if not config.KIPRIS_FOREIGN:
        return []
    window = _window(now, config.FOREIGN_LOOKBACK_DAYS)
    out: dict[str, dict] = {}
    errors = []
    for ipc in config.FOREIGN_IPC:
        start = 1
        taken = 0
        while taken < config.FOREIGN_PER_QUERY:
            q = {"ipc": ipc, "openDate": window, "collectionValues": config.FOREIGN_COUNTRIES,
                 "currentPage": str(start), "docsCount": str(config.FOREIGN_ROWS),
                 "accessKey": config.KIPRIS_KEY}
            url = f"{config.FOREIGN_BASE}/{config.FOREIGN_SERVICE}/advancedSearch?" + urllib.parse.urlencode(q)
            try:
                root = _get_xml(url)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{ipc}: {util.redact(e)}")
                break
            code = (root.findtext(".//resultCode") or "").strip()
            if code:  # 해외는 '값이 있으면' 오류다
                errors.append(f"{ipc}: resultCode={code} {(root.findtext('.//resultMsg') or '').strip()}")
                break
            rows = root.findall(".//searchResult")
            for n in rows:
                one = _fr_item(n, clf, now)
                if one and one["key"] not in out:
                    out[one["key"]] = one
                    taken += 1
            if len(rows) < config.FOREIGN_ROWS:
                break
            start += config.FOREIGN_ROWS  # 쪽 번호가 아니라 시작 위치
            time.sleep(config.KIPRIS_DELAY)
    if errors and not out:
        raise RuntimeError("모든 질의 실패 — " + errors[0])
    return list(out.values())
