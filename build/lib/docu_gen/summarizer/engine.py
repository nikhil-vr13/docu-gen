from __future__ import annotations
import json
import os
import subprocess
from typing import Optional

from ..config import Config
from ..models import (
    ChangeCategory,
    ChangeType,
    Commit,
    DocuGenOutput,
    DocumentedChange,
    FileChange,
    Session,
)
from .templates import (
    SUMMARIZE_COMMITS_PROMPT,
    SUMMARIZE_SESSION_PROMPT,
    format_commit_history,
    format_session_messages,
)


class SummarizeError(Exception):
    pass


def summarize_commits(
    commits: list[Commit],
    title: Optional[str] = None,
    config: Optional[Config] = None,
) -> DocuGenOutput:
    cfg = config or Config.load()
    history = format_commit_history(commits)

    all_refs: list[str] = []
    for c in commits:
        all_refs.extend(c.ticket_refs)
    all_refs = list(set(all_refs))

    contributors = list(set(c.author for c in commits if c.author))

    if _has_valid_api_key(cfg):
        return _llm_summarize_commits(commits, history, cfg, contributors, all_refs)
    return _template_summarize_commits(commits, contributors, all_refs, title)


def summarize_session(
    session: Session,
    config: Optional[Config] = None,
) -> DocuGenOutput:
    cfg = config or Config.load()
    messages = format_session_messages(session)

    if _has_valid_api_key(cfg):
        return _llm_summarize_session(session, messages, cfg)

    return _template_summarize_session(session)


def _llm_summarize_commits(
    commits: list[Commit],
    history: str,
    config: Config,
    contributors: list[str],
    ticket_refs: list[str],
) -> DocuGenOutput:
    prompt = SUMMARIZE_COMMITS_PROMPT.format(commit_history=history)
    result = _call_llm(prompt, config)
    data = _parse_llm_response(result)

    changes = []
    for c in data.get("changes", []):
        changes.append(_change_from_dict(c))

    return DocuGenOutput(
        title=data.get("title", f"Changes ({commits[0].hash[:8]}...)" if commits else "Code Changes"),
        description=data.get("description", ""),
        source_info=f"Git history ({len(commits)} commits)",
        changes=changes,
        breaking_changes=data.get("breaking_changes", []),
        contributors=contributors,
        ticket_refs_all=ticket_refs,
        raw_commits=commits,
    )


def _llm_summarize_session(
    session: Session,
    messages: str,
    config: Config,
) -> DocuGenOutput:
    prompt = SUMMARIZE_SESSION_PROMPT.format(
        tool=session.tool,
        user_goal=session.user_goal or "Not specified",
        start_time=session.start_time.strftime("%Y-%m-%d %H:%M") if session.start_time else "N/A",
        message_count=len(session.messages),
        tool_call_count=len(session.tool_calls),
        files_touched=", ".join(session.files_touched[:20]),
        session_messages=messages,
    )
    result = _call_llm(prompt, config)
    data = _parse_llm_response(result)

    changes = []
    for c in data.get("changes", []):
        changes.append(_change_from_dict(c))

    return DocuGenOutput(
        title=data.get("title", f"Session: {session.session_id[:16]}"),
        description=data.get("description", ""),
        source_info=f"Session log ({session.tool}, {len(session.messages)} messages)",
        changes=changes,
        breaking_changes=data.get("breaking_changes", []),
        contributors=[],
        ticket_refs_all=[],
        raw_commits=session.commits,
    )


def _call_llm(prompt: str, config: Config) -> str:
    provider = config.llm.provider

    if provider == "openai":
        return _call_openai(prompt, config)
    elif provider == "anthropic":
        return _call_anthropic(prompt, config)
    elif provider == "ollama":
        return _call_ollama(prompt, config)
    elif provider == "gemini":
        return _call_gemini(prompt, config)
    else:
        raise SummarizeError(f"Unsupported LLM provider: {provider}")


