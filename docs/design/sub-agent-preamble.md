# Sub-Agent Standard Preamble

Every sub-agent prompt begins with this standard preamble. It handles
input parsing, validation, and error reporting before the task-specific
instructions execute.

## The preamble

```markdown
## Input Handling

You accept input in two forms:

1. **JSON (preferred)**: If the input is valid JSON matching your input
   schema, validate it and proceed immediately to your task. This is the
   efficient path — zero tokens spent on parsing.

2. **Text (fallback)**: If the input is not JSON, attempt to derive the
   required input JSON from the text provided. Map the text content to
   your input schema fields as accurately as possible.
   - If you can construct a valid input JSON: validate it and proceed.
   - If you cannot construct a valid input JSON (missing required
     fields, ambiguous content, insufficient information): return a
     structured error. Do NOT guess or fabricate missing fields.

## Validation

Before executing your task, validate that the input JSON contains all
required fields per your input schema. If validation fails, return:

```json
{
  "error": true,
  "agent": "{your-agent-name}",
  "message": "{what is missing or invalid}",
  "required_fields": ["{list of required fields}"],
  "received_fields": ["{list of fields actually present}"]
}
```

Do NOT proceed with partial input. Do NOT ask clarifying questions.
Return the error and let the caller decide what to do.

## Output

Always return JSON matching your output schema. Never return markdown,
prose, or formatted text. The caller renders the output — your job is
to return structured data.

If your task completes successfully, return the output JSON.
If your task fails (e.g., no evidence found, source unreachable),
return a structured result with appropriate fields indicating the
failure — not a JSON error object. Failures within the task are valid
results, not errors.

Errors (the JSON above) are reserved for input validation failures
and system-level problems — situations where the task cannot even
begin.
```

## How it's used

Each sub-agent prompt is structured as:

```markdown
# {Agent Name}

{Standard preamble — copied or referenced}

## Input Schema

{JSON schema definition for this agent's required input}

## Output Schema

{JSON schema definition for this agent's output}

## Task

{The actual instructions for what this agent does}
```

The preamble is identical across all sub-agents. The schemas and task
instructions are unique to each.

## Design notes

- The preamble makes every sub-agent usable both interactively (human
  types text) and programmatically (coordinator sends JSON). Same
  prompt, same agent, two input modes.
- The error format is standardized so the coordinator can handle
  errors uniformly regardless of which sub-agent produced them.
- The distinction between errors (can't start) and failures (task
  ran but found nothing) is important — a search that returns no
  results is a valid finding, not an error.
