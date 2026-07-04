from __future__ import annotations

import argparse
import copy
import os
import re
import subprocess
import sys
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

if __package__:
    from .client import (
        NotionClient,
        changed_properties,
        code_block,
        extract_property_value,
        find_database_property,
        heading_2,
        paragraph,
        property_payload,
        property_values_equal,
        rich_text,
        title,
        title_property_name,
        to_plain_value,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from client import (  # type: ignore[no-redef]
        NotionClient,
        changed_properties,
        code_block,
        extract_property_value,
        find_database_property,
        heading_2,
        paragraph,
        property_payload,
        property_values_equal,
        rich_text,
        title,
        title_property_name,
        to_plain_value,
    )


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_KEY = "code_change_log"
CODE_CHUNK_SIZE = 1800
APPEND_BATCH_SIZE = 80
SUMMARY_LIMIT = 1800
MANUAL_NOTES_HEADING = "Manual Notes"
RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"

PROPERTY_MAPPING: dict[str, tuple[str, str, list[str]]] = {
    "commit_sha": ("title", ["Commit SHA", "commit_sha", "commit sha", "commitsha"]),
    "short_sha": ("rich_text", ["Short SHA", "short_sha", "short sha", "shortsha"]),
    "date": ("date", ["Date", "date"]),
    "author": ("rich_text", ["Author", "author"]),
    "branch": ("rich_text", ["Branch", "branch"]),
    "change_type": ("select", ["Change Type", "change_type", "change type", "changetype"]),
    "area": ("multi_select", ["Area", "area"]),
    "summary": ("rich_text", ["Summary", "summary"]),
    "status": ("select", ["Status", "status"]),
}
OPTIONAL_PROPERTY_MAPPING: dict[str, tuple[str, str, list[str]]] = {
    "github_url": ("url", ["GitHub URL", "github_url", "github url", "githuburl"]),
    "files_changed": ("rich_text", ["Files Changed", "files_changed", "files changed", "fileschanged"]),
}

AREA_RULES = [
    ("Config YAML", lambda path: path.startswith("core/") or "/core/" in path),
    ("Notion Sync", lambda path: path.startswith("notion/")),
    ("Agent Node", lambda path: path.startswith("agent/") or "/agent/" in path),
    (
        "Data API",
        lambda path: any(
            path.startswith(prefix) or f"/{prefix}" in path
            for prefix in (
                "collectors/",
                "clients/",
                "scrapers/",
                "services/",
                "api/",
                "db/",
                "models/",
                "repositories/",
                "schemas/",
            )
        ),
    ),
    ("Testing", lambda path: path.startswith("tests/") or "/tests/" in path),
    ("Docs", lambda path: path.startswith("docs/") or "/docs/" in path),
    ("Infra", lambda path: path.startswith(".github/workflows/")),
]


@dataclass
class CommitInfo:
    commit_sha: str
    short_sha: str
    author_name: str
    author_email: str
    date: str
    subject: str
    body: str
    branch: str
    files_changed: str
    diff_stat: str
    changed_paths: list[str]
    github_url: str | None

    @property
    def author(self) -> str:
        return f"{self.author_name} <{self.author_email}>"


@dataclass
class SyncCounts:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"warning: {message}", file=sys.stderr)


def run_git(args: list[str], *, allow_fail: bool = False) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT_DIR,
            check=not allow_fail,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git executable was not found.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"git command failed: git {' '.join(args)}: {message}") from exc

    if allow_fail and result.returncode != 0:
        return ""
    return result.stdout.strip()


def ensure_git_repo() -> None:
    output = run_git(["rev-parse", "--is-inside-work-tree"], allow_fail=True)
    if output.lower() != "true":
        raise RuntimeError(f"Not a git repository: {ROOT_DIR}")


def current_branch() -> str:
    ref_name = os.getenv("GITHUB_REF_NAME")
    if ref_name:
        return ref_name
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], allow_fail=True)
    return branch if branch and branch != "HEAD" else "detached"


def github_base_url() -> str | None:
    remote = run_git(["config", "--get", "remote.origin.url"], allow_fail=True)
    if not remote:
        return None

    remote = remote.strip()
    if remote.startswith("git@github.com:"):
        repo = remote.removeprefix("git@github.com:")
        return f"https://github.com/{repo.removesuffix('.git')}"
    if remote.startswith("ssh://git@github.com/"):
        repo = remote.removeprefix("ssh://git@github.com/")
        return f"https://github.com/{repo.removesuffix('.git')}"
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    return None


