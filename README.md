# AI-Tech Radar

AI **뉴스·논문·특허**를 한곳에 모아 분야·날짜별로 보고, 한국어로 검색하는 정적 웹사이트입니다.
GitHub Actions가 3시간마다 수집해 GitHub Pages에 자동 배포합니다. 서버·DB·외부 패키지가 필요 없습니다.

```
https://<계정>.github.io/<저장소>/#tab=news&cat=datacenter&period=today
```

## 주요 기능

| 기능 | 내용 |
|---|---|
| 통합 수집 | 뉴스(Google 뉴스 한·영 + AI 전문 매체 RSS 8곳), 논문(arXiv 8개 분류 + Hugging Face Daily Papers), 특허(KIPRIS Plus 국내 + US·EP·JP·CN) |
| 한국어 검색 | 띄어쓰기 무시(`생성형AI` = `생성형 AI`), 한↔영 동의어(`엔비디아` → Nvidia), 초성 검색(`ㅎㅁㄴㅇㄷ` → 휴머노이드), 제외어 `-단어`, 구문 `"…"`, `A|B`, 조사 제거(`엔비디아의`), 출원인·저자·출원번호·arXiv 번호 검색, 일치 부분 강조 |
| 필터 | 유형(전체/뉴스/논문/특허), 기간(오늘·3일·7일·30일·전체·기간 지정), 분야 11개(복수 선택), 저장한 항목 |
| 정렬 | 최신순(날짜별 묶음), 관련도순, 화제순(같은 소식을 낸 매체 수·HF 추천 수) |
| 중복 제거 | ① URL 정규화(추적 파라미터·www 제거) ② arXiv ID로 arXiv·HF 병합 ③ 출원번호로 공개·등록공보 병합 ④ 제목 2-gram 유사도로 같은 사건 기사를 묶어 "같은 소식 N곳"으로 표시 |
| 출처 링크 | 모든 항목은 원문으로 연결(Google 뉴스 리디렉트보다 언론사 직접 주소 우선, 논문은 PDF·코드·HF, 특허는 Google Patents) |
| 분포 보기 | 분야 레이더(유형별 겹쳐 그림, 축 이름을 누르면 필터)와 14일 막대(누르면 그날만) |
| 공유 | 모든 필터 상태가 주소(`#tab=…&cat=…&period=…&q=…`)에 남아 링크로 공유 |
| 기타 | 다크 모드, 모바일, 새 항목 표시(지난 방문 이후), 별표 저장(브라우저 보관), `/` 키로 검색창 이동 |

## 폴더 구성

```
index.html               화면(한 장)
assets/
  app.js                 화면 로직(필터·정렬·그리기)
  search.js              한국어 검색 엔진(동의어·초성·띄어쓰기)
  style.css              디자인
  taxonomy.json          ★ 분야 정의 + 분류 키워드 + 검색 동의어 (수집기와 화면이 함께 씀)
collector/               수집기(파이썬 표준 라이브러리만 사용)
  config.py              ★ 수집 소스·검색어·주기·보존 기간
  sources_news.py        Google 뉴스 RSS, 매체 RSS
  sources_papers.py      arXiv API, Hugging Face Daily Papers
  sources_patents.py     KIPRIS Plus 국내·해외
  classify.py            분야 분류(키워드·arXiv 분류·IPC)
  dedup.py               중복 제거(URL 정규화, 제목 유사도)
  store.py               누적·병합·보존 기간 정리·파일 분할
  demo.py                화면 확인용 샘플 데이터
tools/build_snapshot.py  데이터까지 담은 단일 HTML 파일 만들기(메일 첨부·오프라인 열람용)
tests/                   오프라인 테스트(파이썬 14개, 검색 9개)
.github/workflows/update.yml   3시간마다 수집 → gh-pages 배포
```

수집 결과는 `data/items-recent.json`(최근 7일, 첫 화면용), `data/items-archive.json`(그 이전, 뒤에서 불러옴),
`data/meta.json`(갱신 시각·소스별 상태)으로 나뉘며 **gh-pages 브랜치에만** 쌓입니다.

## GitHub Pages에 올리기 (처음 한 번)

