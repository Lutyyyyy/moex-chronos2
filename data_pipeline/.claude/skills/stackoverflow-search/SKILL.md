---
name: stackoverflow-search
description: >-
  Search Stack Overflow for working code snippets and ready-made solutions.
  Triggers when the user asks to "search Stack Overflow", "find code on SO",
  "search for a solution on Stack Overflow", "check if someone solved this on
  Stack Overflow", "find a working snippet", "look for answers on SO", or when
  the user mentions Stack Overflow in the context of finding code. Also triggers
  on "search SO", "SO snippet", "stackoverflow solution".
version: 0.1.0
---

# Stack Overflow Code Search

Find **verified, working code snippets** on Stack Overflow using a two-stage pipeline: broad discovery, then deep per-thread inspection.

**Hard rule:** Only return code that is confirmed to work. If no reliable snippet exists — ask the user to decompose the task into smaller searchable sub-problems.

## When to Use

- User explicitly asks to search Stack Overflow.
- User needs a working snippet for a well-defined, bounded problem (error handling pattern, API call recipe, regex, config syntax, etc.).
- A GitHub code search didn't yield results, but the problem is the kind developers commonly ask about on Q&A sites.

## Workflow

### Phase 1 — Candidate Discovery

**Goal:** Build a shortlist of 3-7 promising Stack Overflow question threads. Do NOT decide the answer here.

#### 1.1 Determine Context

Before searching, establish:

- **Language / framework / library** — from project files (`package.json`, `requirements.txt`, etc.) or by asking.
- **Exact error text** (if applicable).
- **Version constraints** (if applicable).

#### 1.2 Formulate Search Queries

Construct 2-4 query variants using WebSearch. Effective patterns:

```
site:stackoverflow.com "<exact error text>"
site:stackoverflow.com <task> <language> <framework>
site:stackoverflow.com <library> <specific operation> example
site:stackoverflow.com <short problem description> [tag:python] OR [tag:javascript]
```

**Query expansion strategy** (try at least 2 of these):

| Variant | Example |
|---|---|
| Exact error text | `site:stackoverflow.com "Cannot read property 'map' of undefined" react` |
| Shortened/generalized error | `site:stackoverflow.com map undefined array react` |
| Task-oriented | `site:stackoverflow.com iterate nested JSON python` |
| Tag-scoped | `site:stackoverflow.com flask file upload multipart` |

#### 1.3 Collect Candidates

For each search result, note:

- Question URL
- Title
- Vote count / view count (visible in search snippets)
- Whether an accepted answer exists (green checkmark mentioned in snippet)
- Age / last activity (prefer threads active within last 3 years)

**Discard** threads that are:
- Closed as duplicate (follow the duplicate target instead)
- Very old with no recent activity and version-sensitive topic
- Clearly about a different language/framework

Aim for **3-7 candidates** after filtering.

### Phase 2 — Deep Thread Inspection

**Goal:** Inspect each candidate thread one by one. Extract a verified working snippet or reject the thread.

#### 2.1 Fetch and Read Each Thread

Use WebFetch on each candidate URL. For each thread, extract:

- **Full question** — understand what exactly was asked
- **Accepted answer** — code + explanation
- **Top-voted alternative answers** — sometimes better than accepted
- **Comments on answers** — often contain critical corrections, edge cases, version caveats
- **Vote counts** — high votes on answer = community validation

#### 2.2 Classify Each Thread

Assign one of these categories:

| Category | Action |
|---|---|
| **Exact match** | Extract the snippet. This is the target. |
| **Partial analogue** | Note what's reusable, keep searching. |
| **Outdated workaround** | Skip — note the deprecation for context. |
| **Version-specific fix** | Use only if version matches user's stack. |
| **Not applicable** | Discard. |

#### 2.3 Validate the Snippet

Before accepting any snippet as "the answer", verify:

1. **Does the code actually compile/run?** — Check for obvious syntax errors, missing imports, undefined variables.
2. **Do comments contradict the answer?** — Comments saying "this breaks in version X" or "this has a security issue" are disqualifying.
3. **Is the answer self-contained?** — All necessary imports, setup, and context are present or clearly stated.
4. **Vote ratio** — Strongly prefer answers with 10+ upvotes. Be cautious with 0-1 vote answers.
5. **Accepted != correct** — If a non-accepted answer has significantly more votes, prefer it and explain why.

### Phase 3 — Present Results

#### If a reliable snippet is found:

```
## Stack Overflow Search Results

### Problem: "<what was searched>"

**Source:** [Question Title](url) — N upvotes, accepted answer

### Working Snippet

\`\`\`<language>
<the extracted code>
\`\`\`

### Why This Works
<Brief explanation from the answer + relevant comments>

### Caveats
- <Version constraints, if any>
- <Edge cases mentioned in comments>
- <Any adaptation needed for user's specific context>
```

Then adapt the snippet to the user's project (naming conventions, style, integration points).

#### If NO reliable snippet is found:

Do NOT fabricate or guess. Instead:

```
## Stack Overflow Search Results

### Problem: "<what was searched>"

**No verified working snippet found.**

Searched N threads, but none contained a reliable, complete solution.
Reasons: <briefly — too old / wrong version / partial only / conflicting answers>

### Suggested Decomposition

The problem may be too specific or composite for a single SO answer.
Try splitting into smaller sub-problems:

1. <sub-problem 1> — more likely to have a standalone SO answer
2. <sub-problem 2> — common pattern, should be findable
3. <sub-problem 3> — may need custom implementation

Want me to search for any of these individually?
```

## Decision Rules (compact)

```
Need a snippet for a known problem  ->  Phase 1: broad search
Found promising threads             ->  Phase 2: inspect one by one
Thread has validated code            ->  Extract, verify, present
Thread is partial / outdated         ->  Continue to next candidate
All candidates exhausted, no match   ->  Ask user to decompose the task
Snippet found but version-sensitive  ->  Confirm user's version first
```

## Important Notes

- **Never return unverified code.** If you can't confirm a snippet works, say so.
- **Prefer answers with high votes AND recent activity** over accepted-but-old answers.
- **Always link the source thread** so the user can read the full discussion.
- **Check comments.** Stack Overflow comments frequently contain critical corrections that invalidate the main answer.
- **Respect the user's stack.** A Python answer doesn't help a TypeScript project, even if the algorithm is the same — search again in the right language.
- **Rate the confidence:** If the best snippet you found has caveats, say "this likely works but has caveat X" rather than presenting it as certain.
