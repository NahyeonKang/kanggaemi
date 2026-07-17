from __future__ import annotations

import json
from typing import Protocol

from openai import OpenAI

from app.agent.catalog import load_yaml
from app.agent.contracts import AssetExtraction
from app.core.config import settings


class AssetExtractor(Protocol):
    def extract(self, user_query: str) -> AssetExtraction: ...


class OpenAIAssetExtractor:
    def __init__(self, client: OpenAI | None = None, model: str | None = None) -> None:
        if not settings.OPENAI_API_KEY and client is None:
            raise RuntimeError("OPENAI_API_KEY is required for classify_node")
        self.client = client or OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model or settings.LLM_MODEL

    def extract(self, user_query: str) -> AssetExtraction:
        classes = [item["asset_class"] for item in load_yaml("asset_class_taxonomy.yaml")["classes"]]
        specs = load_yaml("node_specs.yaml")
        horizons = specs["conventions"]["supported_horizons"]
        intents = _query_intents(specs)
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract only the named investment asset and classification hints. "
                        "Never invent an entity/ticker code; grounding happens in a master. "
                        f"asset_class must be one of {classes}; horizon one of {horizons}; "
                        f"query_intent one of {intents}. Return JSON with asset_name, "
                        "asset_class, horizon, query_intent, aliases, confidence."
                    ),
                },
                {"role": "user", "content": user_query},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty asset classification")
        return AssetExtraction.model_validate(json.loads(content))


def _query_intents(specs: dict) -> list[str]:
    node = next(item for item in specs["nodes"] if item["node_id"] == "classify_node")
    return list(node["output_schema"]["fields"]["query_intent"]["allowed_values"])