def _call_openai(prompt: str, config: Config) -> str:
    try:
        import openai
    except ImportError:
        raise SummarizeError(
            "openai package not installed. Run: pip install openai"
        )

    client = openai.OpenAI(api_key=config.llm.api_key)
    response = client.chat.completions.create(
        model=config.llm.model,
        messages=[
            {
                "role": "system",
                "content": "You are a technical documentation writer. Respond only with valid JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=config.llm.temperature,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or ""


def _call_anthropic(prompt: str, config: Config) -> str:
    try:
        import anthropic
    except ImportError:
        raise SummarizeError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=config.llm.api_key)
    response = client.messages.create(
        model=config.llm.model,
        max_tokens=4096,
        system="You are a technical documentation writer. Respond only with valid JSON.",
        messages=[{"role": "user", "content": prompt}],
        temperature=config.llm.temperature,
    )
    return response.content[0].text


def _call_ollama(prompt: str, config: Config) -> str:
    try:
        import httpx
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": config.llm.model,
                "prompt": prompt,
                "system": "You are a technical documentation writer. Respond only with valid JSON.",
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except ImportError:
        raise SummarizeError("httpx is required for Ollama calls")
    except Exception as e:
        raise SummarizeError(f"Ollama call failed: {e}")


def _call_gemini(prompt: str, config: Config) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise SummarizeError(
            "google-genai package not installed. Run: pip install google-genai"
        )

    client = genai.Client(api_key=config.llm.api_key)
    response = client.models.generate_content(
        model=config.llm.model or "gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are a technical documentation writer. Respond only with valid JSON.",
            temperature=config.llm.temperature,
            response_mime_type="application/json",
        ),
    )
    return response.text


def _parse_llm_response(response: str) -> dict:
    text = response.strip()

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise SummarizeError(f"Failed to parse LLM response as JSON: {text[:200]}")


def _template_summarize_commits(
    commits: list[Commit],
    contributors: list[str],
    ticket_refs: list[str],
    title: Optional[str] = None,
) -> DocuGenOutput:
    if title is None:
        title = f"Code Changes ({len(commits)} commits)"

    categories: dict[ChangeCategory, list[Commit]] = {}
    for c in commits:
        cat = c.category or ChangeCategory.OTHER
        categories.setdefault(cat, []).append(c)

    changes = []
    for cat, cat_commits in categories.items():
        files = []
        for c in cat_commits:
            files.extend(c.files)

        summary_lines = []
        for c in cat_commits:
            summary_lines.append(f"- {c.message} ({c.hash[:8]})")

        changes.append(
            DocumentedChange(
                title=cat.value.replace("_", " ").title(),
                summary="\n".join(summary_lines),
                category=cat,
                files=files,
                commits=cat_commits,
            )
        )

    desc_parts = []
    for cat, cats in categories.items():
        desc_parts.append(f"{len(cats)} {cat.value.replace('_', ' ')}")
    description = f"Summary of {len(commits)} commits: {', '.join(desc_parts)}."

    return DocuGenOutput(
        title=title,
        description=description,
        source_info=f"Git history ({len(commits)} commits)",
        changes=changes,
        contributors=contributors,
        ticket_refs_all=ticket_refs,
        raw_commits=commits,
    )


def _template_summarize_session(session: Session) -> DocuGenOutput:
    files_by_ext: dict[str, list[str]] = {}
    for f in session.files_touched:
        ext = f.split(".")[-1] if "." in f else "other"
        files_by_ext.setdefault(ext, []).append(f)

    change = DocumentedChange(
        title="Session Changes",
        summary=f"Modified files across {len(files_by_ext)} file types using {len(session.tool_calls)} tool calls.",
        category=ChangeCategory.OTHER,
        files=[FileChange(path=f, change_type=ChangeType.MODIFIED) for f in session.files_touched],
        commits=session.commits,
        technical_details=f"Tool calls: {len(session.tool_calls)}",
    )

    return DocuGenOutput(
        title=f"Session: {session.session_id[:16]}",
        description=session.user_goal or "Code changes from agent session",
        source_info=f"Session log ({session.tool}, {len(session.messages)} messages)",
        changes=[change],
        raw_commits=session.commits,
    )


def _has_valid_api_key(config: Config) -> bool:
    key = config.llm.api_key
    if not key:
        return False
    placeholders = ["sk-...", "your-api-key", "<your-key>"]
    if key.strip() in placeholders:
        return False
    if key.startswith("sk-") and len(key) < 10:
        return False
    return True


def _change_from_dict(d: dict) -> DocumentedChange:
    cat_str = d.get("category", "other")
    try:
        category = ChangeCategory(cat_str)
    except ValueError:
        category = ChangeCategory.OTHER

    return DocumentedChange(
        title=d.get("title", "Change"),
        summary=d.get("summary", ""),
        category=category,
        files=[],
        commits=[],
        breaking_change=d.get("breaking_change", False),
        ticket_refs=d.get("ticket_refs", []),
        technical_details=d.get("technical_details", ""),
        testing_notes=d.get("testing_notes", ""),
        affected_areas=d.get("affected_areas", []),
    )
