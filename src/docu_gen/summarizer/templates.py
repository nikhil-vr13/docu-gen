SUMMARIZE_COMMITS_PROMPT = """You are a technical documentation writer. Given the following git commit history, produce a structured summary of changes suitable for a Confluence page.

Group related commits together. For each group, provide:
1. A clear title
2. A concise summary of what changed and why
3. The category (bug_fix, feature, refactor, performance, test, docs, chore, dependency, other)
4. Whether it's a breaking change
5. Technical details (key implementation decisions, architecture changes)
6. Testing notes
7. The affected areas/modules

Commit History:
{commit_history}

Respond with a JSON object:
{{
  "title": "Overall release/change title",
  "description": "High-level overview paragraph",
  "breaking_changes": ["list of breaking change descriptions"],
  "contributors": ["list of contributors"],
  "ticket_refs": ["all ticket references"],
  "changes": [
    {{
      "title": "Change group title",
      "summary": "What changed and why",
      "category": "bug_fix|feature|refactor|performance|test|docs|chore|dependency|other",
      "breaking_change": false,
      "ticket_refs": ["PROJ-123"],
      "technical_details": "Implementation details",
      "testing_notes": "How to test this change",
      "affected_areas": ["module/area1", "module/area2"]
    }}
  ]
}}
"""

SUMMARIZE_SESSION_PROMPT = """You are a technical documentation writer. Given the following AI coding agent session log, produce a structured summary of the changes made during the session.

Session Information:
- Tool: {tool}
- User Goal: {user_goal}
- Start: {start_time}
- Messages: {message_count}
- Tool Calls: {tool_call_count}
- Files Touched: {files_touched}

Session Messages:
{session_messages}

Respond with a JSON object:
{{
  "title": "Summary of session changes",
  "description": "What was accomplished in this session",
  "breaking_changes": ["list of breaking change descriptions"],
  "changes": [
    {{
      "title": "Change group title",
      "summary": "What changed and why",
      "category": "bug_fix|feature|refactor|performance|test|docs|chore|dependency|other",
      "breaking_change": false,
      "ticket_refs": [],
      "technical_details": "Implementation details",
      "testing_notes": "How to test this change",
      "affected_areas": ["module/area1"]
    }}
  ]
}}
"""

NO_LLM_FALLBACK_TEMPLATE = """# {title}

## Summary
{description}

## Changes

{changes_section}

## Files Changed
{files_section}
"""


def format_commit_history(commits: list) -> str:
    lines = []
    for c in commits:
        files_str = ", ".join(f.path for f in c.files[:10])
        if len(c.files) > 10:
            files_str += f" ... (+{len(c.files) - 10} more)"
        lines.append(f"Commit: {c.hash[:8]}")
        lines.append(f"Author: {c.author}")
        lines.append(f"Date: {c.date.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Message: {c.message}")
        if c.body:
            lines.append(f"Body: {c.body[:200]}")
        if files_str:
            lines.append(f"Files: {files_str}")
        lines.append("---")
    return "\n".join(lines)


def format_session_messages(session) -> str:
    lines = []
    for msg in session.messages[-20:]:
        content = msg.content[:300]
        if len(msg.content) > 300:
            content += "..."
        lines.append(f"[{msg.role}] {content}")
        lines.append("---")
    return "\n".join(lines)
