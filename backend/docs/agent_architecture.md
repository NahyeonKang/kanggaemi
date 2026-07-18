# 투자 전략 리포트 에이전트 상세 설계 및 구현 가이드

## 1. 문서 목적

이 문서는 kanggaemi 투자 전략 리포트 에이전트의 구조, 데이터 흐름, 핵심 구현 방식, 실행 방법과 확장 절차를 설명한다. 코드 리뷰, 운영 인수인계, 신규 팩터 및 분석 차원 추가 시 기준 문서로 사용하는 것을 목적으로 한다.

현재 구현은 다음 질문에 답하도록 설계되어 있다.

- 사용자가 언급한 자산이 무엇인지 어떻게 확정하는가?
- 어떤 분석 팩터를 선택하며, 선택 근거는 어디에 정의되는가?
- 미래 데이터 혼입 없이 DB의 적재 데이터를 어떻게 읽는가?
- 매크로·수급·산업·밸류에이션 분석을 어떻게 병렬 처리하는가?
- LLM이 데이터나 종목 코드를 임의로 만들지 못하게 어떻게 통제하는가?
- 평가 실패 시 재작성은 몇 번 수행되고 어떻게 종료되는가?
- CLI와 Streamlit이 동일한 그래프를 어떻게 실행하는가?

## 2. 전체 구조 요약

에이전트는 외부 API를 직접 상시 조회하는 시스템이 아니다. 배치가 PostgreSQL에 적재한 데이터를 feature engine이 point-in-time 방식으로 읽고, 계약에 등록된 팩터만 계산한 뒤, LLM이 그 근거를 해석하고 보고서로 조합한다.

```mermaid
flowchart LR
    API["외부 데이터 API"] --> BATCH["Batch 수집·upsert"]
    BATCH --> DB[(PostgreSQL)]

    USER["사용자 질의"] --> GRAPH["LangGraph"]
    YAML["core/*.yaml 계약"] --> GRAPH
    MASTER["종목 마스터"] --> CLASSIFY["자산 grounding"]
    DB --> FEATURE["Feature Engine"]
    FEATURE --> GRAPH
    GRAPH --> REPORT["한국어 투자 전략 리포트"]
    GRAPH --> CHECKPOINT[(PostgresSaver)]
    REPORT --> CLI["CLI"]
    REPORT --> UI["Streamlit"]
```

핵심 원칙은 다음과 같다.

1. **계약 우선**: 자산군, 데이터셋, 팩터, 노드 정의는 `app/core/*.yaml`을 단일 기준으로 사용한다.
2. **Grounding 우선**: LLM은 자산명을 추출하지만 종목 코드는 만들지 않는다. 종목 마스터가 코드를 확정한다.
3. **Point-in-time 조회**: 모든 근거는 `observation_date <= as_of_date` 범위에서만 읽는다.
4. **근거 없는 팩터 제외**: 데이터가 부족하면 임의 추정하지 않고 `missing_reason`으로 남긴다.
5. **정적 그래프, 병렬 분석**: 토폴로지는 고정하고 분석 노드는 factory로 생성한다.
6. **유한한 평가 루프**: 평가 실패 시 재작성하되 설정된 상한에서 반드시 종료한다.
7. **실행 인터페이스 분리**: CLI와 프론트는 그래프 내부 로직을 복제하지 않는다.

## 3. 주요 디렉터리와 책임

