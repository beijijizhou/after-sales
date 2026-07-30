# Execution Workflow

## Modes

### Fast

Use for copy changes, narrow UI fixes, small mappings, and isolated bugs.

1. Read the target file and direct dependency.
2. Make the smallest complete change.
3. Run syntax check or one targeted test.
4. Stop.

User phrase: `快速处理，只跑相关测试。`

### Standard

Default for normal features and focused refactors.

1. Trace the active call path.
2. Implement the feature and necessary refactor.
3. Run targeted tests.
4. Verify UI or database once when relevant.

User phrase: `标准模式，完成后验证一次。`

### Audit

Use for inventory corrections, financial values, migrations, permissions, and
large shared refactors.

1. Inspect schema and current data.
2. Preview the intended change and totals.
3. Apply the change.
4. Reconcile saved totals.
5. Run broad tests and one UI check.

User phrase: `审计模式，先核对再写入。`

## Where Time Goes

- Searching a large codebase to find the active implementation.
- Re-reading long conversation history to recover business rules.
- Repeated database round trips.
- Running the full test suite for a narrow change.
- Browser verification after every intermediate edit.
- Rendering and visually checking complex spreadsheets.
- Recovering from multiple old modules with similar names.

## When Work Starts Feeling Slow

Ask for a short status using:

`现在卡在哪一步？只告诉我耗时最大的步骤。`

Then choose one:

- `停止全面扫描，只看当前调用链。`
- `先完成核心功能，重构放到下一步。`
- `不要浏览器验证，我自己刷新检查。`
- `只跑相关测试，不跑完整测试。`
- `数据库只做一次预检和一次核验。`
- `先给我结果，非关键问题列为后续项。`

## Starting A Fresh Task

Long conversations increase context cost. For a new task:

1. Open a new task in the same repository.
2. Say which page or module is involved.
3. Ask Codex to read `AGENTS.md`.
4. Include only the new requirement and any changed business rule.

Recommended prompt:

`读取 AGENTS.md。使用标准模式处理 pages/4_库存.py 的这个问题：...`

Use the current long task only when the new work depends on unresolved details
from the ongoing discussion.

## Keeping Documentation Current

- Update `BUSINESS_RULES.md` when a confirmed business rule changes.
- Update `CURRENT_STATE.md` after moving modules or changing ownership.
- Update `PROJECT_RULES.md` only for stable engineering preferences.
- Do not turn these files into activity logs or copy conversation history into
  them.
