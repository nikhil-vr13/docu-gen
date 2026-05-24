from __future__ import annotations
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..models import ChangeCategory, ChangeType, Commit, FileChange


def _run_git(*args: str, cwd: Optional[str] = None) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd or ".",
        check=True,
    )
    return result.stdout


def parse_commit_range(
    since_ref: str,
    until_ref: Optional[str] = None,
    repo_path: Optional[str] = None,
) -> list[Commit]:
    if until_ref:
        rev_range = f"{since_ref}..{until_ref}"
    else:
        rev_range = f"{since_ref}..HEAD"

    log_output = _run_git(
        "log",
        rev_range,
        "--format=---COMMIT---\n%H|||%an|||%ai|||%s|||%b",
        "--no-merges",
        cwd=repo_path,
    )
    return _parse_git_log(log_output, repo_path)


def parse_commits_since(
    ref: str,
    repo_path: Optional[str] = None,
) -> list[Commit]:
    return parse_commit_range(ref, repo_path=repo_path)


def parse_all_commits(
    repo_path: Optional[str] = None,
    max_count: int = 100,
) -> list[Commit]:
    log_output = _run_git(
        "log",
        f"--max-count={max_count}",
        "--format=---COMMIT---\n%H|||%an|||%ai|||%s|||%b",
        "--no-merges",
        cwd=repo_path,
    )
    return _parse_git_log(log_output, repo_path)


def parse_commit_range_by_branch(
    base_branch: str = "main",
    head_branch: Optional[str] = None,
    repo_path: Optional[str] = None,
) -> list[Commit]:
    if head_branch is None:
        head_branch = _run_git("branch", "--show-current", cwd=repo_path).strip()
    return parse_commit_range(base_branch, head_branch, repo_path)


def _parse_git_log(log_output: str, repo_path: Optional[str] = None) -> list[Commit]:
    commits: list[Commit] = []
    blocks = log_output.split("---COMMIT---\n")

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        parts = block.split("|||", 4)
        if len(parts) < 4:
            continue

        hash_val = parts[0].strip()
        author = parts[1].strip()
        date_str = parts[2].strip()
        message = parts[3].strip()
        body = parts[4].strip() if len(parts) > 4 else ""

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")
            except ValueError:
                date = datetime.now()

        ticket_refs = _extract_ticket_refs(message + " " + body)

        commit = Commit(
            hash=hash_val,
            author=author,
            date=date,
            message=message,
            body=body,
            ticket_refs=ticket_refs,
        )

        try:
            diff_output = _run_git(
                "diff",
                f"{hash_val}^..{hash_val}",
                "--stat",
                cwd=repo_path,
            )
            commit.files = _parse_diff_stat(diff_output, hash_val, repo_path)
        except subprocess.CalledProcessError:
            try:
                diff_output = _run_git(
                    "diff",
                    f"{hash_val}^..{hash_val}",
                    "--stat",
                    cwd=repo_path,
                )
                commit.files = _parse_diff_stat(diff_output, hash_val, repo_path)
            except subprocess.CalledProcessError:
                pass

        commit.category = _categorize_commit(commit)
        commits.append(commit)

    return commits


def _parse_diff_stat(
    stat_output: str,
    commit_hash: str,
    repo_path: Optional[str] = None,
) -> list[FileChange]:
    files: list[FileChange] = []
    for line in stat_output.strip().split("\n"):
        if not line or "file changed" in line or "files changed" in line:
            continue
        match = re.match(
            r'\s*(.+?)\s*\|\s*\d+\s*[+-]+(\+*)(-*)$',
            line,
        )
        if match:
            path = match.group(1).strip()
            plus = len(match.group(2))
            minus = len(match.group(3))
            change_type = ChangeType.MODIFIED
            try:
                name_status = _run_git(
                    "diff",
                    f"{commit_hash}^..{commit_hash}",
                    "--name-status",
                    cwd=repo_path,
                )
                for ns_line in name_status.strip().split("\n"):
                    parts = ns_line.split("\t")
                    if len(parts) >= 2 and parts[1] == path:
                        status = parts[0]
                        if status.startswith("A"):
                            change_type = ChangeType.ADDED
                        elif status.startswith("D"):
                            change_type = ChangeType.DELETED
                        elif status.startswith("R"):
                            change_type = ChangeType.RENAMED
                        break
            except subprocess.CalledProcessError:
                pass

            diff_content = ""
            try:
                diff_content = _run_git(
                    "diff",
                    f"{commit_hash}^..{commit_hash}",
                    "--",
                    path,
                    cwd=repo_path,
                )
            except subprocess.CalledProcessError:
                pass

            files.append(
                FileChange(
                    path=path,
                    change_type=change_type,
                    diff=diff_content,
                    lines_added=plus,
                    lines_removed=minus,
                )
            )
    return files


def _extract_ticket_refs(text: str) -> list[str]:
    patterns = [
        r'(?i)(?:fixes?|closes?|resolves?|refs?)\s+#(\d+)',
        r'(?i)(?:fixes?|closes?|resolves?|refs?)\s+([A-Z]+-\d+)',
        r'(?i)PROJ-\d+',
        r'(?i)JIRA-\d+',
        r'\b[A-Z]{2,6}-\d{1,6}\b',
    ]
    refs: list[str] = []
    for pat in patterns:
        refs.extend(re.findall(pat, text))
    return list(set(refs))


_COMMIT_CATEGORY_PATTERNS: dict[str, list[str]] = {
    "bug_fix": [
        r"(?i)^fix", r"(?i)^bug", r"(?i)hotfix", r"(?i)patch",
        r"(?i)resolve[sd]?.*bug", r"(?i)fixes?.*issue",
    ],
    "feature": [
        r"(?i)^feat", r"(?i)^feature", r"(?i)add[s]?", r"(?i)implement",
        r"(?i)new:", r"(?i)introduce",
    ],
    "refactor": [
        r"(?i)^refactor", r"(?i)^refactor", r"(?i)^rework",
        r"(?i)cleanup", r"(?i)restructure", r"(?i)simplify",
    ],
    "performance": [
        r"(?i)^perf", r"(?i)performance", r"(?i)optimize", r"(?i)improve.*speed",
    ],
    "test": [
        r"(?i)^test", r"(?i)add.*test", r"(?i)update.*test",
    ],
    "docs": [
        r"(?i)^docs?", r"(?i)document", r"(?i)readme",
    ],
    "chore": [
        r"(?i)^chore", r"(?i)^bump", r"(?i)^update\s+(dep|version|config)",
        r"(?i)merge", r"(?i)lint",
    ],
    "dependency": [
        r"(?i)^dep", r"(?i)dependabot", r"(?i)upgrade.*dep",
    ],
}


def _categorize_commit(commit: Commit) -> Optional[ChangeCategory]:
    text = f"{commit.message} {commit.body}"
    for cat, patterns in _COMMIT_CATEGORY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text):
                return ChangeCategory(cat)
    return None
