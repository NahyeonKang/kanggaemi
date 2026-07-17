from __future__ import annotations

import argparse
import json
import uuid

from langgraph.checkpoint.postgres import PostgresSaver

from app.agent.assets import AssetResolver
from app.agent.graph import build_investment_report_graph
from app.agent.llm import OpenAIAssetExtractor
from app.agent.reasoning import OpenAIReportReasoner
from app.core.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete investment strategy report LangGraph."
    )
    parser.add_argument("query")
    parser.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--setup-checkpointer", action="store_true")
    args = parser.parse_args()
    run_id = args.thread_id or str(uuid.uuid4())
    resolver = AssetResolver(OpenAIAssetExtractor())
    reasoner = OpenAIReportReasoner()
    with PostgresSaver.from_conn_string(_postgres_uri(settings.DATABASE_URL)) as saver:
        if args.setup_checkpointer:
            saver.setup()
        graph = build_investment_report_graph(
            resolver, reasoner, checkpointer=saver,
        )
        result = graph.invoke(
            {
                "run_id": run_id, "user_query": args.query,
                "as_of_date": args.as_of, "locale": "ko-KR",
            },
            {"configurable": {"thread_id": run_id}},
        )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(result["user_facing_report"])
    return 0


def _postgres_uri(value: str) -> str:
    if not value.startswith("postgresql"):
        raise ValueError("PostgresSaver requires a PostgreSQL DATABASE_URL")
    return value.replace("postgresql+psycopg2://", "postgresql://", 1)


if __name__ == "__main__":
    raise SystemExit(main())