| 경로 | 책임 |
|---|---|
| `app/core/data_specs.yaml` | 데이터셋의 grain, key, unit, 시점 컬럼, caveat 정의 |
| `app/core/factor_catalog.yaml` | 팩터의 차원, 데이터셋, transform, 해석, 상태 정의 |
| `app/core/asset_class_taxonomy.yaml` | 지원 자산군과 적용 가능한 분석 차원 정의 |
| `app/core/asset_taxonomy.yaml` | 확인된 자산 인스턴스 캐시 |
| `app/core/node_specs.yaml` | 노드 입출력, 실행 순서, 평가 기준, 보고서 구조 정의 |
| `app/agent/contracts.py` | YAML 계약을 런타임에서 검증하는 Pydantic 모델 |
| `app/agent/state.py` | LangGraph 공유 state 스키마 |
| `app/agent/assets.py` | 자산 캐시 조회, 종목 마스터 grounding, 캐시 append |
| `app/agent/catalog.py` | YAML 로딩과 자산군 정책 조회 |
| `app/agent/feature_engine.py` | DB 시계열 조회, transform 계산, fetch-on-miss, evidence 생성 |
| `app/agent/nodes.py` | classify, plan, analyzer, synthesize, evaluate, formatter 구현 |
| `app/agent/graph.py` | LangGraph 토폴로지 구성 |
| `app/agent/llm.py` | 자산 추출용 LLM 경계 |
| `app/agent/reasoning.py` | 종합 판단 및 평가용 LLM 경계 |
| `app/agent/run_flow_slice.py` | flow 수직 슬라이스 CLI |
| `app/agent/run_report.py` | 전체 보고서 CLI |
| `frontend/adapters/langgraph.py` | LangGraph task 이벤트를 프론트 NodeEvent로 변환 |
| `frontend/adapters/mock.py` | 백엔드 없이 동작하는 YAML 기반 mock 이벤트 스트림 |

## 4. 그래프 토폴로지

전체 그래프는 다음 순서로 실행된다.

```mermaid
flowchart TD
    START([START]) --> C["classify_node"]
    C --> P["plan_node"]
    P --> M["macro_node"]
    P --> F["flow_node"]
    P --> I["industry_node"]
    P --> V["valuation_node"]
    M --> S["synthesize_node"]
    F --> S
    I --> S
    V --> S
    S --> E["evaluate_node"]
    E -->|"통과 또는 재작성 상한 도달"| R["report_formatter_node"]
    E -->|"미통과이고 상한 미도달"| S
    R --> END([END])
```

`plan_node` 이후의 네 분석 노드는 동시에 실행할 수 있다. 각 노드는 state의 서로 다른 키에만 결과를 기록한다.

- `macro_node` → `macro_result`
- `flow_node` → `flow_result`
- `industry_node` → `industry_result`
- `valuation_node` → `valuation_result`

LangGraph의 join edge는 네 분석 노드가 끝난 뒤에만 `synthesize_node`를 실행한다. 이 구조로 병렬 write 충돌과 일부 결과를 누락한 조기 종합을 방지한다.

## 5. State 설계

`InvestmentAgentState`는 `TypedDict(total=False)`로 정의한다. 노드마다 필요한 키만 읽고 자신의 책임 범위에 해당하는 키만 반환한다.

| 그룹 | 주요 필드 | 설명 |
|---|---|---|
| 실행 입력 | `run_id`, `user_query`, `as_of_date`, `locale` | 실행 식별자, 원문 질의, 분석 기준일, 출력 언어 |
| 분류 | `classification` | 확정된 자산 코드·자산군·시장·섹터·의도·기간 |
| 계획 | `execution_plan`, `selected_dimensions`, `selected_factors`, `node_order` | 실행 대상 차원과 팩터 |
| 분석 | `macro_result`, `flow_result`, `industry_result`, `valuation_result` | 병렬 노드별 독립 결과 |
| 종합 | `synthesis_result` | 최종 관점, 전략, 시나리오, 선택 근거 |
| 평가 | `evaluation_result`, `evaluation_feedback`, `revision_count`, `max_synthesis_revisions` | 품질 점수와 재작성 제어 |
| 출력 | `user_facing_report`, `notion_report_page`, `report_run_summary`, `tags` | 사용자·저장·운영용 출력 |

State에 SQLAlchemy 객체나 DB 세션을 넣지 않는다. 체크포인트 직렬화를 위해 dict, list, 문자열, 숫자처럼 직렬화 가능한 값만 저장한다.

## 6. 계약 계층

### 6.1 YAML 계약

YAML은 운영자가 코드 수정 없이 분석 범위를 조정할 수 있게 한다.

