#!/usr/bin/env python3
"""Compile sub-agent prompts by concatenating guidelines + prompt + schema.

Produces self-contained prompt files in prompts/compiled/ for use by the
Claude Code plugin. Each compiled prompt includes the common guidelines,
the sub-agent prompt, and the output JSON schema — everything the model
needs in a single file.

Usage:
    python scripts/compile-prompts.py

The source files are in src/diogenes/prompts/ and src/diogenes/schemas/.
The compiled output goes to prompts/compiled/ (used by the plugin).
"""

from __future__ import annotations

import json
from pathlib import Path

# Source locations (inside the package)
PACKAGE_DIR = Path(__file__).parent.parent / "src" / "diogenes"
PROMPTS_DIR = PACKAGE_DIR / "prompts"
SCHEMAS_DIR = PACKAGE_DIR / "schemas"
GUIDELINES_PATH = PROMPTS_DIR / "common-guidelines.md"

# Output location (for plugin use)
COMPILED_DIR = Path(__file__).parent.parent / "prompts" / "compiled"

# Mapping: sub-agent prompt filename -> output schema filename
# Sub-agents that don't have an output schema (or don't need one compiled)
# are omitted.
PROMPT_SCHEMA_MAP: dict[str, str | None] = {
    "input-clarifier.md": "clarified-input.schema.json",
    "hypothesis-generator.md": "hypotheses.schema.json",
    "search-designer.md": "search-plan.schema.json",
    "relevance-scorer.md": "relevance-scores.schema.json",
    "result-selector.md": "search-results.schema.json",
    "search-executor.md": "search-results.schema.json",
    "source-scorer.md": "source-scorecards.schema.json",
    "evidence-synthesizer.md": "synthesis.schema.json",
    "self-auditor.md": "self-audit.schema.json",
    "report-assembler.md": "report.schema.json",
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
        "input-clarifier.md",
        "hypothesis-generator.md",
        "search-designer.md",
        "relevance-scorer.md",
        "source-scorer.md",
        "evidence-synthesizer.md",
        "self-auditor.md",
        "report-assembler.md",
    ]

    for prompt_name in workflow_order:
        prompt_path = PROMPTS_DIR / "sub-agents" / prompt_name
        if prompt_path.exists():
            parts.append(prompt_path.read_text().strip())

    return "\n\n---\n\n".join(parts)


def main() -> None:
    """Compile all prompts."""
    COMPILED_DIR.mkdir(parents=True, exist_ok=True)

    # Per-sub-agent compiled prompts (guidelines + prompt + schema)
    print("Compiling per-sub-agent prompts (with schemas):")
    compiled_count = 0
    for prompt_name, schema_name in PROMPT_SCHEMA_MAP.items():
        compiled = compile_prompt(prompt_name, schema_name)
        output_path = COMPILED_DIR / prompt_name
        output_path.write_text(compiled + "\n")
        compiled_count += 1
        print(f"  {prompt_name} ({len(compiled):,} chars)")

    # Standalone single-file prompt (no schemas)
    print("\nCompiling standalone prompt (no schemas):")
    standalone = compile_standalone()
    standalone_path = COMPILED_DIR.parent.parent / "ai-research-methodology" / "standalone" / "research.md"
    standalone_path.parent.mkdir(parents=True, exist_ok=True)
    standalone_path.write_text(standalone + "\n")
    print(f"  research.md ({len(standalone):,} chars)")

    print(f"\n{compiled_count} sub-agent prompts compiled to {COMPILED_DIR}")
    print(f"Standalone prompt compiled to {standalone_path}")


if __name__ == "__main__":
    main()
