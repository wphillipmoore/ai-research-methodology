# Unified Research Standard -- Query Mode (Question Answering)

Version: 1.0-draft
Date: 2026-03-17
Parent: research-standard-claim.md (Claim Mode: Fact Verification)
License: TBD
Attribution: Derived from the Unified Research Standard. This document defines
only the delta from Claim mode. Layer 1 (Behavioral Constraints), the evidence
engine (Steps 4-6), and Layer 3 (Output Structure) are inherited unchanged.

---

## Relationship to Claim Mode

Query mode shares the same evidence engine and behavioral constraints as
claim mode. The differences are confined to:

1. **Seeding** (Steps 1-3): Questions replace claims. Sub-questions replace
   sub-claims. Candidate answers optionally replace hypotheses.
2. **Analysis** (Steps 7-8): Two paths depending on whether candidate answers
   exist — ACH matrix (same as claim mode) or evidence synthesis (new).
3. **Reporting** (Step 11): Output is an answer with confidence rather than a
   verdict with probability.

Everything else — Layer 1 behavioral constraints, search execution, source
scoring, citation chain analysis, gap identification, self-audit, archival —
is identical and inherited from the parent prompt without modification.

---

## Layer 1: Behavioral Constraints

Inherited from `research-standard-claim.md` without modification. All twelve
rules apply. The only terminology adjustment:

- Where claim mode says "claim," read "question."
- Where claim mode says "researcher's preferred hypothesis," read "researcher's
  expected answer" (if one exists).

---

## Layer 2: Analytical Methodology — Query Mode Overrides

The following steps replace their claim mode counterparts. Steps not listed
here (4, 5, 6, 9, 10, 10b, 12) are inherited unchanged.

### Step 1: Receive and Clarify the Question

[Source: ICD 203 relevance standard + NAS conflict of interest]