def commit_github_url(base_url: str | None, commit_sha: str) -> str | None:
    if not base_url:
        return None
    return f"{base_url}/commit/{commit_sha}"


def normalize_git_date_for_notion(value: str) -> str:
    """Convert git date output into a Notion-compatible ISO 8601 string."""
    text = value.strip()
    if not text:
        return text

    # Git --date=iso-strict already emits ISO 8601. Older/manual values may use
    # "YYYY-MM-DD HH:MM:SS +0900", which Notion rejects without T and colonized TZ.
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z")
        return parsed.isoformat()
    except ValueError:
        pass

    return text.replace(" ", "T", 1)


def infer_change_type(subject: str) -> str:
    match = re.match(r"^(feat|fix|refactor|docs|test|chore|remove|delete)(\([^)]+\))?:", subject, re.IGNORECASE)
    if not match:
        return "Update"
    kind = match.group(1).lower()
    return {
        "feat": "Add",
        "fix": "Fix",
        "refactor": "Refactor",
        "docs": "Docs",
        "test": "Test",
        "chore": "Config",
        "remove": "Remove",
        "delete": "Remove",
    }[kind]


def infer_areas(paths: list[str]) -> list[str]:
    areas: list[str] = []
    normalized_paths = [path.replace("\\", "/") for path in paths]
    for area, predicate in AREA_RULES:
        if any(predicate(path) for path in normalized_paths):
            areas.append(area)
    if not areas:
        areas.append("General")
    return areas


