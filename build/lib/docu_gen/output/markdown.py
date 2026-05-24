from __future__ import annotations

from ..models import DocuGenOutput


def generate_markdown(output: DocuGenOutput) -> str:
    return output.to_markdown()


def save_markdown(output: DocuGenOutput, filepath: str) -> str:
    md = generate_markdown(output)
    with open(filepath, "w") as f:
        f.write(md)
    return filepath
