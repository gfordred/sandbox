# ZARONIA Desk — LLM Wiki Schema

This file defines the wiki architecture and workflows for this repository.
The wiki is a persistent, LLM-maintained knowledge base about the codebase.
**You (Claude) write and maintain the wiki. The human reads it.**

---

## Directory layout

```
wiki/                   LLM-maintained markdown wiki (you write this)
  index.md              Master catalog — update on every change
  log.md                Append-only chronological log
  overview.md           System-level description and architecture
  modules/              One page per Python module
  concepts/             Domain knowledge (rates, risk, math)
  decisions/            Design decisions and rationale
raw/                    Immutable source documents (human drops files here)
tools/
  search.py             CLI search over wiki pages
src/                    Live source code
```

---

## Page format

Every wiki page follows this structure:

```markdown
# Page Title

> One-sentence summary (shown in index.md)

## Section 1
...

## Section 2
...

## See also
- [[related-page]] — why it's related
- [[another-page]] — why it's related
```

**Linking convention:** Use Obsidian wikilinks: `[[modules/risk_engine]]` or `[[concepts/dv01_krd]]`.
Path is relative to `wiki/`. Omit `.md` extension. Display text optional: `[[modules/risk_engine|Risk Engine]]`.

**No frontmatter** unless the human explicitly requests Dataview support.

---

## Operations

### Ingest (new source added to raw/)

When the human drops a file into `raw/` and asks you to ingest it:

1. Read the source file completely.
2. Discuss key takeaways with the human — ask what to emphasize.
3. Write a summary page in `wiki/` (e.g. `wiki/sources/filename.md`).
4. Identify all existing wiki pages the source touches. Update them.
5. Create new concept or entity pages for anything mentioned but not yet covered.
6. Update `wiki/index.md` — add the new page(s), update touched pages' summaries.
7. Append an entry to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] ingest | Source Title
   - Summary page: [[sources/filename]]
   - Pages updated: [[modules/foo]], [[concepts/bar]]
   - New pages: [[concepts/baz]]
   ```

A single source commonly touches 5–15 wiki pages.

### Query

When the human asks a question:

1. Read `wiki/index.md` to find relevant pages.
2. Use `python tools/search.py "<query>"` if the index isn't enough.
3. Read the relevant pages. Synthesize an answer with `[[page]]` citations.
4. If the answer is non-trivial and reusable, ask whether to file it as a new wiki page.
5. If filed, update `wiki/index.md` and append to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] query | Question summary
   - Answer filed as: [[decisions/filename]]
   ```

### Lint

When the human asks you to health-check the wiki:

1. Read every page. Check for:
   - Contradictions between pages
   - Stale claims superseded by newer sources or code changes
   - Orphan pages (no inbound `[[links]]`)
   - Concepts mentioned but lacking their own page
   - Missing cross-references between related pages
2. Report findings. Fix obvious issues immediately; flag larger ones for human review.
3. Append to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] lint
   - Issues fixed: ...
   - Issues flagged: ...
   ```

### Update after code changes

When you modify source code:

1. Check which wiki pages cover the changed modules.
2. Update those pages to reflect the change.
3. Append to `wiki/log.md`:
   ```
   ## [YYYY-MM-DD] code-update | Brief description
   - Pages updated: ...
   ```

---

## index.md format

```markdown
# Wiki Index

_N pages · last updated YYYY-MM-DD_

## Overview
| Page | Summary |
|------|---------|
| [[overview]] | ... |

## Modules
| Page | Summary |
|------|---------|
| [[modules/foo]] | ... |

## Concepts
...

## Decisions
...

## Sources
...
```

Update the page count and date on every change.

---

## log.md format

Append-only. Newest entries at the **top**. Each entry:

```
## [YYYY-MM-DD] <type> | <title>
<bullet points>
```

Types: `ingest`, `query`, `lint`, `code-update`, `init`.

---

## Search tool

```bash
python tools/search.py "query terms"          # top 5 results
python tools/search.py "query terms" -n 10    # top 10
python tools/search.py "query terms" --paths  # file paths only
```

The tool scores pages by title match, header match, and body frequency.
Use it when the index alone isn't enough to find the right page.

---

## Conventions

- Write for a technical reader who knows Python and rates but may not know this specific codebase.
- Prefer concrete over abstract: include function signatures, class names, actual numbers from the code.
- Keep pages focused. A 200–400 word page with good links beats a 2000-word monolith.
- Every page must have a `## See also` section with at least one link.
- When in doubt, create a new page rather than appending to an existing one.
