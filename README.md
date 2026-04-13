# AI Research Methodology

A unified research methodology for AI agents combining nine intelligence and
scientific frameworks into an 11-step evidence-based process. Available as a
Claude Code plugin or as a standalone prompt for any AI interface (Claude,
ChatGPT, Gemini, or any capable LLM).

## Table of Contents

- [What This Is](#what-this-is)
- [Three Input Types](#three-input-types)
- [Installation](#installation)
- [Usage](#usage)
- [MCP Server (optional)](#mcp-server-optional)
- [dio CLI](#dio-cli)
- [Configuration](#configuration)
- [The 11-Step Process](#the-11-step-process)
- [Anti-Sycophancy by Design](#anti-sycophancy-by-design)
- [Customization](#customization)
- [Attribution](#attribution)
- [License](#license)

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

The detailed background behind this methodology — the framework evaluation,
the design decisions, and the evidence for every feature — is discussed in a
pair of articles:

- [The Truth is Out There. But How Do You Find It?][part1]
  — the what and the why (Part 1)
- [The Truth is Out There. Now Go Find It.][part2]
  — the how and how to get it (Part 2)

[part1]: https://the-infrastructure-mindset.ghost.io/the-truth-is-out-there/
[part2]: https://the-infrastructure-mindset.ghost.io/the-truth-is-out-there-now-go-find-it/

## Three Input Types

- **Claims** — factual assertions to verify. Each claim is tested against
  competing hypotheses with evidence scored for reliability, relevance, and
  bias.
- **Queries** — research questions to answer. Each question generates
  hypotheses ranked by evidence strength.
- **Axioms** — facts declared by the researcher that must be assumed true
  during the investigation. Not tested — they function as constraints that
  frame the research.

All three can be combined in a single research run using `/research run`.

Research produces complete evidence archives: source scorecards, search logs,
hypothesis evaluations, collection-level synthesis, gap identification,
and a five-domain self-audit.

## Installation

### As a Claude Code plugin (recommended)

From within a Claude Code session, run these two commands:

```bash
# Add the marketplace (one-time setup)
/plugin marketplace add wphillipmoore/ai-research-methodology

# Install the plugin
/plugin install ai-research-methodology@ai-research-methodology
```

The first command registers the marketplace. The second installs the plugin.
After installation, the `/research` skill is available in all sessions.

**Verify the install**: run `/plugin`, go to the **Installed** tab, and
confirm `ai-research-methodology` appears with the expected version.

Documentation:
[Discover and install plugins](https://code.claude.com/docs/en/discover-plugins),
[Plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)

### Updating to a new version

From within a Claude Code session:

```bash
# Refresh the marketplace to pick up new versions
/plugin marketplace update ai-research-methodology

# Then update the plugin
# Option A: use the interactive UI
/plugin
# Go to Installed tab → select the plugin → Update

# Option B: from the shell (outside a session)
claude plugin update ai-research-methodology@ai-research-methodology
```

After updating, run `/reload-plugins` to activate the new version in your
current session.

Documentation:
[Configure auto-updates](https://code.claude.com/docs/en/discover-plugins#configure-auto-updates),
[CLI commands](https://code.claude.com/docs/en/plugins-reference#cli-commands-reference)

**Note**: Auto-updates are disabled by default for third-party marketplaces.
To enable them, go to `/plugin` → **Marketplaces** tab and configure
auto-update for this marketplace.

### As a standalone prompt (any AI interface)

Copy the contents of
[`ai-research-methodology/standalone/research.md`](ai-research-methodology/standalone/research.md)
and paste it into any AI conversation — Claude, ChatGPT, Gemini, or any
capable LLM. Then provide your claims, queries, and/or axioms. The prompt
includes both the research methodology and the output format. It was
developed and tested with Claude but uses no Claude-specific features.

- With file system access: results are written as a directory of linked
  markdown files.
- Without file system access: results are displayed in the conversation and
  offered as a single downloadable HTML file with internal navigation.

## Usage

```bash
# Run research from a file (claims, queries, axioms, or any combination)
/research run file=claims.md output=research/ai-trust

# Run research interactively
/research run

# Re-run previous research (isolation enforced — no access to prior results)
/research rerun research/ai-trust

# Extract verifiable claims from a document
/research extract articles/my-article/drafts/draft.md

# Fact-check a document (extract claims + verify in one step)
/research fact-check articles/my-article/drafts/draft.md output=research/my-article-claims

# Fact-check in batch mode (no confirmation prompts)
/research fact-check article.md output=research/check confirm=no
```

## MCP Server (optional)

The Diogenes MCP server exposes Python-based web search and page fetching
tools that Claude Code can use instead of its built-in AI web search.
This is **optional** — the plugin works without it. The MCP server reduces
token consumption during the search phase by ~93%.

**Without MCP**: The AI uses its built-in web search tool. Works
out of the box, but search-heavy research consumes more tokens.

**With MCP**: The AI calls `dio_search` and `dio_fetch` instead.
Searches are executed by Python via Serper.dev (or Brave/Google), and
only the results (titles, URLs, snippets) are returned to the AI.

**Requires**: A configured search provider with a valid API key. The
default provider is Serper.dev (free tier: 2,500 searches/month). Brave
Search and Google Custom Search are also supported. See
[Configuration](#configuration) for setup.

### MCP Setup

1. Install the package:

   ```bash
   pip install diogenes
   ```

2. Configure your search provider API key
   (see [Configuration](#configuration)).

3. Add to Claude Code settings (`~/.claude/settings.json`):

   ```json
   {
     "mcpServers": {
       "diogenes": {
         "command": "dio-mcp"
       }
     }
   }
   ```

4. Restart Claude Code. The MCP tools are now available in all sessions.

### MCP Tools

| Tool | Description |
| ---- | ----------- |
| `dio_search` | Web search via configured provider. Returns titles, URLs, snippets. |
| `dio_fetch` | Fetch a URL, extract visible text (~2000 chars). |
| `dio_search_batch` | Execute multiple searches at once. |

## dio CLI

The `dio` command-line interface runs the full 11-step research pipeline
as a Python coordinator calling AI sub-agents via the Anthropic API. It
uses the same methodology as the plugin but manages the process
programmatically.

**Requires**: An Anthropic API key and a configured search provider
with a valid API key. See [Configuration](#configuration) for setup.

```bash
# Install
pip install diogenes

# Run research
dio run input.md --output research/my-topic --runs 1
```

The CLI produces JSON output files at each pipeline step (clarified
input, hypotheses, search plans, search results, source scorecards,
synthesis, self-audit, and final reports), plus a `usage.json` with
per-call token counts and estimated costs.

## Configuration

Diogenes resolves configuration from multiple sources in priority order.
Higher-priority sources override lower ones.

### Priority order

1. **Environment variable** — highest priority, overrides everything
2. **`.env` file** — `.env` in the current directory (standard Python
   convention, loaded as pseudo-environment variables)
3. **Project `.diorc`** — `.diorc` file in the current directory
4. **User `~/.diorc`** — `~/.diorc` in your home directory (recommended
   for personal API keys that apply across all projects)

### Required keys

| Key | Required for | Where to get it |
| --- | ------------ | --------------- |
| `ANTHROPIC_API_KEY` | dio CLI only | <https://console.anthropic.com/> |
| Search provider API key | MCP server, dio CLI | See search providers table below |

At least one search provider must be configured. The default provider is
Serper.dev. Diogenes checks for a configured provider at startup and
raises an error if none is found.

### Search providers

| Provider | Config value | API key variable | Free tier |
| -------- | ------------ | ---------------- | --------- |
| Serper.dev (default) | `serper` | `SERPER_API_KEY` | 2,500 searches/month |
| Brave Search | `brave` | `BRAVE_API_KEY` | Paid only ($5/month) |
| Google Custom Search | `google` | `GOOGLE_API_KEY` + `GOOGLE_SEARCH_ENGINE_ID` | 100/day |

To use a non-default provider, set `provider` in the `[search]` section
of your `.diorc` file. Diogenes uses the provider specified in the
configuration and requires the corresponding API key.

### Recommended: user `~/.diorc` file

For personal use, create `~/.diorc` with your API keys. This keeps
keys out of project directories and works across all projects.

```toml
[api]
key = "sk-ant-..."

[search]
provider = "serper"
serper_api_key = "your-serper-key"
```

### Alternative: project `.diorc` file

For project-specific configuration, create `.diorc` in the project root.
Project settings override user settings.

```toml
[api]
key = "sk-ant-..."
model = "claude-sonnet-4-20250514"

[search]
provider = "brave"
brave_api_key = "your-brave-key"
```

### Alternative: environment variables

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export SERPER_API_KEY="your-serper-key"
```

## The 11-Step Process

1. **Claim/query received and clarified** — ambiguities surfaced, assumptions
   identified, axioms acknowledged
2. **Vocabulary exploration** — map terminology across domains before searching
3. **Competing hypotheses generated** (Chamberlin/Platt) — minimum three
4. **Discriminating searches designed** — what would disprove each hypothesis?
5. **Searches executed and logged** (PRISMA) — every search documented
6. **Per-source scoring** (GRADE + Cochrane) — reliability, relevance, six
   bias domains
7. **Collection-level synthesis** (IPCC) — evidence quality, source agreement,
   independence
8. **Probability assessment** (ICD 203) — nine-point calibrated scale
   (including deterministic endpoints)
9. **Gap identification** (NAS) — what's missing and what it means
10. **Process self-audit + source-back verification** (ROBIS + net-new) —
    five-domain bias check including interpretation verification
11. **Report with revisit triggers** (ICD 203) — every claim sourced, every
    judgment explicit, specific conditions for re-research identified
12. **Temporal revisitation archive** — enable periodic re-execution

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

The output format
(`ai-research-methodology/skills/research/output-formats/default.md`) can be
replaced with a custom
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

W. Phillip Moore — [The Infrastructure Mindset](https://the-infrastructure-mindset.ghost.io)
