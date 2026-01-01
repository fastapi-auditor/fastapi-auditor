#!/usr/bin/env python3
import os
import re
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

from openai import OpenAI

# =========================================================
# TOOL METADATA
# =========================================================

TOOL_NAME = "ModernAPI"
FORMAL_NAME = "API Modernization Audit (FastAPI)"
TOOL_VERSION = "0.2.0"
RULESET = "fastapi-core"

EXIT_OK = 0
EXIT_SCORE_BELOW_THRESHOLD = 1
EXIT_INVALID_REPO = 2
EXIT_INTERNAL_ERROR = 3

# =========================================================
# CONFIGURATION
# =========================================================

DEFAULT_AI_MODEL = "gpt-4o-mini"
DEFAULT_AI_LIMIT = 5
VERSION_PATTERN = re.compile(r"/v\d+", re.IGNORECASE)

# Robust route decorator matching (supports app/router, multi-line, spacing)
ROUTE_PATTERN = re.compile(
    r"@\w+\.(get|post|put|patch|delete|options|head|trace|route)\s*\(",
    re.IGNORECASE
)

# =========================================================
# CLIENT SETUP
# =========================================================

def get_openai_client() -> OpenAI | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️  Warning: OPENAI_API_KEY not set. AI advice will be disabled.")
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        print(f"⚠️  Failed to initialize OpenAI client: {e}")
        return None


client = get_openai_client()

# =========================================================
# ANALYSIS (ROBUST ROUTE PARSING)
# =========================================================

def extract_string_arg(arg_str: str, keyword: str) -> str | None:
    """Extract value from key=value or bare string literal."""
    pattern = rf"{keyword}\s*=\s*[\"']([^\"']+)[\"']"
    match = re.search(pattern, arg_str)
    if match:
        return match.group(1)

    # Fallback: if no keyword, assume first string is path (common for .get("/path"))
    if keyword == "path":
        bare_match = re.search(r"^\s*[\"']([^\"']+)[\"']", arg_str)
        if bare_match:
            return bare_match.group(1)
    return None


def has_kwarg(arg_str: str, keyword: str) -> bool:
    return re.search(rf"{keyword}\s*=", arg_str) is not None


def analyze_routes(repo_path: Path) -> List[Dict[str, Any]]:
    routes = []

    for root, _, files in os.walk(repo_path):
        for file in files:
            if not file.endswith(".py"):
                continue

            file_path = Path(root) / file
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue  # Skip unreadable files silently

            # Find all route decorators
            for match in ROUTE_PATTERN.finditer(content):
                start_pos = match.end()
                # Extract argument block inside parentheses (naive but effective)
                paren_depth = 1
                arg_start = start_pos
                i = start_pos
                while i < len(content) and paren_depth > 0:
                    if content[i] == "(":
                        paren_depth += 1
                    elif content[i] == ")":
                        paren_depth -= 1
                    i += 1
                decorator_args = content[arg_start:i-1].strip()

                path = extract_string_arg(decorator_args, "path")
                if not path:
                    path = "UNKNOWN"

                method = match.group(1).upper()

                routes.append({
                    "method": method,
                    "path": path,
                    "file": str(file_path.relative_to(repo_path)),
                    "versioned": bool(VERSION_PATTERN.search(path)),
                    "has_response_model": has_kwarg(decorator_args, "response_model"),
                    "has_tags": has_kwarg(decorator_args, "tags"),
                    "has_summary": has_kwarg(decorator_args, "summary"),
                    "has_description": has_kwarg(decorator_args, "description"),
                    "decorator_args": decorator_args,  # For better AI context
                })

    return routes


# =========================================================
# SCORING
# =========================================================

def score_route(route: Dict[str, Any]) -> Dict[str, Any]:
    score = 100
    penalties = []

    if not route["versioned"]:
        score -= 20
        penalties.append("Missing API versioning (e.g., /v1/, /v2/)")

    if not route["has_response_model"]:
        score -= 25
        penalties.append("Missing response_model (critical for typing & docs)")

    if not route["has_tags"]:
        score -= 10
        penalties.append("Missing tags= for OpenAPI grouping")

    if not route["has_summary"]:
        score -= 10
        penalties.append("Missing summary= for endpoint title")

    if not route["has_description"]:
        score -= 5
        penalties.append("Missing description= for details")

    route["score"] = max(score, 30)
    route["penalties"] = penalties
    return route


# =========================================================
# AI ADVISOR
# =========================================================

