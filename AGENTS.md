# After-Sales Project Guide

Read only the documents needed for the current task:

- Engineering and UI work: `docs/PROJECT_RULES.md`
- Inventory, production, access, and business semantics: `docs/BUSINESS_RULES.md`
- Finding the active page and module: `docs/CURRENT_STATE.md`
- Choosing verification depth and controlling execution cost:
  `docs/WORKFLOW.md`

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

Do not infer database structure when it can be inspected. Confirm schema before
designing database changes. Never overwrite unrelated worktree changes.