1. **저장소 만들기** — GitHub에서 새 저장소(예: `ai-tech-radar`, Public)를 만들고 이 폴더 내용을 올립니다.
   ```bash
   cd ai-tech-radar
   git init && git add . && git commit -m "AI-Tech Radar"
   git branch -M main
   git remote add origin https://github.com/<계정>/ai-tech-radar.git
   git push -u origin main
   ```
   웹에서 올릴 때는 `.github` 폴더까지 포함되었는지 확인하세요.
2. **KIPRIS 키 등록(특허를 받으려면)** — Settings → Secrets and variables → Actions → New repository secret
   - Name: `KIPRIS_KEY` / Value: KIPRIS Plus(plus.kipris.or.kr)에서 발급받은 인증키
   - 국내 검색(특허·실용신안 정보)과 해외 특허 검색 서비스 사용 신청이 되어 있어야 합니다.
   - 키가 없어도 뉴스·논문은 정상 수집되고, 화면의 "수집 상태"에 특허가 '실패(KIPRIS_KEY 없음)'로 표시됩니다.
3. **첫 실행** — Actions 탭 → `AI-Tech Radar 수집·배포` → **Run workflow**. 3~5분 뒤 `gh-pages` 브랜치가 생깁니다.
   (Actions가 꺼져 있으면 "I understand my workflows…" 버튼으로 켭니다.)
4. **Pages 켜기** — Settings → Pages → Build and deployment → Source: **Deploy from a branch** →
   Branch: **gh-pages** / **(root)** → Save.
5. 1~2분 뒤 `https://<계정>.github.io/ai-tech-radar/` 에서 열립니다. 이후에는 3시간마다 자동으로 갱신됩니다.

> 워크플로가 `Permission denied`로 push에 실패하면 Settings → Actions → General → Workflow permissions를
> **Read and write permissions**로 바꾸세요(조직 정책으로 막혀 있을 때).

## 내 컴퓨터에서 실행

파이썬 3.10 이상만 있으면 됩니다(설치할 패키지 없음).

```bash
cd ai-tech-radar

# 1) 실제 수집 (KIPRIS 키는 선택)
export KIPRIS_KEY="발급받은키"          # Windows PowerShell: $env:KIPRIS_KEY="발급받은키"
python -m collector --force

# 또는 네트워크 없이 샘플 데이터로 화면만 확인
python -m collector --demo

# 2) 웹서버로 열기 (index.html 을 더블클릭하면 브라우저 보안 때문에 데이터를 못 읽습니다)
python -m http.server 8000
# → http://localhost:8000
```

수집기 옵션

| 명령 | 동작 |
|---|---|
| `python -m collector` | 주기가 돌아온 유형만 수집(Actions 기본) |
| `python -m collector --force` | 뉴스·논문·특허 모두 지금 수집 |
| `python -m collector --only news,paper` | 일부 유형만 |
| `python -m collector --demo` | 샘플 데이터 생성(상단에 "샘플" 안내 표시, 실제 수집 시 자동으로 지워짐) |

테스트: `python -m unittest discover -s tests -v` · `node --test tests/search.test.mjs`

단일 파일 스냅숏: `python tools/build_snapshot.py -o radar.html --days 14` → 서버 없이 더블클릭으로 열리는
HTML 한 장(최근 14일치 데이터 포함)이 만들어집니다. 보고·공유용으로 메일에 첨부할 수 있습니다.

## 바꾸고 싶을 때

| 바꿀 것 | 위치 |
|---|---|
| 분야 추가·이름 변경, 분류 키워드, IPC·arXiv 분류 매핑 | `assets/taxonomy.json` → `categories` |
| 검색 동의어(한↔영) | `assets/taxonomy.json` → `synonyms` (한 줄이 한 묶음) |
| 뉴스 검색어, 매체 RSS 추가 | `collector/config.py` → `GNEWS_QUERIES`, `FEEDS` |
| arXiv 분류, 분류당 건수 | `ARXIV_CATEGORIES`, `ARXIV_PER_CATEGORY` (환경변수로도 가능) |
| 특허 IPC·키워드·조회 기간·대상국 | `KIPRIS_IPC`, `KIPRIS_KEYWORDS`, `KIPRIS_LOOKBACK_DAYS`, `FOREIGN_COUNTRIES` |
| 유형별 수집 주기 | `NEWS_EVERY_HOURS`(0), `PAPER_EVERY_HOURS`(6), `PATENT_EVERY_HOURS`(24) |
| 보존 기간·최대 건수 | `NEWS_RETENTION_DAYS`(45) 등, `NEWS_MAX_ITEMS`(6000) 등 |
| 중복 판정 민감도 | `DEDUP_SIM`(0.55, 높을수록 엄격), `DEDUP_WINDOW_DAYS`(3) |
| 실행 시각 | `.github/workflows/update.yml` 의 `cron` (UTC 기준, KST−9) |
| 색·글꼴 | `assets/style.css` 맨 위 `:root` 변수 |

