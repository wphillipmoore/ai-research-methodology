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
/research run [file=<path>] [output=<dir>] [id=<id>] [n=<count>] [confirm=yes|no]
```

| Parameter | Required | Description | Default | Example |
|-----------|----------|-------------|---------|---------|
| `file` | No | Path to a markdown file containing claims, queries, and/or axioms. | Ask interactively | `file=claims.md` |
| `output` | No | Output directory. | Ask interactively | `output=research/ai-trust` |
| `id` | No | Research instance ID. Only needed if your output format uses it. | Auto-generated | `id=R0005` |
| `n` | No | Number of independent runs. Each run is blind to the others. After all complete, a synthesis step produces aggregate results with consistency metrics. | `3` | `n=1` |
| `confirm` | No | `yes`: confirm before running. `no`: batch mode, just run. | `yes` | `confirm=no` |

Any `key=value` parameter not listed above is ignored. If an unrecognized
parameter is provided, do not ask about it — silently ignore it.

**Examples:**

```
/research run file=claims.md output=research/ai-trust
/research run file=claims.md output=research/ai-trust n=1
/research run
```

### rerun — Re-execute previous research

```
/research rerun <path-to-research-directory> [n=<count>] [confirm=yes|no]
```

Re-executes a previous research run using the saved input spec. The input
spec file (`research-input.md`) is saved in the research instance directory
during the original run. The rerun creates a new timestamped directory
alongside the existing one(s). The `n` parameter works the same as for
`run` (default: 3).

**CRITICAL: Isolation rule.** The rerun MUST be executed with NO knowledge
of prior run results. The skill reads ONLY `research-input.md` from the
research directory. It MUST NOT read, reference, or pass to the subagent
ANY files from existing date directories (prior run results, assessments,
evidence, or any other output). The subagent MUST NOT be given the path
to prior runs. This is essential for reproducibility — reading prior results
would bias the new research through anchoring and confirmation effects.

**Difference report.** After the rerun completes (and ONLY after — the
isolation rule must not be violated), the skill automatically generates a
difference report comparing the new run against the most recent prior run.

The diff is produced by a SEPARATE step that reads both runs AFTER the
rerun subagent has finished. This preserves isolation — the rerun agent
never sees prior results. Only the post-run comparison step reads both.

The diff report is saved in `{research-directory}/diffs/` as
`{prior-date}_vs_{new-date}.md`. If no prior run exists (first run),
no diff is generated.

The diff report contains:

1. **Per-claim/query comparison**: for each entity that exists in both
   runs, compare:
   - Probability/confidence shift (old → new rating)
   - Verdict change (which hypothesis prevailed)
   - New sources found (in new run but not prior)
   - Sources dropped (in prior but not new run)
   - Evidence direction shift

2. **Collection-level comparison**:
   - Overall distribution shift (how many claims moved between ratings)
   - New cross-cutting patterns
   - Gap changes (gaps closed, new gaps identified)
   - Source overlap (shared vs unique sources between runs)

3. **Article impact summary**:
   - Claims that strengthened (no action needed)
   - Claims that weakened (may need softening)
   - Claims that flipped (correction needed)
   - New information that should be incorporated

### extract — Extract verifiable claims from a document

```
/research extract <url-or-path> [output=<dir>]
```

Reads a document and produces a numbered list of verifiable factual claims
as a markdown file suitable for input to `/research run`.

| Parameter | Required | Description | Default | Example |
|-----------|----------|-------------|---------|---------|
| `<url-or-path>` | Yes | URL or local file path | — | `articles/A0005/drafts/draft-v1.md` |
| `output` | No | Directory to write the claims file | Local path: dirname of input. URL: must specify. | `output=research/` |

**Standard output file**: `extracted-claims.md` (placed in the output
directory). This name is fixed — do not ask the user for a filename.

**Extraction rules:**

1. **Read the document body only.** Do NOT read the References, Bibliography,
   Sources, or Works Cited section. The references are a cheat sheet — claims
   must be extracted as they appear in the prose. If the prose names a study,
   institution, or statistic, that's fair game. If the only way to identify
   the source is to read the reference list, skip it.

2. **Extract verifiable factual claims only.** A claim is a statement that
   can be checked against evidence. Skip:
   - Opinions and editorial framing ("I believe...", "This is concerning...")
   - Rhetorical questions
   - Definitions that are being stipulated, not asserted as fact
   - Structural statements about the article itself

3. **Include named entities and categorizations.** Product names, tool names,
   framework names, and categorization claims ("X is a type of Y") are
   verifiable and MUST be extracted. Do not skip "simple" assertions.

4. **If the input is a URL**, fetch the page content and extract the article
   body. Strip navigation, headers, footers, ads, sidebars, and other HTML
   chrome. If the page structure makes it unclear where the article body is,
   err on the side of including too much rather than too little.

5. **Present the claims to the user for review** before saving (unless
   `confirm=no` — see below). The user may add, remove, or modify claims.
   The extraction is a starting point, not a final product.

**Output format** (`extracted-claims.md`):

```markdown
# Claims extracted from {document name}

