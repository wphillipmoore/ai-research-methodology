#!/usr/bin/env python3
"""Compile sub-agent prompts by concatenating guidelines + prompt + schema.

Produces self-contained prompt files the Claude Code plugin reads from
`ai-research-methodology/skills/research/prompts/compiled/`. Each compiled
prompt includes the common guidelines, the sub-agent prompt, and the
output JSON schema — everything the model needs in a single file.

Also produces `ai-research-methodology/standalone/research.md`: a single
copy-paste unified methodology doc for any AI interface without the
skill or MCP server.

The CLI (`dio run`) does NOT read compiled prompts — it constructs them
in-memory from `src/diogenes/prompts/sub-agents/` and `src/diogenes/schemas/`.
Only the skill path reads the compiled output.

Usage:
    python scripts/compile-prompts.py
"""

from __future__ import annotations

import json
from pathlib import Path

# Source locations (inside the package)
PACKAGE_DIR = Path(__file__).parent.parent / "src" / "diogenes"
PROMPTS_DIR = PACKAGE_DIR / "prompts"
SCHEMAS_DIR = PACKAGE_DIR / "schemas"
GUIDELINES_PATH = PROMPTS_DIR / "common-guidelines.md"

# Output locations.
REPO_ROOT = Path(__file__).parent.parent
SKILL_COMPILED_DIR = REPO_ROOT / "ai-research-methodology" / "skills" / "research" / "prompts" / "compiled"
STANDALONE_PATH = REPO_ROOT / "ai-research-methodology" / "standalone" / "research.md"

# Mapping: sub-agent prompt filename -> output schema filename
# Sub-agents that don't have an output schema (or don't need one compiled)
# are omitted.
PROMPT_SCHEMA_MAP: dict[str, str | None] = {
    "clarified-input.md": "clarified-input.schema.json",
    "hypotheses.md": "hypotheses.schema.json",
    "search-plans.md": "search-plans.schema.json",
    "search-results.md": "relevance-scores.schema.json",
    "result-selector.md": "search-results.schema.json",
    "search-executor.md": "search-results.schema.json",
    # source-scorer emits only scoring fields (see source-scorer-output schema).
    # The Python coordinator rehydrates content_extract/title/snippet/items
    # from its own copy of the input into the persisted source-scorecards
    # format that downstream sub-agents read.
    "scorecards.md": "scorecards.schema.json",
    "evidence-packets.md": "evidence-packets.schema.json",
    "synthesis.md": "synthesis.schema.json",
    "self-audit.md": "self-audit.schema.json",
    "reports.md": "reports.schema.json",
}


def compile_prompt(prompt_name: str, schema_name: str | None) -> str:
    """Compile a single prompt with guidelines and schema."""
    parts: list[str] = []

    # Part 1: Common guidelines
    if GUIDELINES_PATH.exists():
        parts.append(GUIDELINES_PATH.read_text().strip())

    # Part 2: Sub-agent prompt
    prompt_path = PROMPTS_DIR / "sub-agents" / prompt_name
    if not prompt_path.exists():
        msg = f"Prompt not found: {prompt_path}"
        raise FileNotFoundError(msg)
    parts.append(prompt_path.read_text().strip())

    # Part 3: Output JSON schema
    if schema_name:
        schema_path = SCHEMAS_DIR / schema_name
        if not schema_path.exists():
            msg = f"Schema not found: {schema_path}"
            raise FileNotFoundError(msg)
        schema_text = schema_path.read_text().strip()
        # Validate it's valid JSON
        json.loads(schema_text)
        parts.append(
            "## Output JSON Schema\n\n"
            "Your output MUST conform to this JSON Schema. "
            "This is the canonical specification — if anything in the prompt "
            "above conflicts with this schema, the schema wins.\n\n"
            f"```json\n{schema_text}\n```"
        )

    return "\n\n---\n\n".join(parts)


def compile_standalone() -> str:
    """Compile the standalone single-file prompt (no schemas).

    This is the copy-paste version for any AI interface. It includes
    the common guidelines and all sub-agent workflow steps as a single
    document that the AI can follow end-to-end.
    """
    parts: list[str] = []

    # Common guidelines
    if GUIDELINES_PATH.exists():
        parts.append(GUIDELINES_PATH.read_text().strip())

    # All sub-agent prompts (in workflow order)
    workflow_order = [
        "clarified-input.md",
        "hypotheses.md",
        "search-plans.md",
        "search-results.md",
        "scorecards.md",
        "evidence-packets.md",
        "synthesis.md",
        "self-audit.md",
        "reports.md",
    ]

    for prompt_name in workflow_order:
        prompt_path = PROMPTS_DIR / "sub-agents" / prompt_name
        if prompt_path.exists():
            parts.append(prompt_path.read_text().strip())

    return "\n\n---\n\n".join(parts)


def main() -> None:
    """Compile all prompts."""
    SKILL_COMPILED_DIR.mkdir(parents=True, exist_ok=True)
    STANDALONE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Per-sub-agent compiled prompts for the skill path.
    print("Compiling per-sub-agent prompts (with schemas):")
    compiled_count = 0
    for prompt_name, schema_name in PROMPT_SCHEMA_MAP.items():
        compiled = compile_prompt(prompt_name, schema_name)
        (SKILL_COMPILED_DIR / prompt_name).write_text(compiled + "\n")
        compiled_count += 1
        print(f"  {prompt_name} ({len(compiled):,} chars)")

    # Standalone unified methodology (no schemas).
    print("\nCompiling standalone prompt (no schemas):")
    standalone = compile_standalone()
    STANDALONE_PATH.write_text(standalone + "\n")
    print(f"  research.md ({len(standalone):,} chars)")

    print(f"\n{compiled_count} sub-agent prompts compiled to {SKILL_COMPILED_DIR}")
    print(f"Standalone prompt compiled to {STANDALONE_PATH}")


if __name__ == "__main__":
    main()
