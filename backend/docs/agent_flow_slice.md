# Investment strategy agent: flow vertical slice

This slice implements `classify_node -> plan_node -> flow_node -> simple_output_node` with LangGraph. It establishes the contracts for the later parallel macro, industry and valuation analyzers without implementing those nodes yet.

## One-time setup

Install the added LangGraph/Postgres dependencies and load the KIS stock masters used for grounding:

```bash
pip install -r requirements.txt
python -m scripts.load_domestic_stock_master --download --market both
```

The loader creates `domestic_stock_master`. It follows the official KOSPI 227-character and KOSDAQ 221-character fixed-width tails (the attached examples' 228/222 slices include the newline). It stores the official ticker/name/market and large, medium and small sector codes. The source does not contain sector display names, so classification uses the grounded large-sector code rather than inventing a label.

The first agent execution must initialize the official PostgresSaver tables:

```bash
python -m app.agent.run_flow_slice "삼성전자 수급 전망을 분석해줘" --as-of 2026-07-17 --setup-checkpointer
```

Later executions omit the setup flag:

```bash
python -m app.agent.run_flow_slice "삼성전자 수급 전망을 분석해줘" --as-of 2026-07-17
python -m app.agent.run_flow_slice "SK하이닉스 단기 매수 타이밍은?" --as-of 2026-07-17 --json
```

`OPENAI_API_KEY`, `LLM_MODEL` and a PostgreSQL `DATABASE_URL` use the existing application settings. Each run supplies a LangGraph `thread_id` (generated unless `--thread-id` is passed), and PostgresSaver checkpoints every node transition.

## Contract behavior

- The LLM extracts only `asset_name`, asset-class/horizon hints and `query_intent`; it never supplies an entity code.
- Cache hits use `asset_taxonomy.yaml`. Cache misses ground the official code, name, market and sector code in `domestic_stock_master`, then append the verified instance to the taxonomy under a process-safe lock.
- `plan_node` selects only `status=active` flow factors applicable to the classified asset class. Draft factors such as `SHORT_BALANCE` are excluded.
- The feature engine maps stock factors to the equity data specs, reads only rows whose observation date is at or before `as_of_date`, and applies the transform declared in `factor_catalog.yaml`.
- When a stock series is absent or shorter than the transform window, fetch-on-miss invokes the existing stock chart (~1 year), investor-flow and program-trade sync paths once. Analysis nodes never call a scraper directly.
- Each available factor produces the `node_specs.yaml.evidence_contract`. Missing factors are excluded from evidence and listed in `missing_data`.

Example evidence:

```json
{
  "data_spec_id": "DS_KR_EQUITY_INVESTOR_FLOW",
  "source": "kis",
  "entity_code": "005930",
  "field": "net_amount",
  "value": 12345.0,
  "unit": "KRW_million",
  "observation_date": "2026-07-17",
  "as_of_date": "2026-07-17",
  "transform": {"method": "rolling_sum", "window": "5D"},
  "is_estimated": true,
  "caveats": []
}
```
