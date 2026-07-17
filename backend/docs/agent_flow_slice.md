# Investment strategy agent: flow vertical slice

The original slice implements `classify_node -> plan_node -> flow_node -> simple_output_node`. The complete report graph documented below extends the same contracts with parallel macro, industry, and valuation analysis plus synthesis, evaluation, and formatting.

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
- `plan_node` selects only `status=active` factors in applicable dimensions. Draft factors such as `SHORT_BALANCE` are excluded.
- The feature engine maps stock factors to the equity data specs, reads only rows whose observation date is at or before `as_of_date`, and applies the transform declared in `factor_catalog.yaml`.
- KOSPI futures-flow factors resolve the contract from the point-in-time domestic `KOSPI200` `active_contract` history and read `derivative_snapshot`. Each date uses its last KST snapshot. A missing contract or snapshot is reported in `missing_data` instead of aborting the graph.
- When a stock series is absent or shorter than the transform window, fetch-on-miss invokes the existing stock chart (~1 year), investor-flow, program-trade, and annual/quarter financial sync paths once. Analysis nodes never call a scraper directly.
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

## Complete report graph

The approved extension is available through `app.agent.run_report`:

```powershell
python -m app.agent.run_report "삼성전자 3개월 전망 분석해줘" `
  --as-of 2026-07-16 `
  --setup-checkpointer
```

Use `--setup-checkpointer` once per database (it is safe to repeat), and use
`--json` when the complete state/evidence/evaluation payload is needed.

```text
classify -> plan -> [macro | flow | industry | valuation]
         -> synthesize -> evaluate -> (synthesize, at most 2 revisions)
         -> report_formatter
```

- All analyzers are created by `make_analyzer` and write only their own state key.
- Only active catalog factors are planned. Both `data_spec_ids` and the existing
  singular financial `data_spec_id` contract are supported.
- The synthesis LLM selects evidence IDs from a registry; code maps them back to
  immutable evidence objects, preventing generated values or entity codes.
- All human-readable analysis, strategy, scenario, risk, evaluation, and report
  prose is required to be Korean. Internal contract enums and IDs remain unchanged,
  and display-time signal labels are translated to Korean.
- Evaluation follows the `node_specs.yaml` 100-point rubric. A score below 70
  or a critical issue requests a rewrite until the configured revision cap.
- The formatter returns `user_facing_report`, `notion_report_page`, and
  `report_run_summary`; it does not write to an external system.
