---
name: research
description: Run structured research — claim verification, query answering, and document fact-checking — with full evidence archive output.
user_invocable: true
---

# Research

## Overview

Run a structured research investigation. Produces a complete evidence archive
with searches, sources, scorecards, evidence extracts, hypotheses, ACH
matrices, and self-audits.

The input can contain claims (assertions to verify), queries (questions to
answer), axioms (facts to assume true), or any combination. The research
methodology determines how to handle each type automatically.

## Commands

### run — Execute new research

```
/research run [file=<path>] [output=<directory>] [id=<research-id>]
```

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `file` | No | Path to a markdown file containing claims, queries, and/or axioms. If omitted, ask interactively. | `file=claims.md` |
| `output` | No | Output directory. If omitted, ask interactively. | `output=research/ai-trust` |
| `id` | No | Research instance ID. Only needed if your output format uses it. Auto-generated or `RXXXX` if omitted. | `id=R0005` |

Any `key=value` parameter not listed above is ignored. If an unrecognized
parameter is provided, do not ask about it — silently ignore it.

**Examples:**

```
/research run file=claims.md output=research/ai-trust
/research run
```

### rerun — Re-execute previous research

```
/research rerun <path-to-research-directory>
```

Re-executes a previous research run using the saved input spec. The input
spec file (`research-input.md`) is saved in the research instance directory
during the original run. The rerun creates a new date directory alongside
the existing one(s).

**CRITICAL: Isolation rule.** The rerun MUST be executed with NO knowledge
of prior run results. The skill reads ONLY `research-input.md` from the
research directory. It MUST NOT read, reference, or pass to the subagent
ANY files from existing date directories (prior run results, assessments,
evidence, or any other output). The subagent MUST NOT be given the path
to prior runs. This is essential for reproducibility — reading prior results
would bias the new research through anchoring and confirmation effects.

### extract — Extract claims from a document (planned)

```
/research extract <url-or-path>
```

Reads a document and produces a list of verifiable claims as a markdown file
suitable for input to `/research run`. Respects the claim extraction blindness
rule: reads only the document body, not references or bibliography sections.

*Not yet implemented.*

### check — Extract and verify in one step (planned)

```
/research check <url-or-path> [output=<directory>]
```

Combines `extract` and `run` into a single command. Extracts claims from the
document, then immediately runs verification on them.

*Not yet implemented.*

## Workflow (for `run` and `rerun`)

### Step 1: Gather input

Parse any `key=value` parameters from the invocation. For any parameter NOT
provided on the command line, ask the user interactively. For parameters
that WERE provided, use them directly — do not re-ask.

1. **Input** (`file=` parameter) — either:
   - A file path was provided: read it and extract the claims, queries,
     and/or axioms
   - No file provided: ask the user to type them or provide a path

2. **Output directory** (`output=` parameter) — where to write the results.
   If not provided, ask the user. If the user doesn't have one, suggest
   `research/{slug}/` as a starting point.

3. **Research ID** (`id=` parameter) — optional. If not provided, auto-generate
   from the output directory slug or use `RXXXX` as a placeholder.

### Step 2: Confirm and save input spec

Present a summary of what will be researched:

```
Research ID: R0005
Output directory: research/ai-trust/
Run date: 2026-03-31
Axioms: 0
Claims: 5
Queries: 2
  C001: First claim text...
  C002: Second claim text...
  ...
  Q001: First query text...
  Q002: Second query text...
```

Ask the user to confirm before proceeding.

After confirmation, save the input specification as
`{output_directory}/research-input.md`. This file enables future re-runs
without re-specifying parameters.

**Guardrail**: Before writing `research-input.md`, check if one already
exists in the output directory. If it does, this is NOT a new research run —
it is an attempted reuse of an existing research directory. **STOP and fail
with an error:**

```
ERROR: {output_directory}/research-input.md already exists.
This directory belongs to an existing research instance.
To re-run this research, use: /research rerun {output_directory}
To start new research, use a different output directory.
```

Do NOT overwrite, merge, or append to an existing `research-input.md`.
Do NOT proceed with execution. This is a hard stop.

### Step 3: Create run directory

Create `{output_directory}/{YYYY-MM-DD}/` using today's date. If the directory
already exists, append a sequence number: `{YYYY-MM-DD}-02/`,
`{YYYY-MM-DD}-03/`, etc.

### Step 4: Execute research

Launch a subagent with the following context:

- The research methodology prompt: `skills/research/prompts/research.md`
- The output format specification — check in this order:
  1. If the user has configured a custom `output_format` path (via plugin
     userConfig), read that file.
  2. Otherwise, use `skills/research/output-formats/default.md`.
- The input (axioms, claims, queries)
- The output directory (the run directory created in Step 3)
- The research ID and run date

The subagent must read BOTH the methodology prompt AND the output format spec
before beginning work. The methodology prompt defines HOW to investigate
(search strategy, evidence evaluation, self-audit). The output format spec
defines WHAT to produce (directory structure, file contents).

The subagent then:

1. Reads the methodology prompt and output format specification
2. For each claim/query in the input, investigates it following the methodology
3. Writes all output files to the run directory following the output format spec
4. After all individual investigations, produces the run-level index.md with
   collection analysis

### Step 5: Report completion

When the subagent finishes, report to the user:

```
## Research Complete

- **Items investigated**: {n}
- **Files produced**: {n}
- **Output**: {path to run directory}
- **Duration**: {wall clock time}

### Verdict Summary

| Probability | Count | Items |
|-------------|-------|-------|
| Almost certain | {n} | {list} |
| Very likely | {n} | {list} |
| Likely | {n} | {list} |
| Unlikely | {n} | {list} |

### Flags for Attention

| Item | Issue |
|------|-------|
| {ID} | {description of issue needing correction} |
```

## Constraints

- Do not proceed without user confirmation (Step 2)
- Do not modify files outside the output directory
- The output format spec is the source of truth for file structure
- Every search result must be dispositioned (no silent drops)
- Always produce a minimum of 3 hypotheses per claim or query.
  The first three are mandatory: H1 (affirmative/accurate), H2 (negative/
  partially correct), H3 (nuanced/materially wrong). Additional hypotheses
  (H4, H5, ...) may be added when the evidence supports more than three
  distinct explanations.
- **Run isolation**: The subagent MUST NOT read prior run results. On a rerun,
  read ONLY `research-input.md`. Do NOT pass prior run paths to the subagent.
  Prior results bias new research through anchoring and confirmation effects.
- **Claim extraction blindness**: When extracting claims from a document
  (via `extract` or `check`), read ONLY the document body. Do NOT read or
  include the References section — it biases the fact-checker. Claims should
  be extracted as they appear in the prose.
- **Unrecognized parameters**: Silently ignore any `key=value` parameter not
  documented above. Do not ask about it.

## Customization

The output format can be customized without modifying the plugin. When
installing the plugin, you are prompted for an optional `output_format`
path. Set this to the path of your own output format markdown file. Leave
it empty to use the default format included with the plugin.

Your custom output format file lives outside the plugin — in your own repo
or wherever you choose. Plugin updates will not affect it.

The research methodology prompt (`prompts/research.md`) defines the research
process and is independent of the output format. You can change how results
are presented without changing how research is conducted.

## Future extensions

- **extract** command (claim extraction from documents)
- **check** command (extract + run in one step)
- **report** mode (topic exploration with facets)
- Sub-agent architecture with structured output and deterministic rendering