Source: {url or path}
Extracted: {date}

## Claims

1. {first verifiable claim as it appears in the prose}
2. {second claim}
...

## Axioms

{empty by default — user may add axioms before running verification}

## Queries

{empty by default — user may add queries before running verification}
```

### fact-check — Extract and verify in one step

```
/research fact-check <url-or-path> [output=<dir>] [confirm=yes|no]
```

Extracts claims from a document and immediately runs verification on them.

| Parameter | Required | Description | Default | Example |
|-----------|----------|-------------|---------|---------|
| `<url-or-path>` | Yes | URL or local file path | — | `articles/A0005/drafts/draft-v1.md` |
| `output` | No | Directory for all output (claims + research) | Local path: dirname of input. URL: must specify. | `output=research/A0005-claims/` |
| `confirm` | No | `yes`: present claims for review before verifying. `no`: skip confirmation, just run. | `yes` | `confirm=no` |

**Workflow:**

1. Check if `{output}/extracted-claims.md` exists AND is newer than the
   source document. If yes, skip extraction and use the existing claims file.
   If no, run extraction.
2. **Pre-fact-check gate** (reference audit): Read the document's References
   section. For each reference:
   - If it has research evidence links (R/Q, SRC) → pass (already scored)
   - If it is clearly informational (link to an organization homepage,
     Wikipedia, regulatory text with no associated claim) → pass
   - If it supports a factual claim but has no scorecard → **flag it**
   Report any flagged references to the user. If flags exist and
   `confirm=yes`: ask the user to resolve them before proceeding. If
   `confirm=no`: report the flags as warnings but continue.
3. If `confirm=yes` (default): present the extracted claims to the user for
   review. The user may add, remove, or modify claims before proceeding.
4. If `confirm=no`: skip review, treat extracted claims as final.
5. Pass the claims to `run` for verification. The full research output is
   written to the output directory alongside the claims file.

**`confirm=no` (batch mode):**
- No confirmation prompt before extraction or verification
- No clarification of input
- Treat all input as final — the user specified everything on the command line
- Just run
- Still save research-input.md, snapshots, and all output artifacts

This is a convenience command. It does nothing that `extract` followed by
`run` doesn't do — it chains them and adds smart caching of the extraction.

**Future**: Support for directory input (collection of files) to fact-check
documentation trees is planned but not yet implemented.

## Workflow (for `run` and `rerun`)

### Step 1: Gather input

Parse any `key=value` parameters from the invocation. For any parameter NOT
provided on the command line, ask the user interactively. For parameters
that WERE provided, use them directly — do not re-ask.

1. **Input** (`file=` parameter) — either:
   - A file path was provided: read it and extract the claims, queries,
     axioms, and any candidate evidence attached to claims
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
Claims: 5 (2 with candidate evidence)
Queries: 2
  C001: First claim text...
  C002: Second claim text... [+1 candidate evidence URL]
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

### Step 3: Create run group directory

Create `{output_directory}/{YYYY-MM-DD-HHMM}/` using the current date and
time (24-hour format, no seconds). This is the **run group** directory that
will contain n independent runs plus synthesis files.

Within the run group, create `run-1/`, `run-2/`, ... `run-{n}/` subdirectories.

### Step 4: Save methodology snapshot

Copy the files used to drive the research into the run group directory
(not into each run subdirectory — one copy shared across all runs):

- `prompt-snapshot.md` — copy of the research methodology prompt
- `output-format-snapshot.md` — copy of the output format specification

This creates a permanent record of exactly what instructions were in effect.

### Step 5: Execute n independent research runs

Determine the output format specification — check in this order:
1. Look for a project-local custom output format at
   `skills/research/output-formats/custom.md` in the current working
   directory. If this file exists, use it.
2. Otherwise, use the plugin's default:
   `skills/research/output-formats/default.md`.

For each of the n runs, launch an independent subagent with:
- The research methodology prompt
- The output format specification
- The input (axioms, claims, queries)
- The output directory (the specific `run-{N}/` subdirectory)
- The research ID and run date

**Isolation rule**: Each run is completely blind to the others. No run
may read, reference, or be influenced by any other run's output. This
is the same isolation principle as reruns — each run must be independent
to provide a valid signal about reproducibility.

**Parallelism**: For n<=5, launch runs in parallel where possible. For
larger n, the agent may batch runs to manage resources.

Each subagent:
1. Reads the methodology prompt and output format specification
2. For each claim/query in the input, investigates it following the methodology
3. Writes all output files to its `run-{N}/` directory
4. After all individual investigations, produces the run-level index.md with
   collection analysis

### Step 5b: Synthesize across n runs

**This step runs ONLY after ALL n runs have completed.** It reads the
output from every `run-{N}/` directory and produces group-level files in
the run group directory.

Produce these files:

1. **synthesis.md** — aggregate result derived from n independent runs:
   - For each claim/query: consensus verdict, divergences, union of sources
   - Overall assessment that integrates findings from all runs
   - Where runs agree: state with increased confidence
   - Where runs disagree: note the divergence and classify the root cause

2. **consistency.md** — similarity metrics across the n runs:
   - Source overlap (% shared between each pair, sources found in all/most/one)
   - Verdict agreement (did all runs support the same hypothesis?)
   - Scoring consistency (same source scored the same way?)
   - Overall similarity score
   - Diagnostic: if <50% overlap, flag as "query may be too ambiguous"

3. **reading-list.md** — consolidated reading list across all n runs,
   deduplicated, with provenance (which runs found each source)

4. **resources.md** — combined resource usage across all runs

### Step 6: Report completion

When synthesis finishes, report to the user:

```
## Research Complete

