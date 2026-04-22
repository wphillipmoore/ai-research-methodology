# JSON Schemas

**Status:** Locked (baseline) — the schemas listed below are contracts.
Breaking changes require a spec update and a bump of the affected schema
file.
**Last verified:** 2026-04-22 (canonical packaged schemas live under
`src/diogenes/schemas/`; this directory retains reference copies).
**Sources:** Relocated from `docs/design/schemas/` as part of the
retroactive spec extraction for issue #129. The JSON-first architecture
and the "Python validates, model proposes" contract are formalized in
[`../output-contract.md`](../output-contract.md); the surrounding
pipeline is specified in
[`../workflow-architecture.md`](../workflow-architecture.md).

JSON Schema definitions for all data interchange in the research
methodology workflow. Each sub-agent has an input schema and an output
schema. The Python coordinator validates all data against these schemas
before passing it to the next step.

## Validation in Python

```python
import json
import jsonschema

# Load schema
with open("research-input.schema.json") as f:
    schema = json.load(f)

# Load input
with open("my-research-input.json") as f:
    data = json.load(f)

# Validate
try:
    jsonschema.validate(instance=data, schema=schema)
    print("Valid")
except jsonschema.ValidationError as e:
    print(f"Invalid: {e.message}")
    print(f"Path: {'.'.join(str(p) for p in e.absolute_path)}")
```

The `jsonschema` library (install: `pip install jsonschema`) implements
JSON Schema Draft 2020-12. It provides:
- Type checking
- Required field validation
- Pattern matching (regex)
- Enum constraints
- Format validation (URI, date, etc.)
- Nested object and array validation
- Custom error messages with path to the failing field

## Schema files

Canonical location: `src/diogenes/schemas/` (packaged with `pip install
diogenes`). The schemas in this directory are retained for reference but
the packaged versions are the single source of truth.

| Schema | Purpose |
|--------|---------|
| `research-input.schema.json` | Input to the entire research workflow |
| `research-input.example.json` | Example valid input |
| `clarified-input.schema.json` | Step 1 output (input-clarifier) |
| `hypotheses.schema.json` | Step 2 output (hypothesis-generator) |

## Design principles

1. **JSON is the canonical data format.** Markdown is a rendering.
2. **Every sub-agent: JSON in, JSON out.** Validate before processing.
3. **Schemas are the contract.** If it validates, the sub-agent can
   process it. If it doesn't, return a structured error.
4. **Forward-compatible.** Schemas use `additionalProperties: false`
   to prevent undeclared fields. New fields require a schema update.
5. **Each schema maps to a future database table.** Design as if it's
   a data model, not a throwaway format.

## Output rendering

The Python renderer produces two output formats from the same JSON:

1. **Drill-down hierarchy** — directory structure with linked markdown
   files for navigating the data interactively. This is the primary
   output for understanding the research. Each level links to the
   next level of detail.

2. **Flat file** — a single consolidated document suitable for sharing,
   reading linearly, or publishing as an article appendix. The flat
   file includes links back into the drill-down hierarchy so readers
   who need more detail can jump to the navigation view.

Both are rendered from the same JSON by a default Python renderer with
configurable parameters (no custom prompt needed). The renderer replaces
the current custom output format specification entirely.
