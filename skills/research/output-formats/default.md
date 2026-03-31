# Default Output Format

## Overview

This output format produces clean, portable markdown that renders well in any
markdown viewer — GitHub, VS Code, terminals, static site generators. No
framework-specific syntax. No custom CSS classes. Just markdown.

The output is organized as a directory tree. Each claim or query gets its own
directory containing the full evidence archive.

## Directory Structure

```
{output-directory}/
├── research-input.md                    # Input spec (enables reruns)
├── {YYYY-MM-DD}/                        # Run directory (date-stamped)
│   ├── index.md                         # Run summary with all results
│   ├── prompt-snapshot.md               # Copy of the methodology prompt
│   ├── output-format-snapshot.md        # Copy of the output format spec (if separate)
│   ├── {entity-slug}/                   # One directory per claim/query
│   │   ├── assessment.md                # Full analytical product
│   │   ├── sources.md                   # All source scorecards
│   │   ├── searches.md                  # All search logs
│   │   └── self-audit.md               # Process + source-back audit
```

**Methodology snapshots**: Before beginning research, save the instructions
you are operating under:

- If the methodology prompt and output format were loaded as **separate files**,
  copy each into the run directory: `prompt-snapshot.md` and
  `output-format-snapshot.md`. Two files.
- If the instructions were provided as a **single pasted document**, save it as
  `prompt-snapshot.md`. One file.

This creates a permanent record of what produced these results. The number of
snapshot files also indicates how the research was invoked (plugin vs paste).

## File Formats

### research-input.md

```markdown
# Research Input

**Mode**: claim | query
**Research ID**: {id}
**Created**: {date}

## Claims / Queries

1. {first claim or query text}
2. {second claim or query text}
...
```

### index.md (Run Summary)

```markdown
# {Research ID} — {date}

**Mode**: claim | query
**Claims/Queries**: {count}
**Model**: {model name}

## Results

### {Entity ID} — {short title}

**Verdict/Answer**: {one-line summary}

**Probability**: {band} ({range}) — or N/A for query mode without
probability ratings

**Hypotheses**:
- **H1**: {statement} — {Supported | Eliminated | Inconclusive}
- **H2**: {statement} — {status}
- **H3**: {statement} — {status}

**Sources**: {count} | **Searches**: {count}

[Full analysis]({entity-slug}/assessment.md)

---

{Repeat for each claim/query}

## Collection Analysis

### Cross-Cutting Patterns

{Narrative identifying themes that span multiple claims/queries}

### Collection Statistics

| Metric | Value |
|--------|-------|
| Claims/Queries investigated | {n} |
| Sources scored | {n} |
| Evidence extracts | {n} |
| Results dispositioned | {selected} selected + {rejected} rejected |

### Source Independence

{Assessment of whether sources are genuinely independent or share
common upstream origins}

### Collection Gaps

| Gap | Impact |
|-----|--------|
| {what's missing} | {how it affects conclusions} |

## Resources

| Metric | Value |
|--------|-------|
| Duration | {wall clock time} |
| Searches | {count} |
| Sources scored | {count} |
| Files produced | {count} |
```

### assessment.md (Per-Entity)

```markdown
# {Entity ID} — {short title}

**Research**: {Research ID}
**Run**: {date}
**Mode**: claim | query

## BLUF

{1-3 sentence bottom-line assessment}

## Probability / Answer

**Rating**: {band} ({range})
**Confidence**: {High | Medium | Low}
**Rationale**: {why this confidence level}

## Reasoning Chain

1. {Evidence summary with source reference.}
   [Source: {SRC ID}, {reliability}, {relevance}]
2. {Next step in reasoning.}
   [Source: {SRC ID}, {reliability}, {relevance}]
3. JUDGMENT: {Analytical conclusion drawn from evidence above.}

## Hypotheses

### H1: {statement}
**Status**: {Supported | Eliminated | Inconclusive}
**Evidence for**: {summary}
**Evidence against**: {summary}

### H2: {statement}
**Status**: {status}
**Evidence for**: {summary}
**Evidence against**: {summary}

### H3: {statement}
**Status**: {status}
**Evidence for**: {summary}
**Evidence against**: {summary}

## Evidence Summary

| Source | Description | Reliability | Relevance | Key Finding |
|--------|-------------|-------------|-----------|-------------|
| {SRC01} | {name} | {rating} | {rating} | {finding} |

## Collection Synthesis

| Dimension | Assessment |
|-----------|------------|
| Evidence quality | {assessment} |
| Source agreement | {assessment} |
| Source independence | {assessment} |
| Outliers | {assessment} |

{Narrative synthesis}

## Gaps

| Missing Evidence | Impact on Assessment |
|-----------------|---------------------|
| {what's missing} | {how it affects the conclusion} |

## Researcher Bias Check

**Declared biases**: {any biases identified}
**Influence assessment**: {how they may have affected results}

## Revisit Triggers

Specific conditions that would warrant re-running this research:

| Trigger | Type | Check |
|---------|------|-------|
| {specific event, study, update, or deadline} | {time / event / data / policy} | {how to check if this trigger has occurred} |

```

### sources.md (Per-Entity)

All source scorecards in one file.

