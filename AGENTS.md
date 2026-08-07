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

Treat dependent UI state as a data dependency, not as an isolated widget
choice. When an upstream department, category, date range, mode, or filter
changes, recompute every downstream option set in the same rerun. Clear or
reset stale selections, selected batches, editors, previews, and displayed
details before rendering them. Preserve a user's child selection only while
its parent scope and option set are unchanged. Add regression coverage for
important cascading selectors so the UI never displays data from the previous
scope under a newly selected parent.

ERP automation must be reviewable and traceable in the product UI. Never hide
business mappings, normalization rules, substitutions, allocation priorities,
or source coverage only in Python code. Before a consequential operation, show
the source fields, normalized values, target business records, rule/version,
quantities, exceptions, and the exact scope being applied. After the operation,
preserve a batch-first audit trail containing the business date, source scope,
mapping rule/version, final row-level targets, quantities, operator, timestamp,
status, and reversals. Users must be able to reconstruct why a row changed
without reading source code or asking an administrator to query the database.

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

Treat every user-requested Git push as a release gate. Before pushing, run the
full project test suite and expose the test command's direct result to the user
instead of spending response tokens restating the log. Do not push when any
test fails; diagnose and fix the failure first, then rerun the gate. Push only
after the complete suite passes. A short final pass/fail statement is enough
unless a failure needs explanation.
