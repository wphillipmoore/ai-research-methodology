---
name: research
description: Run structured research — claim verification or query answering — with full evidence archive output.
user_invocable: true
---

# Research

## Overview

Run a structured research investigation. Produces a complete evidence archive
with searches, sources, scorecards, evidence extracts, hypotheses, ACH
matrices, and self-audits.

Two modes:

- **claim** — verify a list of assertions (true/false/partially true)
- **query** — answer a list of questions (hypotheses ranked by evidence)

## Invocation

### New research

```
/research claim [file=<path>] [id=<research-id>] [output=<directory>]
/research query [file=<path>] [id=<research-id>] [output=<directory>]
```

The mode (claim or query) is required. All other parameters are optional —
if provided on the command line, skip the interactive prompt for that
parameter. If omitted, ask interactively.

| Parameter | Description | Example |
|-----------|-------------|---------|
| `file` | Path to a markdown file containing the claims or queries | `file=claims.md` |
| `id` | Research instance ID | `id=R0005` |
| `output` | Output directory (run directory created inside this) | `output=research/R0005-topic` |

**Example — fully specified (no interactive prompts):**

```
/research claim file=claims.md id=R0005 output=research/R0005-ai-trust
```

**Example — minimal (everything asked interactively):**

```
/research claim
```

### Re-run existing research

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

| Parameter | Description | Example |
|-----------|-------------|---------|
| `<path>` | Path to the research instance directory | `research/R0005-ai-trust` |

## Workflow

### Step 1: Gather input

Parse any `key=value` parameters from the invocation. For any parameter NOT
provided on the command line, ask the user interactively. For parameters
that WERE provided, use them directly — do not re-ask.

1. **Claims or queries** (`file=` parameter) — either:
   - A file path was provided: read it and extract the list items
   - No file provided: ask the user to type them or provide a path

2. **Research ID** (`id=` parameter) — e.g., `R0005`. If not provided and
   the user doesn't have one, use `RXXXX` as a placeholder.

3. **Output directory** (`output=` parameter) — where to write the results.
   If not provided, ask the user. If the user doesn't have one, suggest
   `research/{Research ID}/` as a starting point.

### Step 2: Confirm and save input spec

Present a summary of what will be researched:

```
Mode: claim
Research ID: R0005
Output directory: research/R0005-ai-trust/
Run date: 2026-03-30
Claims (5):
  C001: First claim text...
  C002: Second claim text...
  ...
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

- The research methodology prompt for the mode:
  - Claim: `skills/research/prompts/claim.md`
  - Query: `skills/research/prompts/query.md`
- The output format specification:
  - `skills/research/output-formats/default.md`
- The list of claims or queries
- The output directory (the run directory created in Step 3)
- The research ID and run date

The subagent must read BOTH the methodology prompt AND the output format spec
before beginning work. The methodology prompt defines HOW to investigate
(search strategy, evidence evaluation, ACH analysis, self-audit). The output
format spec defines WHAT to produce (directory structure, file contents).

The subagent then:

1. Reads the methodology prompt and output format specification
2. For each claim/query in the list, investigates it following the methodology
3. Writes all output files to the run directory following the output format spec
4. After all individual investigations, produces the run-level index.md with
   collection analysis

### Step 5: Report completion

When the subagent finishes, report to the user:

```
## Research Complete

- **Claims/Queries investigated**: {n}
- **Files produced**: {n}
- **Output**: {path to run directory}
- **Duration**: {wall clock time}

### Verdict Summary

| Probability | Count | Claims |
|-------------|-------|--------|
| Almost certain | {n} | {C001, C002, ...} |
| Very likely | {n} | {list} |
| Likely | {n} | {list} |
| Unlikely | {n} | {list} |

### Flags for Attention

| Claim | Issue |
|-------|-------|
| {C009} | {description of issue needing correction} |
```

## Constraints

- Do not proceed without user confirmation (Step 2)
- Do not modify files outside the output directory
- The output format spec is the source of truth for file structure
- Every search result must be dispositioned (no silent drops)
- Always produce a minimum of 3 hypotheses (both claim and query modes).
  The first three are mandatory: H1 (affirmative/accurate), H2 (negative/
  partially correct), H3 (nuanced/materially wrong). Additional hypotheses
  (H4, H5, ...) may be added when the evidence supports more than three
  distinct explanations.
- **Run isolation**: The subagent MUST NOT read prior run results. On a rerun,
  read ONLY `research-input.md`. Do NOT pass prior run paths to the subagent.
  Prior results bias new research through anchoring and confirmation effects.
- **Claim extraction blindness**: When extracting claims from an article for
  verification, read ONLY the article body. Do NOT read or include the
  References section — it is a cheat sheet that biases the fact-checker.
  Claims should be extracted as they appear in the prose. If the prose names
  a study or institution, that's fair game. If the only way to identify the
  source is to read the reference list, the fact-checker must find it
  independently.

## Customization

The output format can be customized by replacing or supplementing
`output-formats/default.md` with your own specification. The methodology
prompts (`prompts/claim.md` and `prompts/query.md`) define the research
process and are independent of the output format.

## Future extensions

- **extract** command (claim extraction from documents)
- **report** mode (topic exploration with facets)
- Sub-agent architecture with structured output and deterministic rendering