숫자 설정은 워크플로의 `env:`에 넣어 코드 수정 없이 바꿀 수도 있습니다.

## 주소 파라미터

| 키 | 값 | 예 |
|---|---|---|
| `tab` | `news` `paper` `patent` (없으면 전체) | `tab=paper` |
| `cat` | 분야 키, 쉼표로 여러 개 | `cat=llm,chip` |
| `period` | `today` `3d` `7d`(기본) `30d` `all` `custom` | `period=today` |
| `from`, `to` | `YYYY-MM-DD` (`period=custom`) | `from=2026-11-01&to=2026-11-13` |
| `q` | 검색어 | `q=온디바이스` |
| `sort` | `latest` `relevance` `hot` | `sort=hot` |

분야 키: `llm` LLM·생성형 AI · `agent` AI 에이전트 · `vision` 비전·멀티모달 · `robot` 로봇·자율주행 ·
`chip` AI 반도체·하드웨어 · `datacenter` 데이터센터·인프라 · `health` 의료·바이오 AI · `speech` 음성·오디오 ·
`policy` 정책·안전·윤리 · `ml` ML·학습 알고리즘 · `biz` 산업·비즈니스 · `etc` 일반·기타

## 알아 두면 좋은 점

- **분야 분류는 규칙 기반**입니다(제목 키워드 가중 + arXiv 분류 + 특허 IPC). 한 항목에 최대 3개 분야가 붙고,
  애매하면 '일반·기타'로 갑니다. 잘못 분류되는 표현은 `taxonomy.json` 키워드를 고치면 다음 수집부터 반영됩니다.
- **한영 교차 중복**(같은 사건의 한국어 기사와 영어 기사)은 묶지 않습니다. 제목 유사도는 같은 언어에서만 의미가 있습니다.
- **Google 뉴스 링크**는 news.google.com 경유 주소입니다. 같은 기사가 매체 RSS로도 들어오면 직접 주소로 바뀝니다.
- **특허 링크**는 Google Patents로 연결합니다(KIPRIS 공보 상세는 외부 링크로 직접 열리지 않음). 막 공개된 공보는
  Google Patents 반영이 며칠 늦을 수 있습니다. 카드의 공개·등록번호(마우스를 올리면 출원번호)로 KIPRIS에서 바로 찾을 수 있습니다.
- **KIPRIS 호출 속도**: 초당 호출 한도를 넘으면 키 권한이 정지될 수 있어 요청 사이에 0.35초 간격을 둡니다(`KIPRIS_DELAY`).
- **arXiv 이용 지침**에 따라 요청 사이 3초 간격을 둡니다. arXiv는 하루 한 번 공지하므로 6시간 주기로 충분합니다.
- **저작권**: 제목·짧은 요약·링크만 보관·표시합니다. 원문은 각 출처에서 보세요.
- 공개 저장소의 예약 실행은 저장소 활동이 60일간 없으면 GitHub가 멈출 수 있습니다. 멈추면 Actions 탭에서 다시 켜면 됩니다.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 화면에 "아직 수집된 데이터가 없습니다" | Actions에서 워크플로를 한 번 실행했는지, Pages 소스가 `gh-pages`인지 |
| 특허가 0건 | 화면 하단 "수집 상태" → KIPRIS 오류 문구. 키 Secret 이름(`KIPRIS_KEY`), 서비스 사용 신청 여부 |
| 특정 매체만 실패 | 해당 RSS 주소가 바뀐 경우가 많습니다. `config.py`의 `FEEDS`에서 주소를 고치거나 지우세요 |
| 갱신이 멈춤 | Actions 탭에서 예약 실행이 꺼졌는지(60일 비활성) 확인 |
| 로컬에서 빈 화면 | `index.html`을 파일로 열지 말고 `python -m http.server`로 여세요 |
