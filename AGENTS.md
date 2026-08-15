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

Before writing a new helper, service, selector, table model, validation rule,
or database adapter, perform a cross-page reuse review. Start with
`docs/FUNCTION_CATALOG.md`, then search the sibling pages and shared `ui/`,
`db/`, `utils/`, and `automation/` modules by business fields, user-facing
labels, table/RPC names, and tests—not only by the proposed function name.
Choose in this order: compose an existing capability; extend an existing
interface; extract a shared core and migrate every active duplicate; create a
new implementation only when the catalog and search confirm that the business
semantics are genuinely new. When a change exposes active duplication, remove
that duplication in the same tested change instead of adding a third version.
Keep `docs/FUNCTION_CATALOG.md` current when page ownership or shared
capabilities change.

Group every external ERP integration by provider before grouping it by page or
workflow. Authentication, HTTP requests, payloads, pagination, provider
response handling, production endpoints, logistics endpoints, and provider-
specific parsing for Humbird, SDS, S2B, or another ERP belong under that
provider's package in `automation/api/<provider>/`. Pages and shared workflows
must import the provider package's public facade, not a deep implementation
module. Keep genuinely provider-neutral behavior—business-day ranges, shared
normalized record contracts, carrier classification, workflow stages, retry
primitives, and audit interfaces—in shared modules and compose it from each
provider. Do not create a second provider implementation under a page,
`automation/logistics/`, or `utils/`; compatibility modules may only re-export
an existing provider implementation and must contain no business logic.

Treat UI modularity as seriously as code modularity. Group related functions
in the same page area, and separate distinct workflows with tabs or focused
views instead of stacking multiple full tables and forms on one screen.

Inventory SKU entry and review interfaces must minimize scanning effort. Use
separate fields for brand, material, color, and size instead of one long SKU
label when users need to select or compare those dimensions. Wherever apparel
sizes are offered or displayed, keep the business order `S, M, L, XL, 2XL,
3XL, 4XL, 5XL`; do not use alphabetical sorting.
Interactive SKU entry must reuse the shared linked selector and narrow choices
in the order `material -> brand -> color -> size`; do not recreate independent
unfiltered SKU dropdowns in individual pages.

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

Container interfaces must use the human business batch or remark name as the
primary identity, such as `第十四柜` or `龙哥第一柜`. Show a physical container
number only as secondary supporting information, for example
`第十四柜｜柜号 TRHU5477320`; never force users to recognize a container by the
shipping number alone. Keep the stable internal container key hidden from
ordinary users while continuing to use it for state transitions and audits.
When incoming cargo is known only at a packaging or category level, preserve it
as visibly unallocated cargo with its unit and conversion rules. Do not invent
a SKU split or include the unresolved quantity in SKU-level inventory forecasts
or posting until a user confirms the allocation.
Inactive SKUs must be excluded from every operational selector, inventory
filter, entry table, forecast input, container form, sale, and transfer. Keep
inactive SKUs visible only in SKU administration and historical/audit views so
users can reactivate them and old business records remain traceable.

Every UI operation that increases or decreases inventory must show the same
three-stage SKU-level review before confirmation: current inventory, the
signed batch change, and resulting inventory. Label positive changes as
`本次入库 (+)` and negative changes as `本次出库 (-)`; use
`本次变动 (+/-)` only for a genuinely mixed adjustment. Keep this review in
long-table form, show only affected SKUs, use the shared SKU order, and expose
negative results before the user saves. The rule applies equally to manual
adjustments, daily outbound, system deductions, sales, consumables, container
posting, direct inventory editing, and future inventory-writing workflows.

Use one human review order for SKU data throughout the ERP. Any long-form
table or editor containing material, color, and apparel size must group rows
as material, then color, then the fixed size order S, M, L, XL, 2XL, 3XL,
4XL, 5XL. Apply the same order to entry, preview, verification, costing,
history, and detail views. Wide apparel tables must expose size columns in
that same fixed order. Use the shared SKU sorter instead of local alphabetical
sorting so users never have to relearn row order between workflows.

Do not infer database structure when it can be inspected. Confirm schema before
designing database changes. Never overwrite unrelated worktree changes.

Treat every user-requested Git push as a release gate. Before pushing, run the
full project test suite and expose the test command's direct result to the user
instead of spending response tokens restating the log. Do not push when any
test fails; diagnose and fix the failure first, then rerun the gate. Push only
after the complete suite passes. A short final pass/fail statement is enough
unless a failure needs explanation.
