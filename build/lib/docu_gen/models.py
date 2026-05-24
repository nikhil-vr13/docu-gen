from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional


class ChangeType(Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class ChangeCategory(Enum):
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    TEST = "test"
    DOCS = "docs"
    CHORE = "chore"
    DEPENDENCY = "dependency"
    OTHER = "other"


@dataclass
class FileChange:
    path: str
    change_type: ChangeType
    old_path: Optional[str] = None
    diff: Optional[str] = None
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class Commit:
    hash: str
    author: str
    date: datetime
    message: str
    body: str = ""
    files: list[FileChange] = field(default_factory=list)
    category: Optional[ChangeCategory] = None
    ticket_refs: list[str] = field(default_factory=list)

    @property
    def full_message(self) -> str:
        return f"{self.message}\n\n{self.body}" if self.body else self.message


@dataclass
class ToolCall:
    tool_name: str
    input_summary: str
    timestamp: Optional[datetime] = None
    status: Optional[str] = None


@dataclass
class SessionMessage:
    role: str
    content: str
    timestamp: Optional[datetime] = None


@dataclass
class Session:
    session_id: str
    tool: str
    start_time: datetime
    end_time: Optional[datetime] = None
    user_goal: Optional[str] = None
    messages: list[SessionMessage] = field(default_factory=list)
    commits: list[Commit] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)


@dataclass
class DocumentedChange:
    title: str
    summary: str
    category: ChangeCategory
    files: list[FileChange]
    commits: list[Commit]
    breaking_change: bool = False
    ticket_refs: list[str] = field(default_factory=list)
    technical_details: str = ""
    testing_notes: str = ""
    affected_areas: list[str] = field(default_factory=list)

    @property
    def file_paths(self) -> list[str]:
        return [f.path for f in self.files]


@dataclass
class DocuGenOutput:
    title: str
    description: str
    source_info: str
    generated_at: datetime = field(default_factory=datetime.now)
    changes: list[DocumentedChange] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    contributors: list[str] = field(default_factory=list)
    ticket_refs_all: list[str] = field(default_factory=list)
    raw_commits: list[Commit] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", "", self.description, ""]

        if self.contributors:
            lines.append(f"**Contributors:** {', '.join(self.contributors)}")
            lines.append("")

        if self.ticket_refs_all:
            refs = ", ".join(self.ticket_refs_all)
            lines.append(f"**Tickets:** {refs}")
            lines.append("")

        lines.append(f"**Source:** {self.source_info}")
        lines.append(f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        if self.breaking_changes:
            lines.append("## Breaking Changes")
            lines.append("")
            for bc in self.breaking_changes:
                lines.append(f"- {bc}")
            lines.append("")

        for change in self.changes:
            lines.append(f"## {change.title}")
            lines.append("")
            lines.append(f"**Category:** {change.category.value.replace('_', ' ').title()}")
            lines.append("")
            if change.breaking_change:
                lines.append("**⚠️ Breaking Change**")
                lines.append("")

            if change.ticket_refs:
                lines.append(f"**Tickets:** {', '.join(change.ticket_refs)}")
                lines.append("")

            lines.append(change.summary)
            lines.append("")

            if change.technical_details and change.technical_details.strip():
                lines.append("### Technical Details")
                lines.append("")
                lines.append(change.technical_details)
                lines.append("")

            if change.testing_notes and change.testing_notes.strip():
                lines.append("### Testing Notes")
                lines.append("")
                lines.append(change.testing_notes)
                lines.append("")

            if change.affected_areas:
                lines.append("### Affected Areas")
                lines.append("")
                for area in change.affected_areas:
                    lines.append(f"- {area}")
                lines.append("")

            if change.files:
                lines.append("### Files Changed")
                lines.append("")
                for f in change.files:
                    icon = {"added": "+", "modified": "~", "deleted": "-", "renamed": "→"}.get(
                        f.change_type.value, "•"
                    )
                    lines.append(f"- `{icon} {f.path}` ({f.change_type.value})")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