def truncate_text(text: str, limit: int = SUMMARY_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def parse_name_status(output: str) -> tuple[str, list[str]]:
    lines = [line for line in output.splitlines() if line.strip()]
    paths: list[str] = []
    formatted: list[str] = []
    for line in lines:
        parts = line.split("\t")
        status = parts[0]
        if len(parts) >= 3 and status.startswith("R"):
            path = parts[2]
            formatted.append(f"{status} {parts[1]} -> {parts[2]}")
        elif len(parts) >= 2:
            path = parts[1]
            formatted.append(f"{status} {path}")
        else:
            continue
        paths.append(path.replace("\\", "/"))
    return "\n".join(formatted), paths


def collect_commits(max_count: int, since: str | None) -> list[CommitInfo]:
    ensure_git_repo()
    branch = current_branch()
    base_url = github_base_url()
    log_args = [
        "log",
        f"--pretty=format:%H{FIELD_SEPARATOR}%h{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae{FIELD_SEPARATOR}%ad{FIELD_SEPARATOR}%s{FIELD_SEPARATOR}%B{RECORD_SEPARATOR}",
        "--date=iso-strict",
        f"--max-count={max_count}",
    ]
    if since:
        log_args.append(f"--since={since}")

    raw_log = run_git(log_args)
    commits: list[CommitInfo] = []
    for record in raw_log.split(RECORD_SEPARATOR):
        record = record.strip("\n")
        if not record:
            continue
        fields = record.split(FIELD_SEPARATOR, 6)
        if len(fields) < 7:
            continue
        commit_sha, short_sha, author_name, author_email, commit_date, subject, body = fields
        name_status = run_git(["show", "--name-status", "--format=", commit_sha])
        diff_stat = run_git(["show", "--numstat", "--format=", commit_sha])
        files_changed, changed_paths = parse_name_status(name_status)
        commits.append(
            CommitInfo(
                commit_sha=commit_sha,
                short_sha=short_sha,
                author_name=author_name,
                author_email=author_email,
                date=normalize_git_date_for_notion(commit_date),
                subject=subject,
                body=body.strip(),
                branch=branch,
                files_changed=files_changed,
                diff_stat=diff_stat,
                changed_paths=changed_paths,
                github_url=commit_github_url(base_url, commit_sha),
            )
        )
    return commits


def schema_property(
    available_properties: dict[str, Any],
    notion_name: str,
    expected_type: str,
    aliases: list[str],
    warnings: list[str],
) -> str | None:
    property_name = find_database_property(available_properties, aliases)
    if not property_name:
        warnings.append(f"Missing Notion property '{notion_name}'; skipped.")
        return None
    actual_type = available_properties[property_name]["type"]
    if actual_type != expected_type:
        warnings.append(
            f"Notion property '{property_name}' has type '{actual_type}', expected '{expected_type}'; skipped."
        )
        return None
    return property_name


def build_properties(commit: CommitInfo, available_properties: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "commit_sha": commit.commit_sha,
        "short_sha": commit.short_sha,
        "date": commit.date,
        "author": commit.author,
        "branch": commit.branch,
        "change_type": infer_change_type(commit.subject),
        "area": infer_areas(commit.changed_paths),
        "summary": commit.subject,
        "status": "Applied",
        "github_url": commit.github_url,
        "files_changed": truncate_text(commit.files_changed),
    }
    properties: dict[str, Any] = {}
    for key, (expected_type, aliases) in PROPERTY_MAPPING.items():
        property_name = schema_property(available_properties, aliases[0], expected_type, aliases, warnings)
        if not property_name:
            continue
        payload = property_payload(expected_type, values[key])
        if payload is not None:
            properties[property_name] = payload

    for key, (expected_type, aliases) in OPTIONAL_PROPERTY_MAPPING.items():
        property_name = find_database_property(available_properties, aliases, allowed_types={expected_type})
        if property_name and values.get(key):
            payload = property_payload(expected_type, values[key])
            if payload is not None:
                properties[property_name] = payload

    title_property = title_property_name(available_properties)
    if title_property not in properties:
        properties[title_property] = title(commit.commit_sha)
    return properties


def yaml_dump(value: Any) -> str:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()


def yaml_code_blocks(value: Any, language: str = "yaml", chunk_size: int = CODE_CHUNK_SIZE) -> list[dict[str, Any]]:
    dumped = yaml_dump(value)
    return [
        code_block(dumped[index : index + chunk_size], language)
        for index in range(0, len(dumped), chunk_size)
    ] or [code_block("", language)]


def append_text_section(children: list[dict[str, Any]], heading: str, text: str | None) -> None:
    children.append(heading_2(heading))
    children.append(paragraph(text or ""))


def raw_metadata(commit: CommitInfo) -> dict[str, Any]:
    return {
        "commit_sha": commit.commit_sha,
        "short_sha": commit.short_sha,
        "date": commit.date,
        "author_name": commit.author_name,
        "author_email": commit.author_email,
        "branch": commit.branch,
        "subject": commit.subject,
        "body": commit.body,
        "changed_paths": commit.changed_paths,
        "github_url": commit.github_url,
    }


def build_page_children(commit: CommitInfo) -> list[dict[str, Any]]:
    inferred = {
        "change_type": infer_change_type(commit.subject),
        "areas": infer_areas(commit.changed_paths),
        "status": "Applied",
    }
    children: list[dict[str, Any]] = []
    append_text_section(children, "Commit Summary", commit.body or commit.subject)
    append_text_section(children, "GitHub URL", commit.github_url or "")
    append_text_section(children, "Files Changed", commit.files_changed)
    append_text_section(children, "Diff Stat", commit.diff_stat)
    children.append(heading_2("Inferred Metadata"))
    children.extend(yaml_code_blocks(inferred))
    children.append(heading_2("Raw Git Metadata"))
    children.extend(yaml_code_blocks(raw_metadata(commit)))
    children.append(heading_2(MANUAL_NOTES_HEADING))
    children.append(paragraph(""))
    return children


def strip_null_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_null_values(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [strip_null_values(item) for item in value]
    return value


def clone_appendable_block(block: dict[str, Any]) -> dict[str, Any] | None:
    block_type = block.get("type")
    if not block_type or block_type not in block:
        return None
    payload = copy.deepcopy(block[block_type])
    for key in ("is_toggleable", "children"):
        payload.pop(key, None)
    payload = strip_null_values(payload)
    return {"object": "block", "type": block_type, block_type: payload}


def block_plain_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not block_type or block_type not in block:
        return ""
    rich_text_items = block[block_type].get("rich_text", [])
    return "".join(item.get("plain_text", "") for item in rich_text_items)


def preserved_manual_blocks(existing_blocks: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    manual_start: int | None = None
    for index, block in enumerate(existing_blocks):
        if MANUAL_NOTES_HEADING in block_plain_text(block):
            manual_start = index
            break
    if manual_start is None:
        return []
    preserved: list[dict[str, Any]] = []
    for block in existing_blocks[manual_start:]:
        cloned = clone_appendable_block(block)
        if cloned:
            preserved.append(cloned)
        else:
            warnings.append("Skipped preserving one unsupported Manual Notes block type.")
    return preserved


def append_blocks_in_batches(client: NotionClient, page_id: str, children: list[dict[str, Any]]) -> None:
    for index in range(0, len(children), APPEND_BATCH_SIZE):
        client.append_blocks(page_id, children[index : index + APPEND_BATCH_SIZE])


def replace_page_children_preserving_manual_notes(
    client: NotionClient,
    page_id: str,
    generated_children: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    existing_blocks = client.list_block_children(page_id)
    manual_blocks = preserved_manual_blocks(existing_blocks, warnings)
    if manual_blocks:
        generated_children = generated_children[:-2] + manual_blocks
    append_blocks_in_batches(client, page_id, generated_children)
    for block in existing_blocks:
        client.archive_block(block["id"])


def page_commit_sha(page: dict[str, Any], commit_sha_property: str) -> str:
    page_property = page.get("properties", {}).get(commit_sha_property)
    if not page_property:
        return ""
    value = extract_property_value(page_property)
    return value if isinstance(value, str) else to_plain_value(value)


def print_counts(counts: SyncCounts) -> None:
    print("Code Change Log sync completed.")
    print(f"Created: {counts.created}")
    print(f"Updated: {counts.updated}")
    print(f"Skipped: {counts.skipped}")
    print(f"Warnings: {counts.warning_count}")
    if counts.warnings:
        print("\nWarnings:")
        for warning in counts.warnings:
            print(f"- {warning}")


def sync_git_change_log(*, max_count: int, since: str | None, database_key: str, dry_run: bool) -> SyncCounts:
    counts = SyncCounts()
    commits = collect_commits(max_count=max_count, since=since)
    client = NotionClient()
    database_id = client.get_database_id(database_key)
    database = client.retrieve_database(database_id)
    available_properties = database["properties"]

    property_warnings: list[str] = []
    commit_sha_property = schema_property(
        available_properties,
        "Commit SHA",
        "title",
        PROPERTY_MAPPING["commit_sha"][1],
        property_warnings,
    )
    if not commit_sha_property:
        commit_sha_property = title_property_name(available_properties)
        property_warnings.append(f"Using title property '{commit_sha_property}' as Commit SHA fallback.")
    for warning in dict.fromkeys(property_warnings):
        counts.warn(warning)

    existing_pages = client.query_database(database_id)
    pages_by_commit_sha = {
        commit_sha: page
        for page in existing_pages
        if (commit_sha := page_commit_sha(page, commit_sha_property))
    }

    for commit in commits:
        item_warnings: list[str] = []
        properties = build_properties(commit, available_properties, item_warnings)
        for warning in dict.fromkeys(item_warnings):
            if warning not in counts.warnings:
                counts.warn(warning)

        children = build_page_children(commit)
        existing_page = pages_by_commit_sha.get(commit.commit_sha)
        try:
            if not existing_page:
                counts.created += 1
                if dry_run:
                    print(f"DRY-RUN create {commit.short_sha} {commit.subject}")
                else:
                    created_page = client.create_page(database_id, properties, children=children[:APPEND_BATCH_SIZE])
                    if len(children) > APPEND_BATCH_SIZE:
                        append_blocks_in_batches(client, created_page["id"], children[APPEND_BATCH_SIZE:])
                continue

            changed = changed_properties(properties, existing_page)
            counts.updated += 1
            if dry_run:
                print(f"DRY-RUN update {commit.short_sha} {commit.subject}")
                continue

            if changed:
                client.update_page(existing_page["id"], changed)
            replace_page_children_preserving_manual_notes(client, existing_page["id"], children, counts.warnings)
        except Exception as exc:
            counts.warn(f"{commit.short_sha}: {exc}")
            counts.skipped += 1
            if not existing_page:
                counts.created -= 1

    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Git commit history into Notion Code Change Log DB.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned operations without writing to Notion.")
    parser.add_argument("--max-count", type=int, default=30, help="Recent commit count. Default: 30")
    parser.add_argument("--since", default=None, help="Only include commits after this date.")
    parser.add_argument("--database-key", default=DEFAULT_DATABASE_KEY, help="database_ids.json key. Default: code_change_log")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        counts = sync_git_change_log(
            max_count=args.max_count,
            since=args.since,
            database_key=args.database_key,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print_counts(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
