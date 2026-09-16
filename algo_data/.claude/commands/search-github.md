---
description: Search GitHub for code snippets and ready-made solutions for a coding task
argument-hint: [description of what to search for]
---

Search GitHub repositories for existing code implementations, patterns, and ready-made solutions for the following task:

$ARGUMENTS

Follow the github-code-search skill workflow:
1. First determine the appropriate technical stack from the current project context (check package.json, requirements.txt, Cargo.toml, go.mod, CLAUDE.md, or similar). If the stack is unclear, ask the user.
2. Formulate 2-4 targeted search queries using WebSearch with site:github.com and relevant keywords.
3. For each promising result, use WebFetch to retrieve actual code.
4. Evaluate results for relevance, quality, license compatibility, and freshness.
5. Present findings in structured format with recommendations.
6. If good matches found, suggest how to adapt them to the current project.
