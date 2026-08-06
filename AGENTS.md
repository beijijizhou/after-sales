# After-Sales Project Guide

At the beginning of every new conversation, before inspecting code, designing
changes, or performing project work, read every project-owned Markdown file
tracked by Git. Discover the current list with `git ls-files '*.md'` so newly
added documents are included automatically. This requirement covers project
documentation such as `AGENTS.md`, `docs/`, module `README.md` files, asset
instructions, automation instructions, and SQL instructions.

Do not include Markdown files from dependencies, caches, generated outputs,
virtual environments, or other untracked third-party directories. After the
initial read, use the relevant documents throughout the conversation without
re-reading all of them before every individual request.

Default execution mode is **standard**:

1. Search only the relevant page and its direct dependencies.
2. Preserve established module and UI patterns.
3. Implement the requested result end to end.
4. Run targeted tests.
5. Use full tests, browser checks, or live database verification only when
   the change's risk requires them.

Treat UI modularity as seriously as code modularity. Group related functions
in the same page area, and separate distinct workflows with tabs or focused
views instead of stacking multiple full tables and forms on one screen.

Batch-oriented workflows are a core ERP design rule. For inbound inventory,
outbound inventory, inventory adjustments, costing, containers, and similar
multi-row business operations, present a batch summary first, then let the
user select a batch to view or edit its complete SKU-level details. Do not
flatten every row from every batch into one large editor. Keep the batch ID,
business date, source, totals, status, and audit history intact so related
rows remain understandable and reversible as one business event. Legacy rows
without an explicit batch ID should be grouped into a stable, explainable
business batch where possible rather than exposed as unrelated records.

Do not infer database structure when it can be inspected. Confirm schema before
designing database changes. Never overwrite unrelated worktree changes.