- `data_specs.yaml`: 실제 저장 데이터의 의미와 제약을 정의한다.
- `factor_catalog.yaml`: 어떤 데이터를 어떤 transform으로 분석할지 정의한다.
- `asset_class_taxonomy.yaml`: 자산군별로 어떤 dimension이 유효한지 정의한다.
- `asset_taxonomy.yaml`: 이미 grounding된 자산을 빠르게 재사용한다.
- `node_specs.yaml`: 그래프 순서, 노드 책임, 평가 rubric, 보고서 섹션을 정의한다.

`factor_catalog.yaml`에서 `active`인 팩터만 계획에 포함한다. `draft`는 데이터 소스나 구현이 불충분한 것으로 보고 실행하지 않는다.

### 6.2 런타임 계약

`contracts.py`의 Pydantic 모델은 LLM과 코드 사이의 경계를 검증한다.

- `ClassificationResult`: 자산 분류 결과
- `SelectedFactor`: 계획에서 선택된 팩터
- `Evidence`: 값, 단위, 관측일, 기준일, 출처, transform
- `FactorFeature`: 팩터 신호와 근거 또는 누락 사유
- `DimensionResult`: 차원별 분석 결과
- `SynthesisResult`: 종합 판단과 전략
- `EvaluationResult`: 100점 평가 결과
- `ReportOutput`: 사용자 보고서 및 저장용 메타데이터

신호 값은 `positive`, `neutral`, `negative`, `mixed`, `unknown` 중 하나만 허용한다. LLM이 다른 표현이나 객체를 반환하면 정규화하거나 Pydantic 검증에서 차단한다.

## 7. 노드별 구현

### 7.1 classify_node

분류는 LLM 추출과 DB grounding을 분리한다.

1. `OpenAIAssetExtractor`가 질의에서 `asset_name`, `asset_class`, `horizon`, `query_intent`, `aliases`를 구조화 JSON으로 추출한다.
2. `AssetTaxonomyRegistry`가 이름, 코드, alias를 정규화해 `asset_taxonomy.yaml`을 조회한다.
3. 캐시가 있으면 검증된 코드와 메타데이터를 그대로 사용한다.
4. 캐시가 없으면 자산군 정책을 확인하고 종목 마스터에서 후보를 검색한다.
5. 후보를 선택해 `entity_code`, `market`, `sector`를 확정한다.
6. 검증된 인스턴스를 파일 락 아래 `asset_taxonomy.yaml`에 append한다.

현재 캐시 미스 grounding 구현은 국내 주식(`kr_equity`)을 대상으로 한다. 다른 자산군은 taxonomy에 사전 등록하거나 해당 마스터 resolver를 추가해야 한다.

지원 query intent는 다음과 같다.

- `buy_or_not`
- `long_term_outlook`
- `short_term_timing`
- `risk_check`
- `portfolio_allocation`
- `comparison`
- `general_outlook`

LLM 프롬프트에는 종목 코드를 생성하지 말라는 제약이 포함된다. 코드의 최종 권한은 종목 마스터에 있다.

### 7.2 plan_node

계획 노드는 새 팩터를 만들어내지 않는다.

1. 분류된 자산군의 `applicable_dimensions`를 읽는다.
2. `factor_catalog.yaml`에서 `status: active`인 팩터만 조회한다.
3. 팩터의 dimension과 적용 자산군을 대조한다.
4. `SelectedFactor` 목록을 차원별로 나눈다.
5. 실행 순서와 초기 revision 설정을 state에 기록한다.

따라서 팩터를 추가하려면 적어도 data spec, factor catalog, feature selector 세 계층이 일치해야 한다.

### 7.3 분석 노드 factory

네 분석 노드는 `make_analyzer(dimension, feature_engine)` 하나로 생성한다.

각 analyzer는 다음을 수행한다.

1. plan이 해당 dimension에 배정한 팩터만 선택한다.
2. 팩터마다 `FeatureEngine.compute_factor()`를 실행한다.
3. evidence가 없는 팩터는 종합 근거에서 제외하고 `missing_data`에 기록한다.
4. 팩터 신호와 강도로 dimension 신호 및 confidence를 계산한다.
5. dimension 전용 view와 위험 요약을 만든다.
6. 자신의 `{dimension}_result` 키만 반환한다.

