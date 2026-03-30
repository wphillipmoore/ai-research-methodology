# AI Research Methodology

A unified research methodology for AI agents combining nine intelligence and
scientific frameworks into a 14-step evidence-based process. Implemented as a
Claude Code plugin.

## What This Is

A structured research methodology that makes AI agents produce defensible,
auditable, evidence-based research. It combines frameworks from intelligence
analysis (ICD 203), clinical medicine (GRADE, Cochrane, CONSORT), climate
science (IPCC), systematic review methodology (PRISMA, ROBIS), institutional
standards (NAS), and the philosophy of science (Chamberlin/Platt).

The methodology was developed to solve a specific problem: AI agents, when
asked to "research this," default to building a case rather than conducting an
investigation. They confirm what you expect, minimize contradictions, and
present uncertain conclusions as settled. This methodology constrains that
behavior through enforcement language — telling the AI not just what to do,
but what it is prohibited from doing and why.

## Two Modes

- **Claim verification** (`/research claim`) — verify a list of factual
  assertions. Each claim is tested against competing hypotheses with evidence
  scored for reliability, relevance, and bias.
- **Query answering** (`/research query`) — answer research questions. Each
  question generates hypotheses ranked by evidence strength.

Both modes produce complete evidence archives: source scorecards, search logs,
hypothesis evaluations, collection-level synthesis, gap identification,
and a five-domain self-audit.

## Installation

### As a Claude Code plugin

```bash
# Clone the repository
git clone https://github.com/wphillipmoore/ai-research-methodology.git

# Install as a plugin
/plugin marketplace add wphillipmoore/ai-research-methodology
/plugin install ai-research-methodology@wphillipmoore-ai-research-methodology
```

### As a standalone skill

```bash
# Clone and symlink into your skills directory
git clone https://github.com/wphillipmoore/ai-research-methodology.git
ln -s /path/to/ai-research-methodology/skills/research ~/.claude/skills/research
```

## Usage

```bash
# Verify claims from a file
/research claim file=claims.md id=R0001 output=research/R0001-topic

# Answer research questions interactively
/research query

# Re-run previous research (isolation enforced — no access to prior results)
/research rerun research/R0001-topic
```

## The 14-Step Process

1. **Claim/query received and clarified** — ambiguities surfaced, assumptions
   identified
2. **Vocabulary exploration** — map terminology across domains before searching
3. **Competing hypotheses generated** (Chamberlin/Platt) — minimum three
4. **Discriminating searches designed** — what would disprove each hypothesis?
5. **Searches executed and logged** (PRISMA) — every search documented
6. **Per-source scoring** (GRADE + Cochrane) — reliability, relevance, six
   bias domains
7. **Citation chain analysis** — has each source been replicated, challenged,
   or refuted?
8. **Collection-level synthesis** (IPCC) — evidence quality, source agreement,
   independence
9. **Probability assessment** (ICD 203) — seven-point calibrated scale
10. **Gap identification** (NAS) — what's missing and what it means
11. **Process self-audit** (ROBIS) — four-domain bias check
12. **Source-back verification** — re-read sources, verify assessment accuracy
13. **Report** (ICD 203) — every claim sourced, every judgment explicit
14. **Temporal revisitation archive** — enable periodic re-execution

## Anti-Sycophancy by Design

The methodology includes explicit behavioral constraints that target AI's
most dangerous default behaviors:

- Evidence from research outranks training data
- The researcher's claims are inputs to test, not truths to confirm
- Contradictory evidence must be highlighted, not minimized
- Embedded assumptions must be surfaced and tested
- Uncertainty must be stated explicitly
- The AI cannot declare victory early — the full process runs every time

## Customization

The output format (`output-formats/default.md`) can be replaced with a custom
specification. The methodology prompts are independent of the output format —
you can change how results are presented without changing how research is
conducted.

## Attribution

The enforcement language approach was inspired by
[Joohn Choe's ICD 203 Intelligence Research Agent prompt](https://joohn.substack.com/p/the-copy-and-paste-war-on-ai-for).
The analytical methodology is derived from nine intelligence and scientific
frameworks as documented in the methodology prompts.

## License

GPL-3.0. See [LICENSE](LICENSE).

## Author

W. Phillip Moore — [The Infrastructure Mindset](https://theinfrastructuremindset.ghost.io)
