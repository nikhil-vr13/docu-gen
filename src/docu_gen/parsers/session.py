from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..models import ChangeType, Commit, FileChange, Session, SessionMessage, ToolCall


def parse_opencode_log(filepath: str) -> Optional[Session]:
    path = Path(filepath)
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw) if raw.strip().startswith("{") else _parse_ndjson(raw)

    session = Session(
        session_id=data.get("session_id", path.stem),
        tool="opencode",
        start_time=_parse_time(data.get("start_time")),
        end_time=_parse_time(data.get("end_time")),
        user_goal=data.get("user_goal", ""),
    )

    messages = data.get("messages", data.get("conversation", []))
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", msg.get("text", ""))
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        session.messages.append(
            SessionMessage(
                role=role,
                content=str(content),
                timestamp=_parse_time(msg.get("timestamp")),
            )
        )

    tool_calls = data.get("tool_calls", data.get("actions", []))
    for tc in tool_calls:
        name = tc.get("name", tc.get("tool", tc.get("tool_name", "unknown")))
        inp = tc.get("input", tc.get("args", tc.get("arguments", "")))
        if isinstance(inp, dict):
            inp = json.dumps(inp)
        session.tool_calls.append(
            ToolCall(
                tool_name=name,
                input_summary=str(inp)[:200],
                timestamp=_parse_time(tc.get("timestamp")),
                status=tc.get("status"),
            )
        )

    files = _extract_files_from_session(session)
    session.files_touched = list(set(files))

    commits = _extract_commits_from_session(session)
    session.commits = commits

    return session


def parse_claude_log(filepath: str) -> Optional[Session]:
    path = Path(filepath)
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)

    session = Session(
        session_id=data.get("uuid", data.get("id", path.stem)),
        tool="claude",
        start_time=_parse_time(data.get("start_time", data.get("created_at"))),
        end_time=_parse_time(data.get("end_time", data.get("updated_at"))),
    )

    for msg in data.get("messages", data.get("chat_messages", [])):
        role = msg.get("role", msg.get("sender", "unknown"))
        content = msg.get("content", msg.get("text", ""))
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        parts.append(c.get("text", ""))
                    elif c.get("type") == "tool_use":
                        parts.append(f"[Tool: {c.get('name', 'unknown')}]")
                else:
                    parts.append(str(c))
            content = "\n".join(parts)
        session.messages.append(
            SessionMessage(
                role=role,
                content=str(content),
                timestamp=_parse_time(msg.get("timestamp", msg.get("created_at"))),
            )
        )

    files = _extract_files_from_session(session)
    session.files_touched = list(set(files))
    session.commits = _extract_commits_from_session(session)

    return session


def parse_session_log(filepath: str) -> Optional[Session]:
    path = Path(filepath)
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8")[:2000]
    if "opencode" in raw.lower() or "tool_calls" in raw:
        return parse_opencode_log(filepath)
    elif "claude" in raw.lower() or "chat_messages" in raw:
        return parse_claude_log(filepath)
    else:
        try:
            return parse_opencode_log(filepath)
        except (json.JSONDecodeError, KeyError):
            try:
                return parse_claude_log(filepath)
            except (json.JSONDecodeError, KeyError):
                return None


def _parse_ndjson(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in raw.strip().split("\n"):
        if line.strip():
            try:
                entry = json.loads(line)
                for key, value in entry.items():
                    if key not in result:
                        result[key] = value
            except json.JSONDecodeError:
                pass
    return result


_FILE_CHANGE_RE = re.compile(
    r"(?i)(?:edited|modified|created|added|deleted|removed|renamed)\s+(?:file\s+)?[`'\"]?([\/\w\.\-_]+)[`'\"]?"
)
_SRC_PATH_RE = re.compile(
    r'(?:src|app|lib|packages|components|pages|utils|hooks|services)\/[\/\w\.\-_]+\.\w+'
)
_GIT_COMMIT_RE = re.compile(r"(?i)(?:commit|pushed|committed):?\s*([a-f0-9]{7,40})")


def _extract_files_from_session(session: Session) -> list[str]:
    files: list[str] = []
    for msg in session.messages:
        files.extend(_FILE_CHANGE_RE.findall(msg.content))
        files.extend(_SRC_PATH_RE.findall(msg.content))

    for tc in session.tool_calls:
        files.extend(_FILE_CHANGE_RE.findall(tc.input_summary))
        files.extend(_SRC_PATH_RE.findall(tc.input_summary))

    return files


def _extract_commits_from_session(session: Session) -> list[Commit]:
    commits: list[Commit] = []
    seen_hashes: set[str] = set()

    for msg in session.messages:
        matches = _GIT_COMMIT_RE.findall(msg.content)
        for h in matches:
            full_hash = h
            if h not in seen_hashes:
                seen_hashes.add(h)
                commits.append(
                    Commit(
                        hash=full_hash,
                        author="",
                        date=datetime.now(),
                        message="[Extracted from session log]",
                    )
                )

    return commits


def _parse_time(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val)
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