분석 결과는 최소한 다음 구조를 가진다.

```json
{
  "dimension": "flow",
  "signal": "mixed",
  "confidence": 0.64,
  "summary": "...",
  "key_evidence": [],
  "risks": [],
  "missing_data": [],
  "factor_results": []
}
```

### 7.4 synthesize_node

종합 노드는 네 차원의 결과를 한 투자 논지로 조합한다.

1. 모든 dimension 결과의 evidence를 모은다.
2. 각 evidence에 `E1`, `E2` 같은 실행 내 식별자를 부여한다.
3. LLM에는 immutable evidence registry와 차원별 분석을 전달한다.
4. LLM은 registry에 존재하는 evidence ID만 선택할 수 있다.
5. 선택된 ID를 원본 `Evidence` 객체로 다시 매핑한다.
6. 최종 관점, 신뢰도, 투자기간, 전략, 상승·하락 시나리오, 위험, 모니터링 지표를 검증한다.

보고서는 한국어로 작성하도록 reasoning prompt에서 강제한다. 수치와 종목 코드를 새로 만들거나 evidence registry 밖의 근거를 인용할 수 없다.

### 7.5 evaluate_node와 재작성 루프

평가 노드는 다음 7개 항목을 합산해 100점으로 평가한다.

| 항목 | 최대 점수 |
|---|---:|
| 근거 커버리지 | 20 |
| 데이터 최신성 | 15 |
| 논리 일관성 | 20 |
| 리스크 인식 | 15 |
| 실행 가능성 | 15 |
| 과신 통제 | 10 |
| 사용자 적합성 | 5 |

통과 조건은 평가 점수 70점 이상이며 critical issue가 없는 것이다. LLM이 과도한 점수를 반환해도 실제 확보된 evidence와 factor 수에 따라 근거 커버리지 점수는 코드에서 제한된다.

재작성 상한은 `node_specs.yaml`의 `max_synthesis_revisions: 2`이다.

```text
최초 synthesize: revision_count = 0
1차 evaluate 실패 → 재작성 synthesize: revision_count = 1
2차 evaluate 실패 → 재작성 synthesize: revision_count = 2
3차 evaluate 후에는 결과와 관계없이 formatter로 진행
```

즉 evaluate 노드는 최대 3회 실행된다. 재작성 여부는 feedback 문자열의 존재가 아니라 이전 `evaluation_result`의 존재로 판단한다. 평가자가 빈 개선 제안을 반환해도 상한이 정상 적용되어 무한 루프가 발생하지 않는다.

라우팅 규칙은 다음과 같다.

```python
if evaluation.passed:
    return "report_formatter_node"
if revision_count >= max_synthesis_revisions:
    return "report_formatter_node"
return "synthesize_node"
```

상한 도달로 종료된 보고서는 평가 경고와 낮은 점수를 그대로 포함한다. 상한은 품질 통과를 위조하는 값이 아니라 종료 보장 장치다.

### 7.6 report_formatter_node

formatter는 검증된 종합 결과를 세 가지 형태로 나눈다.

- `user_facing_report`: Streamlit과 CLI에 표시할 Markdown
- `notion_report_page`: 추후 저장 연동을 위한 구조화 payload
- `report_run_summary`: 실행 이력 저장에 적합한 요약

현재 formatter는 Notion에 직접 쓰지 않는다. 저장 가능한 객체를 만들 뿐이며 외부 쓰기는 별도 adapter의 책임이다.

보고서의 기준 계약은 `node_specs.yaml`의 `recommended_report_structure`이다.

1. 질문 재정의
2. 결론 요약
3. 투자기간
4. 핵심 근거
5. 차원별 분석 요약
6. 상승 시나리오
7. 하락 시나리오
8. 투자전략
9. 리스크 및 모니터링 지표
10. 신뢰도와 한계

