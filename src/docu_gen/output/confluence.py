from __future__ import annotations
from typing import Optional

import httpx

from ..config import Config
from ..models import DocuGenOutput


class ConfluenceClient:
    def __init__(self, config: Config):
        self.base_url = config.confluence.url.rstrip("/")
        self.username = config.confluence.username
        self.api_token = config.confluence.api_token
        self.space_key = config.confluence.space_key
        self.parent_page_id = config.confluence.parent_page_id
        self.auth = (self.username, self.api_token) if self.username and self.api_token else None

    def _api_url(self, path: str) -> str:
        return f"{self.base_url}/rest/api{path}"

    def _api_v2_url(self, path: str) -> str:
        return f"{self.base_url}/api/v2{path}"

    def _headers(self) -> dict:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, url: str) -> dict:
        resp = httpx.get(url, headers=self._headers(), auth=self.auth, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, url: str, data: dict) -> dict:
        resp = httpx.post(url, headers=self._headers(), auth=self.auth, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _put(self, url: str, data: dict) -> dict:
        resp = httpx.put(url, headers=self._headers(), auth=self.auth, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_space(self, space_key: str) -> dict:
        return self._get(self._api_url(f"/space/{space_key}"))

    def page_exists(self, title: str, space_key: Optional[str] = None) -> Optional[str]:
        sk = space_key or self.space_key
        if not sk:
            return None
        try:
            resp = self._get(
                self._api_url(f"/content?title={title}&spaceKey={sk}&limit=1")
            )
            results = resp.get("results", [])
            if results:
                return results[0]["id"]
        except httpx.HTTPStatusError:
            pass
        return None

    def create_or_update_page(
        self,
        output: DocuGenOutput,
        space_key: Optional[str] = None,
        parent_page_id: Optional[str] = None,
    ) -> str:
        sk = space_key or self.space_key
        pid = parent_page_id or self.parent_page_id

        html_body = self._render_to_confluence_html(output)

        existing_id = self.page_exists(output.title, sk)

        if existing_id:
            return self._update_page(existing_id, output.title, html_body)
        else:
            return self._create_page(output.title, html_body, sk, pid)

    def _create_page(
        self,
        title: str,
        html_body: str,
        space_key: str,
        parent_page_id: Optional[str] = None,
    ) -> str:
        ancestors = (
            [{"id": parent_page_id}] if parent_page_id else []
        )
        data = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": html_body,
                    "representation": "storage",
                }
            },
        }
        if ancestors:
            data["ancestors"] = ancestors

        result = self._post(self._api_url("/content"), data)
        page_id = result.get("id", "")
        return f"{self.base_url}/spaces/{space_key}/pages/{page_id}"

    def _update_page(self, page_id: str, title: str, html_body: str) -> str:
        existing = self._get(self._api_url(f"/content/{page_id}"))
        version = existing.get("version", {}).get("number", 0)

        data = {
            "id": page_id,
            "type": "page",
            "title": title,
            "body": {
                "storage": {
                    "value": html_body,
                    "representation": "storage",
                }
            },
            "version": {"number": version + 1},
        }

        result = self._put(self._api_url(f"/content/{page_id}"), data)
        return f"{self.base_url}/spaces/{result.get('space', {}).get('key', '')}/pages/{page_id}"

    def _render_to_confluence_html(self, output: DocuGenOutput) -> str:
        parts = [
            f'<h1>{self._escape(output.title)}</h1>',
            f'<p>{self._escape(output.description)}</p>',
            '<hr/>',
        ]

        meta_lines = []
        if output.contributors:
            meta_lines.append(
                f"<p><strong>Contributors:</strong> {self._escape(', '.join(output.contributors))}</p>"
            )
        if output.ticket_refs_all:
            meta_lines.append(
                f"<p><strong>Tickets:</strong> {self._escape(', '.join(output.ticket_refs_all))}</p>"
            )
        meta_lines.append(
            f"<p><strong>Source:</strong> {self._escape(output.source_info)}</p>"
        )
        meta_lines.append(
            f"<p><strong>Generated:</strong> {output.generated_at.strftime('%Y-%m-%d %H:%M:%S')}</p>"
        )
        parts.extend(meta_lines)
        parts.append('<hr/>')

        if output.breaking_changes:
            parts.append('<ac:structured-macro ac:name="warning">')
            parts.append('<ac:rich-text-body>')
            parts.append("<h2>Breaking Changes</h2><ul>")
            for bc in output.breaking_changes:
                parts.append(f"<li>{self._escape(bc)}</li>")
            parts.append("</ul>")
            parts.append('</ac:rich-text-body>')
            parts.append('</ac:structured-macro>')

        for change in output.changes:
            parts.append(f'<h2>{self._escape(change.title)}</h2>')

            cat_label = change.category.value.replace("_", " ").title()
            parts.append(
                f'<p><strong>Category:</strong> '
                f'<ac:structured-macro ac:name="status">'
                f'<ac:parameter ac:name="colour">{self._status_colour(change.category.value)}</ac:parameter>'
                f'<ac:parameter ac:name="title">{cat_label}</ac:parameter>'
                f'</ac:structured-macro></p>'
            )

            if change.breaking_change:
                parts.append(
                    '<p><ac:structured-macro ac:name="status">'
                    '<ac:parameter ac:name="colour">Red</ac:parameter>'
                    '<ac:parameter ac:name="title">Breaking</ac:parameter>'
                    '</ac:structured-macro> Breaking Change</p>'
                )

            if change.ticket_refs:
                parts.append(f"<p><strong>Tickets:</strong> {self._escape(', '.join(change.ticket_refs))}</p>")

            parts.append(f"<p>{self._escape(change.summary)}</p>")

            if change.technical_details:
                parts.append(f"<h3>Technical Details</h3>")
                parts.append(
                    f"<pre>{self._escape(change.technical_details)}</pre>"
                )

            if change.testing_notes:
                parts.append(f"<h3>Testing Notes</h3>")
                parts.append(f"<p>{self._escape(change.testing_notes)}</p>")

            if change.files:
                parts.append(f"<h3>Files Changed</h3>")
                parts.append('<table><tbody>')
                parts.append('<tr><th>File</th><th>Type</th><th>Added</th><th>Removed</th></tr>')
                for f in change.files:
                    parts.append(
                        f"<tr><td><code>{self._escape(f.path)}</code></td>"
                        f"<td>{f.change_type.value}</td>"
                        f"<td>{f.lines_added}</td>"
                        f"<td>{f.lines_removed}</td></tr>"
                    )
                parts.append('</tbody></table>')

            parts.append('<hr/>')

        return "\n".join(parts)

    def _status_colour(self, category: str) -> str:
        colours = {
            "bug_fix": "Red",
            "feature": "Green",
            "refactor": "Blue",
            "performance": "Purple",
            "test": "Teal",
            "docs": "Grey",
            "chore": "Grey",
            "dependency": "Yellow",
        }
        return colours.get(category, "Grey")

    @staticmethod
    def _escape(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )


def push_to_confluence(
    output: DocuGenOutput,
    config: Config,
    space_key: Optional[str] = None,
    parent_page_id: Optional[str] = None,
) -> str:
    client = ConfluenceClient(config)
    return client.create_or_update_page(output, space_key, parent_page_id)