```markdown
# {Entity ID} — Sources

## SRC01: {source name}

**URL**: <{url}>
**Type**: {peer-reviewed | government | industry | media | blog | other}
**Accessed**: {date}

**Reliability**: {High | Medium | Low} — {rationale}
**Relevance**: {High | Medium | Low} — {rationale}

### Bias Assessment

| Domain | Rating | Rationale |
|--------|--------|-----------|
| Missing data | {rating} | {rationale} |
| Measurement | {rating} | {rationale} |
| Selective reporting | {rating} | {rationale} |
| Randomization | {N/A or rating} | {rationale} |
| Protocol deviation | {N/A or rating} | {rationale} |
| Conflict of interest | {rating} | {rationale} |

### Key Evidence

**E01**: {extracted evidence with context}

---

## SRC02: {source name}

{Same format, repeat for each source}
```

### searches.md (Per-Entity)

All search logs in one file.

```markdown
# {Entity ID} — Searches

## S01: {search description}

**Query**: {exact search terms}
**Source**: {where searched — web, academic database, etc.}
**Date**: {date}
**Results returned**: {count}

### Selected

| # | Title | URL | Rationale |
|---|-------|-----|-----------|
| R01 | {title} | <{url}> | {why selected} |
| R02 | {title} | <{url}> | {why selected} |

### Rejected

| # | Title | URL | Rationale |
|---|-------|-----|-----------|
| R03 | {title} | <{url}> | {why rejected} |

---

## S02: {search description}

{Same format, repeat for each search}
```

### self-audit.md (Per-Entity)

```markdown
# {Entity ID} — Self-Audit

## Domain 1: Eligibility Criteria

**Rating**: {Low risk | Some concerns | High risk}
{Assessment of whether criteria were defined before searching}

## Domain 2: Search Comprehensiveness

**Rating**: {rating}
{Assessment of search breadth and depth}

## Domain 3: Evaluation Consistency

**Rating**: {rating}
{Assessment of whether all sources were scored equally}

## Domain 4: Synthesis Fairness

**Rating**: {rating}
{Assessment of whether evidence was synthesized honestly}

## Domain 5: Source-Back Verification

**Rating**: {rating}

For each source cited in the assessment, verify the assessment accurately
represents what the source says.

| Source | Claim in Assessment | Source Actually Says | Match? |
|--------|-------------------|---------------------|--------|
| {SRC01} | {what assessment claims} | {what source says} | {Yes | Discrepancy} |

**Discrepancies found**: {count}
**Corrections applied**: {list, or "None needed"}
**Unresolved flags**: {list, or "None"}

## Overall Assessment

**Overall risk of bias**: {rating}
{Narrative summary}

## Researcher Bias Check

{Assessment of whether declared biases influenced the research}
```

## Rules

1. **Every URL must be a clickable link.** Use `<https://example.com>` or
   `[text](url)`. No bare URLs.

2. **Every source and evidence reference in narrative text should identify
   the source clearly** — by name, SRC ID, or both.

3. **The assessment reasoning chain must be traceable.** A reader should be
   able to follow the logic from evidence through synthesis to conclusion.

4. **Absences are findings.** If a search returned no results, document it.
   If expected evidence wasn't found, say so and explain what it means.

5. **The self-audit is mandatory.** All five domains must be assessed, even
   if the assessment is "no concerns."

6. **The sections above are the minimum, not the maximum.** Once all required
   sections are present and complete, you are encouraged to add additional
   analysis that emerged during the investigation. Comparison tables,
   unexpected patterns, connections between sources, alternative framings,
   contextual observations, or anything else that would help the reader
   understand the evidence landscape — include it. The required structure
   ensures consistency and auditability. Anything beyond that structure is
   a bonus that adds value. Do not suppress interesting findings just because
   the spec doesn't have a section for them. Add a "## Notes" or
   "## Additional Observations" section at the end of the assessment if
   needed.

---

## Output Delivery

Choose the appropriate delivery mode based on your environment:

### Mode A: File System Access (Claude Code, plugin, or any environment with write access)

Write the directory structure directly to the specified output location. Use
the directory layout and file formats defined above. Relative markdown links
between files (e.g., `[assessment](entity-slug/assessment.md)`) will work in
VS Code, GitHub, Obsidian, and most markdown viewers.

### Mode B: No File System Access (web chat, API, or any environment without write access)

Produce a single self-contained HTML file that includes all research output
with internal navigation. The HTML file must:

1. **Contain all content** — the run summary, every entity assessment, all
   source scorecards, all search logs, and all self-audits. Nothing omitted.

2. **Use anchor-based navigation** — a table of contents at the top with
   clickable links to each section. Each entity, source, and search gets its
   own anchor. The reader can click through the results the same way they
   would navigate the directory structure.

3. **Be self-contained** — no external CSS, no JavaScript dependencies, no
   images to load. Just HTML with inline styles. It must render correctly
   when opened from a local file in any browser.

4. **Include basic styling** — readable typography, clear section separation,
   table formatting, and visual distinction between headings. Keep it clean
   and functional, not decorative.

5. **Display the results in the conversation first** — present the full
   research output as text in the conversation so the user can read through
   it immediately. Then offer the HTML file as a downloadable artifact at
   the end: "Download the complete research archive as a single HTML file."

**How to detect which mode to use**: If you can write files (you have access
to tools like Write, Bash, or file creation), use Mode A. If you cannot
write files, use Mode B.
