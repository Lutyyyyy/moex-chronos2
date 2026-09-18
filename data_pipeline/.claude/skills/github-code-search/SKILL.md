---
name: github-code-search
description: >-
  This skill should be used when the user asks to "search GitHub for code",
  "find existing implementations", "look for code patterns", "search for
  ready-made solutions", "find code snippets on GitHub", "check if someone
  already implemented this", "find open source examples", "search repos for
  code", or when implementing a non-trivial coding task where existing
  open-source solutions or patterns may exist. Also triggers when the user
  says "don't reinvent the wheel", "find existing code", "look for libraries",
  or "search for implementations".
version: 0.1.0
---

# GitHub Code Search

Search GitHub repositories for code snippets, patterns, and ready-made solutions before writing code from scratch. Reuse battle-tested open-source implementations when available.

## When to Use

This skill applies in two modes:

1. **Explicit mode**: The user directly asks to search GitHub for code or patterns.
2. **Advisory mode**: While implementing a non-trivial coding step (algorithm, protocol, integration, UI pattern), consider searching for existing implementations first. Especially relevant for:
   - Mathematical/geometric algorithms (geodesic spheres, pathfinding, etc.)
   - API client integrations (Telegram, Discord, Stripe, etc.)
   - UI components (3D viewers, chart widgets, drag-and-drop, etc.)
   - Data format parsers/generators (PDF, Excel, protobuf, etc.)
   - Protocol implementations (WebSocket, OAuth, MQTT, etc.)

## Workflow

### Step 1: Determine the Technical Stack

Before searching, establish the target tech stack. Sources (in priority order):

1. **Project context**: Read `CLAUDE.md`, `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`, or equivalent to detect the existing stack.
2. **Architecture/plan documents**: Check for architecture docs or task plans in the project.
3. **Ask the user**: If the stack is ambiguous or the project is new, ask which language/framework to target.

Capture: **language**, **framework** (if any), **package manager**, and any **constraints** (e.g., "no external dependencies", "must be MIT licensed").

### Step 2: Formulate Search Queries

Construct 2-4 targeted search queries. Effective patterns:

- `"<algorithm/feature> <language>"` — e.g., `"goldberg polyhedron python"`
- `"<library> <task> example"` — e.g., `"telethon get phone by user_id"`
- `"<framework> <component> component"` — e.g., `"three.js 3d model viewer react"`
- Add qualifiers: `language:<lang>`, `stars:>50`, `path:src`

Use WebSearch with queries like:
- `site:github.com <query>`
- `github <feature> <language> example`
- `<library> <task> tutorial OR example`

### Step 3: Search and Evaluate

Execute searches using the WebSearch tool. For each promising result:

1. Use WebFetch to retrieve the actual code from GitHub raw URLs or repository pages.
2. Evaluate fitness:
   - **Relevance**: Does it solve the actual problem?
   - **Quality**: Is it well-structured, tested, maintained?
   - **License**: Is the license compatible? (MIT, Apache-2.0, BSD preferred)
   - **Freshness**: When was it last updated?
   - **Stars/forks**: Community validation signal.
3. Extract the useful code snippet or pattern.

### Step 4: Present Findings

Report results to the conversation in this format:

```
## GitHub Code Search Results

### Query: "<what was searched>"

**Found N relevant results:**

1. **[repo-name](url)** (stars, license, last updated)
   - What it does: <brief description>
   - Relevance: <how it applies to current task>
   - Code snippet: <key extract>

### Recommendation
<Which approach to use and why — adapt existing code, use as library, or implement from scratch>
```

If no good matches found, state this clearly and proceed with original implementation.

### Step 5: Adapt or Integrate

Based on findings:
- **Direct use**: If a well-maintained library exists, suggest adding it as a dependency.
- **Adapt pattern**: Extract the relevant algorithm/pattern and adapt to the project's style and stack.
- **Reference only**: Use as inspiration but implement independently (always note the source).

Always preserve the project's existing code style, naming conventions, and architecture patterns when adapting external code.

## Search Tips

- For GitHub code search, prefer `site:github.com` in WebSearch queries.
- To read specific files from GitHub, fetch the raw URL: `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>`.
- Check `awesome-<topic>` lists for curated collections.
- Look at package registries (npm, PyPI, crates.io) for maintained libraries before raw code search.
- For algorithm implementations, search `"<algorithm> implementation <language>"`.

## Important Notes

- Always attribute code sources in comments when adapting significant portions.
- Verify license compatibility before suggesting code adoption.
- Prefer well-maintained libraries (recent commits, active issues) over abandoned repos.
- When the user says "search for code" or "find implementations", always use this skill explicitly — do not skip the search.
- In advisory mode, briefly mention that existing implementations were checked (or suggest checking) rather than silently skipping.

## Additional Resources

For detailed search query patterns and GitHub API tips, consult:
- **`references/search-patterns.md`** — Advanced query construction and GitHub search syntax
