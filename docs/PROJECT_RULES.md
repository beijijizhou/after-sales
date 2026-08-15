# Project Rules

## Product Standard

- Treat this system as a commercial ERP product intended for sale to multiple
  companies, not as a one-company internal script.
- New features must be reusable and configurable. Do not hard-code the current
  company's departments, brands, suppliers, spreadsheets, packaging rules,
  workflow names, users, or operational dates when they belong in tenant or
  master-data configuration.
- Design data ownership with future tenant isolation in mind. A company's
  operational records, costs, users, integrations, and configuration must be
  separable without relying on naming conventions.
- Business operations must be explicit and auditable: distinguish inbound,
  outbound, counting, correction, reversal, approval, and synchronization;
  record who, when, source, reason, before value, and after value where
  applicable.
- Prefer controlled workflows over direct mutation for sensitive operations,
  while keeping routine warehouse work efficient. Cost, identity, permissions,
  and large inventory changes require stronger validation and auditability.
- Database changes must use repeatable, ordered migrations with constraints,
  rollback or repair guidance, and compatibility consideration for existing
  customer data.
- Public product behavior must fail clearly and safely. Do not expose secrets,
  raw provider errors, stack traces, or implementation details to end users.
- Integrations must be replaceable per company and environment. Credentials,
  Drive folders, spreadsheet IDs, API accounts, and platform mappings belong
  in secure configuration, not shared source constants.
- Preserve localization and accessible manager-oriented UI. Company-specific
  terminology should be configurable instead of implemented as global labels.
- Every material feature requires proportionate automated tests; inventory,
  finance, permissions, tenant boundaries, synchronization, and migrations are
  high-risk areas and require stronger verification.
- Maintain backward compatibility or provide an explicit migration path when
  changing stored data, APIs, configuration, or user workflows.

## Structure

- A Python file should normally stay around 100-200 lines.
- This is a rule of thumb, not a reason to split cohesive logic unnaturally.
- Main page files act as controllers. They select data, permissions, and views.
- Business logic belongs in `db/` or `utils/`; rendering belongs in `ui/`.
- Similar modules belong in one folder. Aim for roughly four focused files per
  folder, but prefer clear ownership over an arbitrary file count.
- Centralize reusable helpers instead of copying logic between QA, hotstamp,
  inventory, containers, and production pages.
- Group external ERP code by provider under `automation/api/<provider>/`.
  Authentication, requests, payloads, production and logistics endpoints, and
  provider-specific parsing share that provider boundary. Put only genuinely
  provider-neutral contracts and utilities in shared integration modules.
- Keep SQL grouped by domain and purpose. Do not combine unrelated platform
  maintenance functions into one oversized SQL script.

## Changes

- Read the active call path before editing. The repository may contain legacy
  modules with similar names.
- Follow current interfaces and patterns before adding new abstractions.
- Keep changes scoped. Refactoring is welcome when it directly improves
  maintainability or removes active duplication.
- Do not silently omit invalid rows. Show users which SKU, barcode, or record
  failed and stop an unsafe batch operation.
- Database writes must be auditable, idempotent where practical, and followed
  by one focused result check.
- Use New York time for operational dates and timestamps.
- When a user asks to correct recurring operational data, implement a reusable
  product workflow for authorized users instead of treating the request as a
  one-time direct database edit. Direct database repair is reserved for
  exceptional recovery when the normal product workflow cannot represent the
  correction.
- Editing an auditable inventory movement must be presented together with its
  existing reversal workflow. The user chooses either reversal only or
  modification and replacement; modification is persisted as reversal of the
  original batch followed by a corrected batch, preserving both records.

## UI

- UI structure must be modular like code structure: group related functions in
  one page area and give each area one clear purpose.
- Do not vertically stack several complete tables or workflows when users only
  need one at a time. Use tabs or focused view switching while preserving the
  shared filters and selection state.
- Keep similar operations together; for example, list, filtered summary, and
  detail views for one business object belong in the same page section.
- Design for a manager who needs a decision quickly.
- Put conclusions, risks, and important totals first and on the left.
- Put parameters and calculation details after the result.
- Avoid showing the same metric in multiple places.
- Prefer one sortable table over several redundant charts or rankings.
- For manual bulk operational input, prefer an editable table that supports
  pasting Excel or Google Sheets columns instead of a multiline text box.
- Use tabs to separate daily work, analysis, history, undo, and master data.
- Reuse shared department/category/brand/material/color/size filters.
- A selected department controls available categories; stale selections must
  reset when the department changes.
- Use wide tables for size/model comparisons when they reduce rows.
- Explain disabled actions in the UI.
- Cost is hidden by default and visible only with the correct permission.
- Inventory surfaces support Chinese, English, and Spanish.

## Verification

- Narrow logic change: syntax check plus targeted tests.
- Shared business logic: targeted tests plus related integration tests.
- UI interaction change: one browser verification after implementation.
- Database write: one precheck and one post-write verification.
- Full test suite is for shared contracts, broad refactors, or release checks.
