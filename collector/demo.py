"""화면 확인용 샘플 데이터(네트워크 불필요). 실제 기사·논문·특허가 아니다.

`python -m collector --demo` 로 만들며 meta.json 에 demo=true 가 기록되어
웹사이트 상단에 '샘플 데이터' 안내가 표시된다. 링크는 모두 example.com 이다.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import util
from .classify import Classifier

NEWS_KO = [
    "온디바이스 LLM 경량화 기법 잇따라 공개…스마트폰 탑재 경쟁",
    "AI 데이터센터 전력 수요 급증, 액침냉각 기술 도입 확산",
    "AI 데이터센터 전력수요 급증…액침 냉각 기술 도입 확산 조짐",
    "HBM 수요 확대에 메모리 업계 증설 경쟁 본격화",
    "국산 NPU 기반 추론 서버 실증 사업 착수",
    "AI 에이전트가 사내 결재·보고서 작성까지…업무 자동화 확산",
    "멀티 에이전트 협업 프레임워크 오픈소스로 공개",
    "휴머노이드 로봇 양산 앞두고 핵심 부품 공급망 재편",
    "피지컬 AI 실증 단지 조성…제조 현장 로봇 학습 데이터 확보",
    "자율주행 레벨4 시범 운행 구역 확대",
    "의료 AI 영상판독 보조 솔루션, 임상 현장 도입 속도",
    "AI 신약 후보물질 발굴 기간 단축 사례 늘어",
    "AI 기본법 하위법령 의견 수렴 시작…고영향 AI 기준 쟁점",
    "생성형 AI 저작권 분쟁, 학습 데이터 공정이용 판단 주목",
    "딥페이크 탐지 기술 고도화…선거철 앞두고 대응 강화",
    "AI 스타트업 투자 회복세, 3분기 펀딩 규모 전년 대비 증가",
    "음성합성 AI로 콜센터 상담 품질 개선",
    "실시간 통역 이어폰, 온디바이스 음성인식 정확도 높여",
    "멀티모달 모델로 영상 검색 정확도 개선",
    "텍스트로 동영상 만드는 생성형 AI, 광고 제작 현장 확산",
    "AI 반도체 설계 인력 부족…산학 공동 교육 과정 신설",
    "강화학습으로 물류센터 로봇 동선 최적화",
    "AI 특허 출원 증가세…생성형 AI 분야 두드러져",
    "거대언어모델 한국어 성능 평가 벤치마크 공개",
    "검색증강생성(RAG) 도입한 공공 민원 챗봇 시범 운영",
]
NEWS_EN = [
    "Open-weight reasoning models narrow the gap with frontier systems",
    "Data center operators race to secure power for AI training clusters",
    "New benchmark measures how well AI agents use real software tools",
    "Humanoid robot startups shift focus from demos to factory pilots",
    "Regulators publish draft guidance on general-purpose AI transparency",
    "Inference chips built for long-context models gain traction",
    "Diffusion models move into scientific simulation workloads",
    "Speech models now run fully on-device on mid-range phones",
]
PAPERS = [
    ("Efficient Long-Context Attention via Learned Token Routing", "cs.CL"),
    ("Agentic Retrieval: Planning Multi-Step Search for Question Answering", "cs.CL"),
    ("A Survey of Tool-Using Language Model Agents", "cs.MA"),
    ("Scaling Laws for Mixture-of-Experts Under Fixed Inference Budgets", "cs.LG"),
    ("Self-Supervised Video World Models for Robot Manipulation", "cs.RO"),
    ("Sim-to-Real Transfer for Humanoid Locomotion with Diffusion Policies", "cs.RO"),
    ("Training-Free Quantization of Vision-Language Models to 4 Bits", "cs.CV"),
    ("Consistent Text-to-Video Generation with Temporal Latent Alignment", "cs.CV"),
    ("Open-Vocabulary 3D Object Detection from Multi-View Images", "cs.CV"),
    ("Low-Latency Streaming Speech Recognition with State Space Models", "eess.AS"),
    ("Expressive Zero-Shot Text-to-Speech with Prosody Tokens", "eess.AS"),
    ("Processing-in-Memory Accelerators for Transformer Inference", "cs.AR"),
    ("KV Cache Compression for Serving Large Language Models at Scale", "cs.DC"),
    ("Reinforcement Learning from Verifiable Rewards for Math Reasoning", "cs.LG"),
    ("Red Teaming Multimodal Models: A Taxonomy of Failure Modes", "cs.CY"),
    ("Protein Language Models for Antibody Design", "q-bio.QM"),
    ("Clinical Report Generation from Chest X-rays with Grounded LLMs", "cs.CV"),
    ("Federated Fine-Tuning of Foundation Models on Edge Devices", "cs.LG"),
    ("Benchmarking Korean Language Understanding in Open LLMs", "cs.CL"),
    ("Synthetic Data Pipelines for Instruction Tuning: What Matters", "cs.CL"),
]
PATENTS = [
    ("인공 신경망 모델의 양자화 방법 및 장치", ["G06N3/0495", "G06N3/08"]),
    ("거대 언어 모델을 이용한 질의 응답 시스템 및 방법", ["G06F40/30", "G06N3/0455"]),
    ("멀티 에이전트 기반 작업 자동화 장치", ["G06N5/043", "G06F9/48"]),
    ("영상 내 객체를 인식하는 딥러닝 모델의 학습 방법", ["G06V10/82", "G06N3/08"]),
    ("텍스트로부터 이미지를 생성하는 확산 모델 기반 장치", ["G06T11/00", "G06N3/0475"]),
    ("로봇 팔의 파지 동작을 강화학습으로 제어하는 방법", ["B25J9/16", "G06N3/092"]),
    ("자율주행 차량의 경로 예측을 위한 신경망 장치", ["B60W60/00", "G06N3/04"]),
    ("뉴럴 프로세싱 유닛의 메모리 접근 최적화 방법", ["G06N3/063", "G06F12/08"]),
    ("데이터센터 서버의 냉각 제어를 위한 인공지능 시스템", ["H05K7/20", "G06N20/00"]),
    ("의료 영상 기반 질병 진단 보조 인공지능 장치", ["G16H50/20", "G06V10/82"]),
    ("음성 인식 모델의 온디바이스 경량화 방법", ["G10L15/16", "G06N3/08"]),
    ("화자 음성을 합성하는 방법 및 장치", ["G10L13/02"]),
    ("학습 데이터의 편향을 보정하는 기계학습 방법", ["G06N20/00"]),
    ("Method for training a neural network with sparse attention", ["G06N3/045"]),
    ("System for verifying outputs of a generative model", ["G06N3/0475", "G06F40/40"]),
]
SRC_KO = ["샘플일보", "샘플테크", "샘플경제", "가상IT뉴스", "데모신문"]
SRC_EN = ["Sample Tech Weekly", "Demo Wire", "Example AI News"]
APPL = ["샘플전자 주식회사", "가상대학교 산학협력단", "데모로보틱스", "예시반도체", "Sample Corp.", "Demo Labs Inc."]


def generate(now: datetime, clf: Classifier, days: int = 14) -> list[dict]:
    rnd = random.Random(20261113)
    out: list[dict] = []

    def when(max_days: float) -> datetime:
        return now - timedelta(hours=rnd.uniform(0.3, max_days * 24))

    for n, title in enumerate(NEWS_KO * 2):
        src = rnd.choice(SRC_KO)
        url = f"https://example.com/news/{n}"
        key = "url:" + url
        summary = "샘플 기사 요약입니다. 실제 수집 시에는 각 매체가 RSS 로 제공한 요약 문장이 들어갑니다."
        out.append({"key": key, "id": util.short_id(key), "type": "news", "title": title, "url": url,
                    "source": src, "date": util.iso(when(days)), "summary": summary, "lang": "ko",
                    "cats": clf.classify(title, summary)})
    for n, title in enumerate(NEWS_EN):
        url = f"https://example.com/en/{n}"
        key = "url:" + url
        out.append({"key": key, "id": util.short_id(key), "type": "news", "title": title, "url": url,
                    "source": rnd.choice(SRC_EN), "date": util.iso(when(days)),
                    "summary": "Sample summary text for layout preview.", "lang": "en",
                    "cats": clf.classify(title)})
    for n, (title, acat) in enumerate(PAPERS * 2):
        key = f"demo-paper:{n}"
        title2 = title if n < len(PAPERS) else title.replace(":", " —", 1) + " (v2 sample)"
        hf = rnd.random() < 0.35
        it = {"key": key, "id": util.short_id(key), "type": "paper", "title": title2,
              "url": f"https://example.com/paper/{n}", "source": "arXiv", "date": util.iso(when(days)),
              "summary": "Sample abstract. We propose a method and evaluate it on standard benchmarks, "
                         "showing consistent improvements over strong baselines.",
              "lang": "en", "authors": util.join_authors(["Author A", "Author B", "Author C", "Author D", "Author E"]),
              "acat": acat, "cats": clf.classify(title, arxiv_primary=acat)}
        if hf:
            it.update(hf=True, upvotes=rnd.randint(5, 180),
                      hf_sum="한 줄 요약 예시: 제안 기법이 추론 비용을 줄이면서 성능을 유지한다.")
        out.append(it)
    for n, (title, ipcs) in enumerate(PATENTS * 2):
        key = f"demo-patent:{n}"
        ko = util.is_korean(title)
        out.append({"key": key, "id": util.short_id(key), "type": "patent", "title": title,
                    "url": f"https://example.com/patent/{n}", "source": "KIPRIS" if ko else "KIPRIS US",
                    "date": util.iso(when(days).replace(hour=0, minute=0, second=0)),
                    "summary": "샘플 초록입니다. 실제 수집 시에는 공보의 요약이 들어갑니다." if ko else "",
                    "lang": "ko" if ko else "en", "authors": rnd.choice(APPL),
                    "number": f"샘플-{n:04d}", "appno": f"샘플출원-{n:04d}",
                    "office": "KR" if ko else "US", "ipc": ipcs, "status": rnd.choice(["공개", "공개", "등록"]),
                    "cats": clf.classify(title, ipcs=ipcs)})
    return out