def advise_route(route: Dict[str, Any], model: str) -> str:
    if not client:
        return "[AI unavailable: OpenAI client not initialized]"

    try:
        prompt = f"""
You are a senior FastAPI engineer performing a code review.

Improve this route definition to follow modern FastAPI best practices.

Current route:
- Method: {route['method']}
- Path: {route['path']}
- File: {route['file']}
- Versioned: {'Yes' if route['versioned'] else 'No'}
- Has response_model: {'Yes' if route['has_response_model'] else 'No'}
- Has tags: {'Yes' if route['has_tags'] else 'No'}
- Has summary: {'Yes' if route['has_summary'] else 'No'}
- Has description: {'Yes' if route['has_description'] else 'No'}

Current decorator arguments:
```{route['decorator_args']}```

Suggest:
1. Specific issues
2. Recommended fixes
3. A complete improved decorator example

Prioritize: versioning, response_model, tags, summary/description.
"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise, pragmatic FastAPI modernization advisor."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"[AI ERROR] {str(e)}"


# =========================================================
# REPORTING
# =========================================================

def write_markdown_report(repo_name: str, routes: List[Dict], repo_score: float, ai_enabled: bool, output_path: Path):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {TOOL_NAME}\n")
        f.write(f"## {FORMAL_NAME}\n\n")
        f.write(f"**Tool Version:** {TOOL_VERSION}  \n")
        f.write(f"**Ruleset:** {RULESET}  \n")
        f.write(f"**AI Advice:** {'Enabled' if ai_enabled else 'Disabled'}  \n")
        f.write(f"**Repository:** `{repo_name}`  \n")
        f.write(f"**Generated:** {timestamp}\n\n")
        f.write("---\n\n")
        f.write("## API Maturity Score\n\n")
        f.write(f"**Overall Score: {repo_score}/100**\n\n")
        f.write(f"Routes analyzed: {len(routes)}\n")
        f.write(f"Perfect routes: {len([r for r in routes if r['score'] == 100])}\n")
        f.write(f"Needs improvement: {len([r for r in routes if r['score'] < 100])}\n\n")
        f.write("---\n\n")

        for r in routes:
            f.write(f"### `{r['method']} {r['path']}`\n")
            f.write(f"- **File:** `{r['file']}`\n")
            f.write(f"- **Score:** {r['score']}/100\n")
            f.write(f"- **Issues:** {', '.join(r['penalties']) if r['penalties'] else 'None 🎉'}\n\n")

            if "advice" in r:
                f.write("**Recommended Modernization:**\n\n")
                f.write("```\n")
                f.write(r["advice"])
                f.write("\n```\n\n")

            f.write("---\n\n")

    return output_path


def write_json_report(routes: List[Dict], repo_score: float, output_path: Path):
    report = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "score": repo_score,
        "routes_analyzed": len(routes),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "routes": routes
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return output_path


# =========================================================
# CLI COMMAND
# =========================================================

def analyze_command(args):
    print(f"{TOOL_NAME} v{TOOL_VERSION}")
    print(f"{FORMAL_NAME}")
    print(f"Ruleset: {RULESET}\n")

    repo_path = Path(args.repo_path).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        print("❌ Invalid repository path")
        sys.exit(EXIT_INVALID_REPO)

    print(f"🔍 Scanning: {repo_path}\n")

    routes = analyze_routes(repo_path)
    if not routes:
        print("❌ No FastAPI routes detected")
        sys.exit(EXIT_INTERNAL_ERROR)

    scored_routes = [score_route(r) for r in routes]
    repo_score = round(sum(r["score"] for r in scored_routes) / len(scored_routes), 1)

    print(f"📊 API MATURITY SCORE: {repo_score}/100")
    print(f"   Routes analyzed: {len(routes)}")
    print(f"   Needs improvement: {len([r for r in scored_routes if r['score'] < 100])}\n")

    if args.summary_only:
        sys.exit(EXIT_OK)

    # AI Advice
    ai_enabled = not args.no_ai and client is not None
    if ai_enabled:
        print(f"🤖 Generating AI advice (limit: {args.ai_limit})...")
        remaining = args.ai_limit
        for r in scored_routes:
            if r["score"] < 100 and remaining > 0:
                r["advice"] = advise_route(r, args.model)
                remaining -= 1

    # Output
    base_name = repo_path.name
    md_path = args.output or Path("api_modernization_report.md")
    json_path = args.json

    write_markdown_report(base_name, scored_routes, repo_score, ai_enabled, md_path)
    print(f"✅ Markdown report: {md_path.resolve()}")

    if json_path:
        json_full_path = Path(json_path)
        write_json_report(scored_routes, repo_score, json_full_path)
        print(f"✅ JSON report: {json_full_path.resolve()}")

    # Fail on low score
    if args.fail_under is not None and repo_score < args.fail_under:
        print(f"❌ Score {repo_score} is below threshold ({args.fail_under})")
        sys.exit(EXIT_SCORE_BELOW_THRESHOLD)

    print("\n🎉 Audit complete!")
    sys.exit(EXIT_OK)


# =========================================================
# MAIN
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description="ModernAPI — FastAPI Modernization Auditor",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="Analyze a FastAPI repository")
    analyze.add_argument("repo_path", help="Path to the FastAPI project directory")
    analyze.add_argument("--ai-limit", type=int, default=DEFAULT_AI_LIMIT,
                        help="Max number of routes to get AI advice for")
    analyze.add_argument("--no-ai", action="store_true",
                        help="Disable AI-powered suggestions")
    analyze.add_argument("--model", default=DEFAULT_AI_MODEL,
                        help="OpenAI model for advice")
    analyze.add_argument("--output", "-o", help="Output Markdown report path")
    analyze.add_argument("--json", help="Also save JSON report to this path")
    analyze.add_argument("--summary-only", action="store_true",
                        help="Only show score summary, no report")
    analyze.add_argument("--fail-under", type=int,
                        help="Exit with error if score is below this value")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "analyze":
        analyze_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
        sys.exit(EXIT_INTERNAL_ERROR)