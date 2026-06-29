from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
NOTION_VERSION = "2022-06-28"
RICH_TEXT_CHUNK_SIZE = 2000


class NotionClientError(RuntimeError):
    """Raised when a Notion API request fails."""


class NotionClient:
    """
    Small reusable wrapper around the Notion REST API.

    Sync scripts should use this client for auth, database ID lookup,
    database queries, page creation, and page updates.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        notion_version: Optional[str] = None,
        database_ids_path: Optional[str] = None,
        request_timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        load_dotenv(ROOT_DIR / ".env")

        self.token = token or os.getenv("NOTION_TOKEN")
        if not self.token:
            raise ValueError("NOTION_TOKEN is missing. Add it to your .env file.")

        self.notion_version = notion_version or os.getenv(
            "NOTION_VERSION",
            NOTION_VERSION,
        )
        self.base_url = "https://api.notion.com/v1"
        self.request_timeout = request_timeout
        self.max_retries = max_retries

        ids_path = database_ids_path or os.getenv(
            "NOTION_DATABASE_IDS_PATH",
            "notion/database_ids.json",
        )
        self.database_ids_path = self._resolve_path(ids_path)
        self.database_ids = self._load_database_ids(self.database_ids_path)

    @staticmethod
    def _resolve_path(value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return ROOT_DIR / path

    def _load_database_ids(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(
                f"Database ID file not found: {path}. "
                "Set NOTION_DATABASE_IDS_PATH or create notion/database_ids.json."
            )

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }

    def get_database_id(self, key: str) -> str:
        item = self.database_ids.get(key)
        if not item:
            raise KeyError(f"Database key not found in database IDs file: {key}")

        database_id = item.get("database_id")
        if not database_id:
            raise KeyError(f"database_id is missing for key: {key}")

        return database_id

    def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.request_timeout,
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    time.sleep(retry_after)
                    continue

                if not response.ok:
                    raise NotionClientError(
                        f"Notion API error {response.status_code}: {response.text}"
                    )

                if response.text:
                    return response.json()

                return {}

            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1.5 * attempt)
                else:
                    break

        raise NotionClientError(f"Notion API request failed: {last_error}")

    def retrieve_database(self, database_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/databases/{database_id}")

    def query_database(
        self,
        database_id: str,
        filter_payload: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        start_cursor: Optional[str] = None

        while True:
            payload: Dict[str, Any] = {"page_size": page_size}

            if filter_payload:
                payload["filter"] = filter_payload
            if sorts:
                payload["sorts"] = sorts
            if start_cursor:
                payload["start_cursor"] = start_cursor

            data = self._request("POST", f"/databases/{database_id}/query", payload)
            results.extend(data.get("results", []))

            if not data.get("has_more"):
                break

            start_cursor = data.get("next_cursor")

        return results

    def find_page_by_title(
        self,
        database_id: str,
        title_property: str,
        title_value: str,
    ) -> Optional[Dict[str, Any]]:
        filter_payload = {
            "property": title_property,
            "title": {"equals": title_value},
        }
        pages = self.query_database(
            database_id=database_id,
            filter_payload=filter_payload,
            page_size=10,
        )
        return pages[0] if pages else None

    def create_page(
        self,
        database_id: str,
        properties: Dict[str, Any],
        children: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        if children:
            payload["children"] = children
        return self._request("POST", "/pages", payload)

    def update_page(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def append_blocks(self, block_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._request("PATCH", f"/blocks/{block_id}/children", {"children": children})

    def list_block_children(self, block_id: str, page_size: int = 100) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        start_cursor: Optional[str] = None

        while True:
            endpoint = f"/blocks/{block_id}/children?page_size={page_size}"
            if start_cursor:
                endpoint += f"&start_cursor={start_cursor}"

            data = self._request("GET", endpoint)
            results.extend(data.get("results", []))

            if not data.get("has_more"):
                break

            start_cursor = data.get("next_cursor")

        return results

    def archive_block(self, block_id: str) -> Dict[str, Any]:
        return self._request("PATCH", f"/blocks/{block_id}", {"archived": True})

    def replace_page_children(
        self,
        page_id: str,
        new_children: List[Dict[str, Any]],
        preserve_manual_notes_heading: str = "Manual Notes",
    ) -> None:
        existing_blocks = self.list_block_children(page_id)

        for block in existing_blocks:
            block_id = block["id"]
            block_type = block.get("type")

            plain_text = ""
            if block_type and block_type in block:
                rich_text_items = block[block_type].get("rich_text", [])
                plain_text = "".join(t.get("plain_text", "") for t in rich_text_items)

            if preserve_manual_notes_heading in plain_text:
                break

            self.archive_block(block_id)

        if new_children:
            self.append_blocks(page_id, new_children)


def normalize_property_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def find_database_property(
    schema: Dict[str, Any],
    aliases: Sequence[str] | str,
    allowed_types: Optional[set[str]] = None,
) -> Optional[str]:
    if isinstance(aliases, str):
        aliases = [aliases]

    normalized_aliases = {normalize_property_name(alias) for alias in aliases}
    for property_name, metadata in schema.items():
        if normalize_property_name(property_name) not in normalized_aliases:
            continue
        if allowed_types is None or metadata["type"] in allowed_types:
            return property_name

    return None


def title_property_name(schema: Dict[str, Any]) -> str:
    for property_name, metadata in schema.items():
        if metadata["type"] == "title":
            return property_name
    raise RuntimeError("Notion database must have a title property.")


def to_plain_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def rich_text(text: Any) -> List[Dict[str, Any]]:
    content = to_plain_value(text)
    return [
        {"type": "text", "text": {"content": content[index : index + RICH_TEXT_CHUNK_SIZE]}}
        for index in range(0, len(content), RICH_TEXT_CHUNK_SIZE)
    ]


def title(text: Any) -> Dict[str, Any]:
    content = to_plain_value(text) or "Untitled"
    return {"title": rich_text(content[:RICH_TEXT_CHUNK_SIZE])}


def text_property(text: Any) -> Dict[str, Any]:
    return {"rich_text": rich_text(text)}


def select(name: Optional[str]) -> Dict[str, Any]:
    return {"select": {"name": str(name)} if name else None}


def multi_select(values: Optional[Iterable[Any]]) -> Dict[str, Any]:
    values = values or []
    return {
        "multi_select": [
            {"name": str(value)}
            for value in values
            if value is not None and str(value).strip()
        ]
    }


def checkbox(value: Optional[bool]) -> Dict[str, Any]:
    return {"checkbox": bool(value)}


def number(value: Optional[float]) -> Dict[str, Any]:
    return {"number": value}


def date_property(value: Optional[str]) -> Dict[str, Any]:
    return {"date": {"start": value} if value else None}


def property_payload(property_type: str, value: Any) -> Optional[Dict[str, Any]]:
    if property_type == "title":
        return title(value)
    if property_type == "rich_text":
        return text_property(value)
    if property_type == "select":
        return select(to_plain_value(value) if value is not None else None)
    if property_type == "multi_select":
        values = value if isinstance(value, list) else ([] if value is None else [value])
        return multi_select(values)
    if property_type == "number":
        return number(value if isinstance(value, (int, float)) else None)
    if property_type == "checkbox":
        return checkbox(value)
    if property_type == "url":
        return {"url": to_plain_value(value) or None}
    if property_type == "email":
        return {"email": to_plain_value(value) or None}
    if property_type == "phone_number":
        return {"phone_number": to_plain_value(value) or None}
    if property_type == "date":
        return date_property(to_plain_value(value))
    return None


def extract_property_value(page_property: Dict[str, Any]) -> Any:
    property_type = page_property.get("type")
    value = page_property.get(property_type)

    if property_type in {"title", "rich_text"}:
        return "".join(part.get("plain_text", "") for part in value)
    if property_type == "select":
        return value.get("name") if value else ""
    if property_type == "multi_select":
        return [item.get("name", "") for item in value]
    if property_type == "date":
        return value.get("start") if value else ""

    return value


def property_values_equal(expected_payload: Dict[str, Any], page_property: Dict[str, Any]) -> bool:
    expected_type = next(iter(expected_payload))
    property_type = page_property.get("type")
    if property_type != expected_type:
        return False

    expected_value = expected_payload.get(property_type)
    current_value = extract_property_value(page_property)

    if property_type in {"title", "rich_text"}:
        expected_text = "".join(
            part.get("text", {}).get("content", "") for part in expected_value
        )
        return expected_text == current_value
    if property_type == "select":
        expected_name = expected_value.get("name") if expected_value else ""
        return expected_name == current_value
    if property_type == "multi_select":
        expected_names = [item.get("name", "") for item in expected_value]
        return expected_names == current_value
    if property_type == "date":
        expected_start = expected_value.get("start") if expected_value else ""
        return expected_start == current_value

    return expected_value == current_value


def changed_properties(
    desired: Dict[str, Any],
    current_page: Dict[str, Any],
) -> Dict[str, Any]:
    changed: Dict[str, Any] = {}
    current_properties = current_page.get("properties", {})

    for property_name, payload in desired.items():
        current_property = current_properties.get(property_name)
        if current_property is None or not property_values_equal(payload, current_property):
            changed[property_name] = payload

    return changed


def paragraph(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text(text)},
    }


def heading_2(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": rich_text(text)},
    }


def code_block(code: str, language: str = "yaml") -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": rich_text(code),
            "language": language,
        },
    }