- **Runs**: {n} independent runs
- **Items investigated**: {count} claims/queries
- **Output**: {path to run group directory}
- **Duration**: {wall clock time}
- **Consistency**: {overall similarity score}%

### Verdict Summary (from synthesis)

| Probability | Count | Items |
|-------------|-------|-------|
| Almost certain | {n} | {list} |
| Very likely | {n} | {list} |
| Likely | {n} | {list} |
| Unlikely | {n} | {list} |

### Run Consistency

| Metric | Value |
|--------|-------|
| Source overlap (avg pairwise) | {n}% |
| Verdict agreement | {all agree / N of M agree} |
| Scoring consistency | {consistent / N divergences} |

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

The output format can be customized without modifying the plugin. Create a
file at `skills/research/output-formats/custom.md` in your project directory.
If this file exists, the skill uses it instead of the default format.

This follows the project-local override pattern: the plugin ships with a
default, your project can override it by placing a file at the conventional
path. Plugin updates will not affect your custom file because it lives in
your project, not in the plugin cache.

The research methodology prompt (`prompts/research.md`) defines the research
process and is independent of the output format. You can change how results
are presented without changing how research is conducted.

## Future extensions

- **report** mode (topic exploration with facets)
- Sub-agent architecture with structured output and deterministic rendering