현재 backend `report_format_node`는 위 내용을 `결론`, `전략`, `시나리오`, `근거`, `주요 위험`, `품질 평가`로 압축해 출력한다. 반면 frontend mock/PDF 계층은 YAML의 섹션 목록을 직접 읽는다. 따라서 YAML 10개 섹션과 backend Markdown heading을 완전히 일치시키는 작업은 남아 있는 계약 정합성 개선 항목이다. 섹션을 변경할 때에는 YAML만 바꾸고 끝내지 말고 formatter 출력과 frontend 계약 테스트를 함께 확인해야 한다.

## 8. Feature Engine

### 8.1 처리 순서

```mermaid
sequenceDiagram
    participant A as Analyzer
    participant F as Feature Engine
    participant Y as YAML Contracts
    participant D as PostgreSQL
    participant S as Existing Sync Service

    A->>F: compute_factor(factor, asset, as_of)
    F->>Y: data spec와 selector 확인
    F->>D: start_date <= observation_date <= as_of 조회
    alt 충분한 이력
        F->>F: transform 계산
    else 국내 주식 데이터 부족
        F->>S: fetch-on-miss 1회
        S->>D: 기존 service.sync로 적재
        F->>D: 동일 as_of 조건으로 재조회
    end
    F-->>A: FactorFeature + Evidence 또는 missing_reason
```

### 8.2 Point-in-time 보장

모든 repository adapter는 `as_of_date` 이후의 관측값을 제외한다. `Evidence`에는 다음 두 날짜를 분리해 저장한다.

- `observation_date`: 데이터가 의미하는 시장 관측일
- `as_of_date`: 사용자가 요청한 분석 기준일

DB의 생성 시각이 분석 기준일보다 늦다는 이유만으로 과거 관측 데이터를 버리지는 않는다. 판단 기준은 데이터 계약의 관측일이다. 반대로 실행 시점 스냅샷만 존재하고 과거 관측일이 없는 데이터는 과거 `as_of` 분석에 사용할 수 없다.

국내 파생 스냅샷은 UTC 저장 시각을 Asia/Seoul 날짜로 변환하고, 날짜별 마지막 스냅샷을 사용한다. 활성 월물은 해당 관측일에 유효한 active contract 기록으로 해석한다.

### 8.3 Transform 인터페이스

transform은 factor catalog에 선언하고 feature engine이 동일한 방식으로 계산한다.

| method | 계산 방식 | 최소 데이터 수 |
|---|---|---:|
| `level` | 마지막 값 | 1 |
| `rolling_sum` | 최근 window개 합 | window 이상 |
| `z_score` | `(마지막 값 - window 평균) / 모표준편차` | window 이상 |
| `pct_change` | `(마지막 값 - 기준 값) / 기준 값 × 100` | window 이상 |
| `level_and_delta` | 마지막 값 - 기준 값 | window 이상 |
| `yoy_growth` | 365일 이전 값 대비 증감률 | 비교 가능한 2개 이상 |
| `spread` | repository에서 계산한 마지막 spread | 1 |

분산이 0인 z-score는 0으로 처리하고, 기준 값이 0인 증감률은 계산 불가로 처리한다. 계산 결과가 없거나 유한수가 아니면 팩터를 `unknown`으로 반환한다.

### 8.4 Factor selector

factor catalog가 분석의 의미를 정의한다면 `_selector()`는 그 팩터를 실제 repository 필드에 연결하는 adapter다. 예시는 다음과 같다.

| 팩터 | 실제 필드 또는 식별자 |
|---|---|
| `MACRO_FX_USDKRW` | `base_rate` |
| `RATE_US_10Y` | US / 10Y / `close` |
| `VOL_VKOSPI` | index `0503` / `close` |
| `FLOW_FOREIGN_SPOT` | investor `frgn` / `net_amount` |
| `PROGRAM_NET` | `net_amount` |
| `FUTURES_OI` | `open_interest` |
| `FUTURES_BASIS` | `basis` |
| `FUTURES_BASIS_DISPARITY` | `disparity` |
| `VAL_PER` | `per`, 낮을수록 긍정인 역방향 polarity |
| `SOX_INDEX` | macro series `NASDAQSOX` |

