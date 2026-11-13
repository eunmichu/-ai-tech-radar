"""AI-Tech Radar 수집 설정.

분야·검색 동의어는 assets/taxonomy.json 에 있다(웹사이트와 공유).
여기에는 '어디서, 얼마나, 얼마나 자주' 모을지만 둔다. 숫자는 환경변수로 덮어쓸 수 있다.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = ROOT / "assets" / "taxonomy.json"
DATA_DIR = Path(os.getenv("ATR_DATA_DIR", ROOT / "data"))


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    return int(_f(name, default))


def _on(name: str, default: str = "on") -> bool:
    return os.getenv(name, default).strip().lower() not in ("0", "off", "false", "no")


# ── 수집 주기(시간) ─ 워크플로는 3시간마다 돌고, 아래 간격이 지난 유형만 실제로 수집한다.
INTERVAL_HOURS = {
    "news": _f("NEWS_EVERY_HOURS", 0),      # 매 실행
    "paper": _f("PAPER_EVERY_HOURS", 6),    # arXiv 는 하루 한 번 공지 → 6시간이면 충분
    "patent": _f("PATENT_EVERY_HOURS", 24),  # 공보는 하루 단위
}

# ── 보존 ─ 기간이 지나거나 개수를 넘으면 오래된 것부터 지운다.
RETENTION_DAYS = {
    "news": _i("NEWS_RETENTION_DAYS", 45),
    "paper": _i("PAPER_RETENTION_DAYS", 60),
    "patent": _i("PATENT_RETENTION_DAYS", 180),
}
MAX_ITEMS = {
    "news": _i("NEWS_MAX_ITEMS", 6000),
    "paper": _i("PAPER_MAX_ITEMS", 4000),
    "patent": _i("PATENT_MAX_ITEMS", 4000),
}
# 첫 화면이 빨리 뜨도록 최근 며칠치는 별도 파일(items-recent.json)로 나눈다.
RECENT_DAYS = _i("RECENT_DAYS", 7)
SUMMARY_MAX = {"news": 220, "paper": 320, "patent": 240}

# ── 중복 제거 ─ 같은 사건을 여러 매체가 낸 기사를 하나로 묶는다.
DEDUP_SIM = _f("DEDUP_SIM", 0.55)          # 제목 2-gram 자카드 유사도 임계값(0~1)
DEDUP_WINDOW_DAYS = _f("DEDUP_WINDOW_DAYS", 3)  # 이 기간 안의 기사끼리만 비교
ALSO_MAX = 8                               # '같은 소식' 으로 남길 다른 매체 수

REQUEST_TIMEOUT = _i("REQUEST_TIMEOUT", 25)

# ── 뉴스 ① Google 뉴스 RSS(키 불필요) ───────────────────────────────
GNEWS_WINDOW = os.getenv("GNEWS_WINDOW", "2d")   # 검색어에 when:2d 를 붙여 최근 기사만
GNEWS_PER_QUERY = _i("GNEWS_PER_QUERY", 25)
GNEWS_QUERIES = [
    # 한국어(국내 매체)
    {"q": "인공지능 OR 생성형 AI", "lang": "ko"},
    {"q": "LLM OR 거대언어모델 OR 언어모델", "lang": "ko"},
    {"q": "AI 에이전트", "lang": "ko"},
    {"q": "AI 반도체 OR NPU OR HBM", "lang": "ko"},
    {"q": "온디바이스 AI", "lang": "ko"},
    {"q": "AI 데이터센터", "lang": "ko"},
    {"q": "피지컬 AI OR 휴머노이드 로봇", "lang": "ko"},
    {"q": "자율주행 AI", "lang": "ko"},
    {"q": "의료 AI OR AI 신약", "lang": "ko"},
    {"q": "AI 기본법 OR AI 규제 OR AI 저작권", "lang": "ko"},
    {"q": "AI 스타트업 투자", "lang": "ko"},
    {"q": "AI 특허", "lang": "ko"},
    # 영어(해외 매체)
    {"q": "generative AI OR large language model", "lang": "en"},
    {"q": "AI agents", "lang": "en"},
    {"q": "AI chip OR Nvidia GPU OR HBM", "lang": "en"},
    {"q": "AI data center", "lang": "en"},
    {"q": "humanoid robot OR physical AI", "lang": "en"},
    {"q": "AI regulation OR AI Act", "lang": "en"},
]

# ── 뉴스 ② AI 전문 매체·연구소 RSS ──────────────────────────────────
# tz: 날짜에 시간대 표기가 없을 때 가정할 시간대(AI타임스는 'YYYY-MM-DD HH:MM:SS' KST).
FEEDS = [
    {"name": "AI타임스", "url": "https://www.aitimes.com/rss/allArticle.xml", "lang": "ko", "tz": "Asia/Seoul"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "lang": "en"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed", "lang": "en"},
    {"name": "The Verge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "lang": "en"},
    {"name": "OpenAI", "url": "https://openai.com/news/rss.xml", "lang": "en"},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "lang": "en"},
    {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml", "lang": "en"},
    {"name": "NVIDIA", "url": "https://blogs.nvidia.com/feed/", "lang": "en"},
]
FEED_LOOKBACK_DAYS = _i("FEED_LOOKBACK_DAYS", 7)
FEED_PER_SOURCE = _i("FEED_PER_SOURCE", 30)

# ── 논문 ① arXiv API(키 불필요, 요청 간 3초 이상 권장) ─────────────────
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_CATEGORIES = [s.strip() for s in os.getenv(
    "ARXIV_CATEGORIES", "cs.AI,cs.CL,cs.CV,cs.LG,cs.RO,cs.AR,cs.MA,eess.AS").split(",") if s.strip()]
ARXIV_PER_CATEGORY = _i("ARXIV_PER_CATEGORY", 40)
ARXIV_DELAY = _f("ARXIV_DELAY", 3.1)

# ── 논문 ② Hugging Face Daily Papers(커뮤니티가 고른 주목 논문, 추천수 포함) ──
HF_API = "https://huggingface.co/api/daily_papers"
HF_DAYS = _i("HF_DAYS", 3)            # 오늘 포함 며칠치 목록을 볼지

# ── 특허: KIPRIS Plus(키 필요 — 저장소 Secret KIPRIS_KEY) ─────────────
# 엔드포인트·파라미터는 GitHub Actions 러너에서 실제 응답으로 확인된 값이다.
KIPRIS_KEY = os.getenv("KIPRIS_KEY", "").strip()
KIPRIS_BASE = os.getenv("KIPRIS_BASE", "http://plus.kipris.or.kr/kipo-api/kipi")
KIPRIS_SERVICE = os.getenv("KIPRIS_SERVICE", "patUtiModInfoSearchSevice")  # 오타가 실제 경로
KIPRIS_LOOKBACK_DAYS = _i("KIPRIS_LOOKBACK_DAYS", 14)  # 매일 최근 14일 공개분을 다시 훑는다(지연 반영분 보충)
KIPRIS_ROWS = _i("KIPRIS_ROWS", 100)
KIPRIS_PER_QUERY = _i("KIPRIS_PER_QUERY", 400)
KIPRIS_DELAY = _f("KIPRIS_DELAY", 0.35)   # 초당 호출 수 제한(초과 시 권한 정지) 대비 여유
# AI 관련 IPC 접두. G06N=AI·기계학습, G06V=이미지·영상 인식, G10L15=음성인식,
# G06F40=자연어처리, G16H50=의료 AI 진단, B25J9/16=로봇 제어(학습), B60W60=자율주행
KIPRIS_IPC = [s.strip() for s in os.getenv(
    "KIPRIS_IPC", "G06N,G06V,G10L15,G06F40,G16H50,B25J9/16,B60W60").split(",") if s.strip()]
# IPC 밖에서 AI 를 쓰는 특허(예: G06Q 업무 자동화)를 초록 키워드로 보충한다. 비우면 끈다.
KIPRIS_KEYWORDS = [s.strip() for s in os.getenv(
    "KIPRIS_KEYWORDS", "인공지능,딥러닝,기계학습").split(",") if s.strip()]

KIPRIS_FOREIGN = _on("KIPRIS_FOREIGN", "on")
FOREIGN_BASE = os.getenv("FOREIGN_BASE", "http://plus.kipris.or.kr/openapi/rest")
FOREIGN_SERVICE = os.getenv("FOREIGN_SERVICE", "ForeignPatentAdvencedSearchService")  # 오타가 실제 경로
FOREIGN_COUNTRIES = os.getenv("FOREIGN_COUNTRIES", "US,EP,JP,CN")
FOREIGN_IPC = [s.strip() for s in os.getenv("FOREIGN_IPC", "G06N").split(",") if s.strip()]
FOREIGN_LOOKBACK_DAYS = _i("FOREIGN_LOOKBACK_DAYS", 10)
FOREIGN_ROWS = _i("FOREIGN_ROWS", 50)
FOREIGN_PER_QUERY = _i("FOREIGN_PER_QUERY", 200)
