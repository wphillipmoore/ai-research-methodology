# JSON Schemas

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

| Schema | Purpose |
|--------|---------|
| `research-input.schema.json` | Input to the entire research workflow |
| `research-input.example.json` | Example valid input |

Additional schemas will be added for each sub-agent's input and output
as they are defined.

## Design principles

1. **JSON is the canonical data format.** Markdown is a rendering.
2. **Every sub-agent: JSON in, JSON out.** Validate before processing.
3. **Schemas are the contract.** If it validates, the sub-agent can
   process it. If it doesn't, return a structured error.
4. **Forward-compatible.** Schemas use `additionalProperties: false`
   to prevent undeclared fields. New fields require a schema update.
5. **Each schema maps to a future database table.** Design as if it's
   a data model, not a throwaway format.