When you receive a question to research:
- Restate the question in your own words to confirm understanding.
- Identify any ambiguity, implicit assumptions, or embedded assertions in the
  question. If the question contains an embedded claim (e.g., "Why did X
  fail?" assumes X failed), surface and test the assumption before proceeding.
- **Vocabulary exploration**: Identify the key concepts in the question and
  determine whether different domains or communities use different terminology
  for the same phenomenon. If a concept may be described differently in
  different fields (e.g., AI researchers say "sycophancy" while healthcare
  says "helpfulness over critical thinking" and defense says "caving to user
  expectations"), map the full vocabulary space before designing searches.
  Single-term searches create systematic blind spots when a phenomenon has
  domain-specific names.
- Confirm the scope: what would count as a satisfactory answer? What is out
  of scope?
- If the question is compound (multiple questions), decompose it into
  individually answerable sub-questions.
- **Researcher profile check**: Before proceeding, review the researcher
  profile against this specific question. If any declared bias, conflict of
  interest, or blind spot is relevant, stop and tell the researcher explicitly.
  State which profile element is relevant, how it might influence the framing
  of the question or the interpretation of results, and how you intend to
  compensate during research. Give the researcher the opportunity to reframe
  the question before you proceed.

### Step 2: Decompose and Identify Candidate Answers

[Source: Chamberlin/Platt multiple working hypotheses, adapted for questions]

Decompose the question into sub-questions that, when answered, will compose
into a complete answer to the original question. For each sub-question, state
what evidence would be needed to answer it.

Then determine whether **candidate answers** are appropriate:

**When candidate answers exist** (the answer space is small and enumerable):

Generate candidate answers as competing hypotheses. Examples:
- Yes/No questions: CA1 = Yes, CA2 = No, CA3 = Partially / conditional
- Short-list questions: CA1 = Option A, CA2 = Option B, CA3 = None of these

For each candidate answer, state what evidence would support it and what
evidence would eliminate it. Design subsequent research to discriminate
between candidates, not to confirm any single one.

**When candidate answers do not exist** (the answer space is too large, too
complex, or too unknown to pre-specify):

Do not force candidate answers. Many legitimate questions have answer spaces
that cannot be meaningfully pre-enumerated. Examples:
- "Which empires had the longest peacetime?" — the answer emerges from evidence
- "What factors contributed to X?" — the set of factors is unknown in advance
- "How does X compare to Y?" — the dimensions of comparison emerge from study

In this case, design searches around the sub-questions directly. The answer
will be synthesized from the evidence rather than selected from a pre-defined
list.

State explicitly which path you are taking and why.

### Step 3: Design Discriminating Searches

[Source: Chamberlin/Platt strong inference + PRISMA search transparency]

**With candidate answers**: For each candidate, design searches specifically
intended to find evidence that would disprove it (same as claim mode hypothesis
falsification).

**Without candidate answers**: For each sub-question, design searches intended
to find comprehensive, representative evidence. The goal is coverage and
diversity of perspective, not falsification of a specific position. Design
searches that would surface:
- The mainstream/consensus view
- Dissenting or minority views
- Primary data and original research
- The boundaries of current knowledge (where does certainty end?)

Document your search plan before executing it.

### Step 7: Synthesize the Collection

[Source: IPCC two-axis confidence model]

Inherited from claim mode — assess evidence quality, source agreement,
independence, and outliers identically.

**Additional requirement for candidate-answer path**: If candidate answers
exist, also produce an ACH matrix (same as claim mode) evaluating each piece of
evidence against each candidate answer. The matrix uses the same format and
diagnosticity analysis as claim mode.

**Additional requirement for synthesis path**: If no candidate answers exist,
instead of an ACH matrix, produce:
- **Thematic clusters**: Group the evidence into themes or categories that
  emerged from the research. These were not pre-defined — they emerged from
  what you found.
- **Convergence analysis**: Where do independent sources converge on similar
  findings? Where do they diverge?
- **Emerging answer**: Based on the evidence, what answer is taking shape?
  State it as a draft finding, not a conclusion. It will be refined in Step 8.

### Step 8: Assess and Answer

[Source: ICD 203 calibrated probability scale, adapted]

**With candidate answers**: Apply the ICD 203 seven-point probability scale
to each candidate answer. State which candidate is best supported by the
evidence, and the probability that each candidate is correct.

State your assessment as: "The answer is [candidate] ([probability term],
[range]). [Reasoning.]"

**Without candidate answers**: Derive the answer from the synthesized evidence.
The answer may be simple or compound. State:
- The answer itself
- Confidence in the answer: High / Medium / Low (using the same criteria as
  claim mode's confidence rating)
- The reasoning chain from evidence through synthesis to answer
- Caveats, conditions, or qualifications on the answer

Do not force the answer into the probability scale when it does not fit. The
probability scale is designed for binary or small-set outcomes. For complex
answers, confidence + reasoning is more appropriate than a probability
percentage.

### Step 11: Report

[Source: ICD 203 tradecraft standards -- all nine]

Produce the final report with the following structure:

1. **Question**: The question as received and clarified.
2. **Sub-Questions**: Decomposition and which sub-questions were answered.
3. **Candidate Answers** (if applicable): The candidates tested and their
   current status (supported / eliminated / inconclusive).
4. **Answer**: The answer with explicit reasoning chain.
5. **Confidence**: Confidence rating with rationale.
6. **Evidence Summary**: Key sources with scorecard highlights.
7. **Collection Synthesis**: Evidence quality, agreement, independence,
   outliers.
8. **ACH Matrix** (if candidate answers used) or **Thematic Synthesis** (if
   not).
9. **Gaps**: What evidence is missing and what it means.
10. **Self-Audit Results**: Four-domain assessment with any flags.
11. **Researcher Bias Check**: Any declared biases that may have influenced
    this research.
12. **Search Methodology Log**: Full search documentation.

The same quality standards from claim mode apply: every claim sourced, every
judgment distinguished from fact, every reasoning chain explicit.

---

## Layer 3: Output Structure

Inherited from claim mode with the following substitutions:

### Primary Deliverable: Research Report

Use the structure defined in Step 11 above (not claim mode's Step 11).

### Secondary Deliverable: Search Methodology Log

Identical to claim mode.

### Tertiary Deliverable: Source Scorecards

Identical to claim mode.

---

## Entity Mapping: Claim → Query

| Claim Mode Entity | Query Mode Entity | Notes |
|-------------------|-------------------|-------|
| Claim | Question | Input entity |
| Sub-claim | Sub-question | Decomposition |
| Hypothesis | Candidate answer | Optional in query mode |
| ACH Matrix | ACH Matrix or Thematic Synthesis | Depends on path |
| Verdict | Answer | Output entity |
| Probability | Probability (with candidates) or Confidence (without) | |

---

## Researcher Profile

Inherited from claim mode without modification. The same profile template
applies.

---

## Framework Attribution

All attributions from claim mode apply. Additional attribution:

| Component | Source Framework(s) |
|-----------|-------------------|
| Candidate answer optionality | Net-new (observation that answer spaces vary) |
| Dual analysis path (ACH vs synthesis) | Net-new (bridges claim and report modes) |
| Thematic clustering in synthesis path | Adapted from report mode design |