catalog에 active 팩터를 추가하고 selector를 구현하지 않으면 실행을 중단하지 않고 `feature adapter missing`을 해당 팩터의 누락 사유로 남긴다.

### 8.5 Fetch-on-miss

상시 배치 유니버스 밖의 국내 종목을 분석할 때 필요한 데이터가 부족하면 다음 bundle을 한 번 요청한다.

- 약 1년 일봉 시세
- 종목 투자자 수급
- 종목 프로그램 매매
- 연간 재무
- 분기 재무

기존 service의 sync 메서드를 그대로 사용하며 scraper 구현을 복제하지 않는다. `(ticker, as_of_date)`는 프로세스 안에서 한 번만 fetch한다. 각 도메인은 예외를 격리하므로 일부 sync가 실패해도 성공한 데이터로 분석을 계속한다.

KIS 토큰 발급 제한을 고려해 실행 전에 공용 throttle을 예약하며, 한 bundle 안에서는 동일 auth client를 공유한다.

주의할 점은 다음과 같다.

- 프로세스 메모리 캐시이므로 다른 프로세스에서는 DB 적재 여부로 재사용 여부가 결정된다.
- 외부 API가 과거 스냅샷을 제공하지 않으면 fetch-on-miss로 과거 시점 데이터를 복원할 수 없다.
- 적재 후에도 최소 이력 수를 충족하지 못하면 해당 팩터는 제외된다.

## 9. LLM 사용 경계

LLM은 세 역할에만 사용한다.

1. 질의에서 자산명·자산군·기간·의도를 추출한다.
2. 계산된 차원별 결과와 evidence를 종합한다.
3. 종합 보고서를 rubric으로 평가한다.

LLM이 하지 않는 일은 다음과 같다.

- 종목 코드 생성
- 원시 API 호출
- 임의 SQL 생성
- catalog에 없는 팩터 생성
- evidence에 없는 숫자 인용
- DB에 직접 쓰기

모든 응답은 JSON 형식과 Pydantic 모델로 검증한다. 현재 분석은 구조화 DB retrieval을 사용하며 벡터 검색 기반 RAG나 MCP를 사용하지 않는다.

## 10. PostgresSaver 체크포인트

전체 그래프는 LangGraph `PostgresSaver`를 사용할 수 있다. 체크포인트에는 각 노드가 끝난 state와 실행 thread 정보가 저장된다.

효과는 다음과 같다.

- 긴 실행의 중간 상태 추적
- 같은 `thread_id` 기반 상태 조회
- Streamlit task 이벤트 종료 후 최종 state 복원
- 향후 중단 지점 재개나 human-in-the-loop 확장 기반

체크포인트 테이블은 데이터베이스마다 최초 한 번 `saver.setup()`으로 생성해야 한다. 매번 초기화할 필요는 없으며, 일반 실행에서 반복 호출하지 않는다.

```powershell
python -m app.agent.run_report "코스피 한달 전망 분석해줘" `
  --as-of 2026-07-16 `
  --setup-checkpointer
```

그다음부터는 `--setup-checkpointer` 없이 실행한다. setup을 한 번도 하지 않은 DB에서는 checkpoint 테이블 부재 오류가 발생한다. setup은 기존 체크포인트를 지우는 reset이 아니라 필요한 테이블을 준비하는 작업이다.

## 11. 실행 인터페이스

### 11.1 환경 변수

최소한 다음 값이 필요하다.

```powershell
$env:DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/kanggaemi"
$env:OPENAI_API_KEY="..."
```

프로젝트가 사용하는 기존 DB 환경변수 명칭이 별도로 설정돼 있다면 `app/db/session.py`의 설정을 따른다. PostgresSaver에는 PostgreSQL 연결 문자열이 필요하다.

### 11.2 전체 보고서 CLI

`backend` 디렉터리에서 실행한다.

