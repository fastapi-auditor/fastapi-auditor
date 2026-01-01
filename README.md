# FastAPI Auditor

**Audit your FastAPI routes for modern best practices** 🚀

Automatically analyze and score endpoints for:
- API versioning (`/v1/`, `/v2/`, etc.)
- `response_model` usage (type safety + better docs)
- OpenAPI completeness (`tags`, `summary`, `description`)
- Overall API maturity score (0–100)

Optional AI-powered modernization suggestions (gpt-4o-mini).

Ideal for code reviews, team standards, migrations, or CI/CD.

## Quick Start

```bash
# Clone and run locally (PyPI coming soon)
git clone https://github.com/fastapi-auditor/fastapi-auditor.git
cd fastapi-auditor

pip install openai  # Optional, for AI advice

python fastapi_auditor.py analyze ./path/to/your/project
