# Kanggaemi

시장 데이터 자동 수집부터 종목별 투자 전략 리포트 생성까지 연결하는 데이터 기반 투자 분석 에이전트입니다.

사용자가 분석할 종목·지수와 투자 시점을 입력하면, 최신 적재 데이터를 기준으로 이슈에 영향을 받는 시장 환경을 매크로·수급·산업·밸류에이션 관점에서 분석하고 종합적인 투자 전망과 실행 전략을 제시합니다.

> 본 프로젝트의 결과는 투자 판단을 지원하기 위한 분석 자료이며, 개인화된 투자 자문이나 수익을 보장하는 권유가 아닙니다.

## 프로젝트 배경

기존 월 단위 보고서는 급변하는 시장을 적시에 반영하기 어렵습니다. 전쟁, 금리 불안, 환율 변동처럼 시장 변동성을 키우는 사건이 발생하면 하루 중에도 시장 방향이 바뀔 수 있지만, 정적 보고서는 사용자가 실제 투자 결정을 내려야 하는 시점과 원하는 종목에 맞는 분석을 제공하지 못합니다.

또한 작성자가 여러 출처의 데이터를 직접 수집하고 정리해야 하므로 분석보다 반복 업무에 많은 시간이 소요됩니다.

Kanggaemi는 다음 목표를 중심으로 이 문제를 해결합니다.

> 입력된 종목에 맞게 이슈, 매크로, 수급, 산업, 밸류에이션 관점으로 분석하고 종합적인 투자 전망 및 투자 전략을 제시한다.

## 기대효과

- 월간 정적 정보 제공에서 벗어나 시장 변화에 맞춰 종목별 투자 전략을 즉시 업데이트합니다.
- 분석에 필요한 시장·종목 데이터를 자동으로 적재해 수작업을 줄이고 업무 효율을 높입니다.
- 사용자 질의와 투자기간에 맞는 전망과 전략을 제공해 고객 응대 속도와 품질을 개선합니다.
- 분석 근거의 데이터셋, 관측값, 기준일을 함께 남겨 결과를 추적하고 검증할 수 있습니다.

## 주요 기능

### 데이터 수집과 배치 오케스트레이션

- 주식·지수·국내외 선물 가격
- 시가총액 상위 종목 유니버스
- 투자자 수급과 프로그램 매매
- 환율, 금리, 매크로 지표, 증시자금
- 기업 재무와 밸류에이션
- 국내외 선물 마스터와 활성월물 롤오버
- 대상 단위 재시도, 부분 실패 격리, 중복 실행 방지, JSON 구조화 로그
- cron과 Airflow에서 동일하게 호출할 수 있는 멱등 CLI

### 투자 전략 리포트 에이전트

```mermaid
flowchart LR
    Q["사용자 질의"] --> C["자산 분류·마스터 grounding"]
    C --> P["팩터 계획"]
    P --> M["매크로 분석"]
    P --> F["수급 분석"]
    P --> I["산업 분석"]
    P --> V["밸류에이션 분석"]
    M --> S["종합 판단"]
    F --> S
    I --> S
    V --> S
    S --> E["품질 평가"]
    E -->|"보완 필요"| S
    E -->|"통과 또는 수정 상한"| R["한국어 리포트"]
```

- 종목명은 LLM이 코드를 생성하지 않고 종목 마스터에서 검증합니다.
- `factor_catalog.yaml`에 등록된 active 팩터만 분석합니다.
- 분석 노드는 DB에 적재된 데이터를 `as_of_date` 기준으로 조회합니다.
- 미래 데이터를 참조하지 않는 point-in-time 분석을 적용합니다.
- 근거가 없는 팩터는 제외하고 부족한 데이터와 한계를 보고서에 표시합니다.
- 유니버스 밖 종목의 데이터가 부족하면 기존 수집 서비스를 한 번 호출해 보완합니다.
- 종합 결과는 근거 충분성, 최신성, 논리 일관성, 위험 인식 등을 평가한 후 필요하면 재작성합니다.
- LangGraph 상태는 PostgreSQL의 PostgresSaver로 체크포인트됩니다.

### Streamlit 웹 화면

- 질의와 분석 기준일 입력
- LangGraph 노드별 시작·완료·실패 상태 실시간 표시
- 실제 에이전트와 Mock 데모 어댑터 선택
- 최종 Markdown 리포트 표시
- 사내 한글 폰트를 포함한 PDF 생성 및 다운로드

## 아키텍처

```text
외부 데이터 API
      │
      ▼
scraper → service → repository → PostgreSQL
                              │
                    batch CLI / cron / Airflow
                              │
                              ▼
사용자 질의 → LangGraph agent → feature engine(as_of) → 투자 전략 리포트
                    │
                    ▼
             Streamlit / PDF
```

에이전트와 데이터의 동작 계약은 다음 YAML을 단일 소스로 사용합니다.

- `backend/app/core/data_specs.yaml`: 데이터셋 grain, key, unit, caveat
- `backend/app/core/factor_catalog.yaml`: 분석 팩터, transform, 해석 방법, 상태
- `backend/app/core/asset_class_taxonomy.yaml`: 자산군 분류 정책
- `backend/app/core/asset_taxonomy.yaml`: 검증된 자산 인스턴스 캐시
- `backend/app/core/node_specs.yaml`: 노드 입출력, 실행 순서, 평가 기준, 리포트 구조