```powershell
cd C:\Users\ooroo\PycharmProjects\kanggaemi\backend
python -m app.agent.run_report "코스피 한달 전망 분석해줘" --as-of 2026-07-16
```

옵션:

- `--thread-id`: 체크포인트 thread 식별자를 직접 지정
- `--json`: 구조화 결과 출력
- `--setup-checkpointer`: 최초 1회 checkpoint 테이블 준비

### 11.3 수직 슬라이스 CLI

분류·계획·flow 분석만 점검할 때 사용한다.

```powershell
python -m app.agent.run_flow_slice "삼성전자 수급 분석해줘" `
  --as-of 2026-07-16
```

### 11.4 Streamlit

```powershell
cd C:\Users\ooroo\PycharmProjects\kanggaemi\backend
streamlit run frontend/app.py
```

`LangGraphAgentAdapter`는 `graph.stream(..., stream_mode="tasks")`를 소비해 다음 공통 이벤트로 바꾼다.

- `node_start`
- `node_complete`
- `final`
- `error`

프론트는 graph state나 node 함수에 직접 의존하지 않고 이 이벤트 계약만 소비한다. Mock adapter도 같은 계약을 사용하며 노드 목록과 보고서 구조를 `node_specs.yaml`에서 읽는다.

실제 adapter에서 백엔드 import가 지연되므로 Mock 모드는 LangGraph나 백엔드 의존성이 준비되지 않아도 동작한다. 실제 실행 오류는 mock 성공으로 숨기지 않고 `error` 이벤트로 표시한다.

## 12. 실패 및 데이터 부족 처리

| 상황 | 동작 |
|---|---|
| 캐시에 자산이 없음 | 종목 마스터 grounding 후 taxonomy에 append |
| 마스터 후보가 없음 | 분류 단계 실패, 코드 임의 생성 금지 |
| active data spec이 아님 | 해당 팩터 `unknown` 처리 |
| selector가 없음 | 해당 팩터 누락 사유 기록 |
| as_of 이력 부족 | fetch-on-miss 대상이면 1회 적재 후 재조회 |
| fetch-on-miss 일부 실패 | 성공한 도메인 데이터로 계속 진행 |
| transform 계산 불가 | 팩터 제외 및 missing reason 기록 |
| 일부 차원 근거 없음 | 차원 결과에 누락을 명시하고 confidence 하향 |
| LLM 평가 미통과 | 상한 내 synthesize 재실행 |
| 상한까지 평가 미통과 | 경고를 보존한 채 formatter로 종료 |
| checkpoint 테이블 없음 | 최초 1회 setup 필요 |

## 13. 확장 방법

### 13.1 새 팩터 추가

다음 순서로 작업한다.

1. `data_specs.yaml`에 소스 데이터 계약이 있는지 확인한다.
2. 없으면 data spec을 먼저 추가하고 실제 repository 조회가 가능한지 검증한다.
3. `factor_catalog.yaml`에 factor ID, dimension, data spec, transform, interpretation을 추가한다.
4. 데이터가 아직 없으면 `draft`, 계산 가능하면 `active`로 둔다.
5. `feature_engine._selector()`에 실제 필드 매핑을 추가한다.
6. `_read_points()`에 해당 data spec adapter가 없다면 repository 조회를 추가한다.
7. transform 최소 이력과 단위를 검증하는 테스트를 추가한다.

팩터 ID는 YAML, selector, 테스트에서 동일해야 한다.

### 13.2 새 자산군 추가

1. `asset_class_taxonomy.yaml`에 자산군과 region, dimension 정책을 정의한다.
2. 해당 자산군의 authoritative master repository를 준비한다.
3. `AssetResolver`에 캐시 미스 grounding 경로를 추가한다.
4. 자산별 data spec 치환이 필요하면 `_effective_data_spec()`을 확장한다.
5. factor applicability와 feature repository 조회를 테스트한다.

LLM 추출만 확장하고 master grounding 없이 자산 코드를 받는 구현은 허용하지 않는다.

### 13.3 새 분석 차원 추가

1. `node_specs.yaml`의 supported dimension과 노드 계약을 추가한다.
2. factor catalog에 해당 dimension 팩터를 정의한다.
3. `InvestmentAgentState`에 독립 결과 키를 추가한다.
4. `make_analyzer()` 지원 목록과 전용 view를 확장한다.
5. `graph.py`의 병렬 analyzer 목록과 join을 갱신한다.
6. synthesize prompt 및 evaluation coverage에 새 차원을 반영한다.
7. frontend가 YAML 실행 순서를 정상 해석하는지 검증한다.

### 13.4 보고서 형식 변경

섹션 제목과 순서는 `node_specs.yaml`의 `recommended_report_structure`를 먼저 변경한다. Streamlit의 mock/PDF 경로는 이 값을 읽어 렌더링하므로 프론트에 제목을 중복 하드코딩하지 않는다. 실제 에이전트가 반환하는 Markdown은 backend formatter에서 생성되므로, formatter가 새 구조의 내용을 채우는지도 함께 수정하고 테스트한다.

## 14. 테스트

에이전트 단위 및 그래프 테스트:

```powershell
cd C:\Users\ooroo\PycharmProjects\kanggaemi\backend
pytest tests/test_agent_flow_slice.py tests/test_agent_report.py -q
```

프론트 이벤트 계약 테스트:

```powershell
pytest frontend/tests/test_frontend_contract.py -q
```

중요 회귀 테스트 범위는 다음과 같다.

- 캐시 hit/miss 및 종목 마스터 grounding
- active 팩터만 선택되는지
- as_of 이후 데이터가 제외되는지
- evidence 없는 팩터가 누락 처리되는지
- 네 analyzer 결과가 독립 state 키에 기록되는지
- 낮은 평가 점수에서 재작성되는지
- 평가 feedback이 비어 있어도 revision 상한이 적용되는지
- 최종 보고서가 한국어 섹션 구조를 지키는지
- 실제·mock adapter가 동일 NodeEvent 계약을 지키는지

## 15. 운영 점검 목록

실행 전:

- PostgreSQL 연결과 마이그레이션이 정상인지 확인한다.
- 배치가 분석 기준일까지 필요한 데이터를 적재했는지 확인한다.
- OpenAI API 키가 환경변수 또는 Streamlit secrets에 있는지 확인한다.
- checkpoint 테이블을 해당 DB에서 최초 1회 준비했는지 확인한다.
- 요청 `as_of_date`가 DB의 관측일 범위 안인지 확인한다.

실행 후:

- `missing_data`가 많은 차원을 확인한다.
- evidence의 `observation_date`가 `as_of_date` 이후가 아닌지 확인한다.
- 평가 점수와 critical issue, revision count를 확인한다.
- 상한 종료 보고서는 경고와 신뢰도 한계를 사용자에게 노출한다.
- fetch-on-miss 오류가 반복되면 API 권한, 호출 가능 시간, 토큰 throttle을 점검한다.

## 16. 현재 한계와 후속 개선

- 캐시 미스 master grounding은 현재 국내 주식 중심이다.
- 이슈·뉴스 분석은 아직 별도 데이터 계약과 팩터가 없다.
- fetch-on-miss는 외부 API가 제공하지 않는 과거 스냅샷을 복원하지 못한다.
- 차원별 analyzer의 신호 집계는 결정론적 규칙이며, 향후 팩터 중요도와 자산군별 임계값 정교화가 필요하다.
- PostgresSaver는 상태를 저장하지만 현재 CLI는 자동 중단 재개 UI를 제공하지 않는다.
- `notion_report_page`는 payload만 만들며 실제 Notion 전송 adapter는 없다.
- 구조화 DB 조회를 사용하므로 비정형 리서치 문서가 필요해지면 별도 RAG 계약과 출처 검증 계층을 설계해야 한다.

이 한계들은 오류를 숨기지 않기 위한 의도적인 경계다. 데이터나 도구가 준비되지 않은 기능은 `draft` 또는 누락 사유로 표현하고, LLM이 그 빈자리를 추정으로 채우지 않도록 유지한다.
