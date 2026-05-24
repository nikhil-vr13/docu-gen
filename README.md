# docu-gen

Generate Confluence documentation from AI agent session logs and git commit history. Attach structured summaries to tickets — no manual writing.

## Quickstart

```bash
pip install -e ".[all]"
docu-gen init
# Edit docu-gen.yaml with your Confluence + LLM API keys
```

## Usage

```bash
# From git: docs for all commits since 'main'
docu-gen from-git main

# From git: docs for a specific range
docu-gen from-git v1.0 v2.0

# From a branch: docs for commits since branching
docu-gen from-branch main

# From an agent session log (OpenCode/Claude)
docu-gen from-session ~/.opencode/sessions/latest.json

# All recent commits
docu-gen all-commits

# Preview as markdown without saving
docu-gen from-git main --preview
```

## Output

- **Confluence**: creates/updates pages with status badges, file tables, breaking change warnings
- **Markdown**: saves to `.md` files for PR attachments or import

## LLM Support

docu-gen uses an LLM (OpenAI, Anthropic, or Ollama) to intelligently group and summarize changes. Without an API key, it falls back to template-based grouping by commit category.

```bash
# Test your LLM connection
docu-gen test-llm

# Override model per-run
docu-gen from-git main --model gpt-4o
```

## Configuration

All options in `docu-gen.yaml` or environment variables:

| Variable | Purpose |
|---|---|
| `DOCU_GEN_CONFLUENCE_URL` | Confluence base URL |
| `DOCU_GEN_CONFLUENCE_API_TOKEN` | API token |
| `DOCU_GEN_CONFLUENCE_SPACE_KEY` | Space key |
| `DOCU_GEN_LLM_API_KEY` | OpenAI/Anthropic API key |
| `DOCU_GEN_LLM_MODEL` | Model name (default: gpt-4o) |
| `OPENAI_API_KEY` | Fallback key |

## Project Structure

```
src/docu_gen/
  main.py        CLI with Click (from-git, from-session, from-branch, all-commits)
  models.py      Data models (Commit, FileChange, Session, DocumentedChange)
  config.py      YAML + env config loading
  parsers/
    git.py       Git log/diff parser
    session.py   OpenCode + Claude session log parser
  summarizer/
    engine.py    LLM + template summarization
    templates.py Prompt templates
  output/
    confluence.py Confluence REST API v2 client
    markdown.py  Markdown export
```