## 기술 스택

- Python 3
- FastAPI, Pydantic
- SQLAlchemy, PostgreSQL
- LangGraph, OpenAI API, PostgresSaver
- Streamlit
- WeasyPrint
- PyYAML, pandas
- pytest

## 디렉터리 구조

```text
kanggaemi/
├─ backend/
│  ├─ app/
│  │  ├─ agent/          # LangGraph, feature engine, 분석 노드
│  │  ├─ batch/          # 외부 스케줄러용 배치 오케스트레이션
│  │  ├─ core/           # 데이터·팩터·자산·노드 계약 YAML
│  │  ├─ models/         # SQLAlchemy 모델
│  │  ├─ repositories/   # DB 접근
│  │  ├─ scrapers/       # 외부 API 수집
│  │  └─ services/       # 도메인 수집·upsert 서비스
│  ├─ frontend/          # Streamlit, 이벤트 어댑터, PDF
│  ├─ deploy/            # cron과 Airflow 예시
│  ├─ docs/              # 배치·에이전트 상세 문서
│  ├─ scripts/           # 마스터와 테이블 초기화 도구
│  └─ tests/
└─ docker-compose.yml    # PostgreSQL 개발 환경
```

## 시작하기

### 1. PostgreSQL 실행

프로젝트 루트에서 실행합니다.

```powershell
docker compose up -d db
```

### 2. Python 의존성 설치

```powershell
cd backend
python -m pip install -r requirements.txt
python -m pip install -r frontend/requirements.txt
```

### 3. 환경변수 설정

루트 `.env`에 환경별 값을 설정합니다. 비밀키는 저장소에 커밋하지 않습니다.

```dotenv
DATABASE_URL=postgresql+psycopg2://kanggaemi:kanggaemi_dev_pw@localhost:5432/kanggaemi
OPENAI_API_KEY=...
LLM_MODEL=gpt-4o-mini

KIS_APPKEY=...
KIS_SECRETKEY=...
ECOS_API_KEY=...
```

실제로 사용하는 수집 도메인에 따라 추가 API 키가 필요할 수 있습니다.

### 4. API 서버 실행

```powershell
python -m uvicorn app.main:app --reload
```

- API 문서: `http://127.0.0.1:8000/docs`
- Health API: `http://127.0.0.1:8000/api/v1/health`

### 5. 데이터 적재

먼저 주요 작업을 dry-run으로 확인할 수 있습니다.

```powershell
python -m app.batch.run universe-refresh --dry-run
python -m app.batch.run stock-prices --dry-run
python -m app.batch.run futures-sync --dry-run
```

실제 적재 예시:

```powershell
python -m app.batch.run universe-refresh
python -m app.batch.run stock-prices --since 20260101
python -m app.batch.run market-indices
python -m app.batch.run macro-indicators
python -m app.batch.run yield-rates
python -m app.batch.run exchange-rates
```

전체 job, 선행조건, 선물 롤오버, cron/Airflow 설정은 [`backend/docs/batch.md`](backend/docs/batch.md)를 참고하세요.

### 6. 에이전트 CLI 실행

PostgresSaver 테이블 초기화가 필요한 첫 실행:

```powershell
python -m app.agent.run_report "삼성전자 3개월 전망 분석해줘" `
  --as-of 2026-07-18 `
  --setup-checkpointer
```

이후 실행에서는 `--setup-checkpointer`를 생략합니다.

```powershell
python -m app.agent.run_report "코스피 한 달 전망 분석해줘" --as-of 2026-07-18
```

에이전트의 데이터 계약과 분석 동작은 [`backend/docs/agent_flow_slice.md`](backend/docs/agent_flow_slice.md)를 참고하세요.

### 7. 웹 화면 실행

PDF용 사내 TTF/OTF 폰트를 다음 디렉터리에 넣습니다.

```text
backend/frontend/assets/fonts/
```

해당 디렉터리에 폰트가 하나만 있으면 자동으로 선택합니다. 여러 개라면 환경변수로 지정합니다.

```powershell
$env:KANGGAEMI_PDF_FONT_FILE="KBFGText-Medium.otf"
$env:KANGGAEMI_PDF_FONT_FAMILY="KBFGText"
python -m streamlit run frontend/app.py
```

사이드바에서 실제 LangGraph와 Mock 데모를 선택할 수 있습니다. 상세 설정은 [`backend/frontend/README.md`](backend/frontend/README.md)를 참고하세요.

## 테스트

```powershell
cd backend
python -m pytest
python -m pytest frontend/tests -q
```

## 운영 원칙

- 애플리케이션은 스케줄을 소유하지 않으며 cron 또는 Airflow가 배치 CLI를 호출합니다.
- 저장 시각은 UTC, 업무 스케줄과 시장 기준은 Asia/Seoul을 사용합니다.
- 수집과 분석은 멱등성과 point-in-time 재현성을 우선합니다.
- 기존 도메인 수집 서비스와 분석 오케스트레이션을 분리합니다.
- API 키와 사내 폰트 파일은 커밋하지 않습니다.
- 데이터 부족, 추정값, 최신성 한계는 숨기지 않고 근거와 함께 표시합니다.
