---
name: doc-code-sync
description: Keeps project docs, Python code, templates, and code index synchronized. Use when editing docs/*.md, *.py, templates/*.html, static/*.css, or when the user mentions syncing or aligning docs and code—trigger phrases include 同步、同步修改、一起改、对齐、文档代码对齐、跟着文档改、跟着代码改、更新索引、骨架同步、架构对齐—or asks to sync documents, code, code index, or architecture.
---

# Doc Code Sync

## Scope

Use this skill for agent-mediated synchronization between:

- `docs/大纲.md` — 项目架构总纲
- Design documents under `docs/` — `strategy设计详解.md`, `ui.md` 等
- Python code: `app.py`, `data.py`, `strategy.py`, `board.py`, `datasources.py`, `portfolio.py`
- Frontend: `templates/index.html`, `static/style.css`
- `docs/代码索引.md` — concept → file/function mapping
- `docs/中英对照表.md` — 中文术语 → 英文标识符

This skill does not create an unattended background watcher.

## Required Order

1. Read `docs/大纲.md` first — it defines the project architecture layers.
2. Read the directly affected source:
   - changed design doc → relevant `docs/*.md`
   - changed Python code → relevant `*.py`
   - changed template/style → `templates/index.html` / `static/style.css`
3. Read `docs/代码索引.md` before changing module responsibilities or adding public symbols.
4. Read `docs/中英对照表.md` before introducing new English code identifiers.
5. Execute the smallest synchronized change set.
6. Run `ruff check` on changed `.py` files.

Do not edit `docs/大纲.md` unless the user explicitly asks to update the outline.

## Entry Workflows

### Design Doc Changed

When a design document under `docs/` changes:

1. Identify the concept changed.
2. Find the corresponding code module from `docs/代码索引.md`.
3. Update Python code following the architecture layers defined in `docs/大纲.md`:
   - `strategy.py` — 核心逻辑层（项目灵魂），改动永远先从这里下手
   - `data.py` / `datasources.py` / `board.py` / `portfolio.py` — 数据与业务支撑层
   - `app.py` / `templates/` / `static/` — 入口与展示层，几乎不改
4. If a design doc change affects frontend behavior, also update `templates/index.html` and/or `static/style.css`.
5. If new public functions/classes appear, update `docs/代码索引.md`.
6. If new English code terms appear, update `docs/中英对照表.md`.

### Code Changed

When Python code changes:

1. Determine whether public modules, functions, constants, or responsibilities changed.
2. Update `docs/代码索引.md` if any public path or symbol changed.
3. Update `docs/中英对照表.md` for any new English code term.
4. Update `docs/strategy设计详解.md` when strategy thresholds or signal rules change.
5. Update `docs/ui.md` when frontend behavior (new buttons, new APIs, state changes) is affected.
6. Update design documents only when the code change reflects a real design change, not a temporary implementation detail.

### Template / Style Changed

When `templates/index.html` or `static/style.css` changes:

1. Identify whether the change adds, removes, or modifies a UI element.
2. Update `docs/ui.md`:
   - New button/interaction → add to the UI 元素逐项清单
   - New state machine → add flow diagram
   - New JS function → add to the JS 函数速查表
   - New CSS class → add to the CSS 类速查表
3. If the change adds a new API endpoint used by the frontend, update both `app.py` route docs and `docs/ui.md`.

### Code Index Changed

When `docs/代码索引.md` changes:

1. Treat it as an architectural intent document.
2. Compare the index against the actual project file tree.
3. Create, move, rename, or update code only when the index clearly specifies the desired structure.
4. If the index conflicts with `docs/大纲.md`, stop and ask the user unless the user explicitly says the index is the new source of truth.
5. After code changes, make sure the index still matches the final code.

## Code Rules

- Refer to `.codewhale/instructions.md` for behavioral guidelines (think before coding, simplicity first, surgical changes, etc.).
- Use `docs/中英对照表.md` before naming new English code terms.
- Python style: `ruff check` clean, `ruff format` applied.
- Keep plain text files UTF-8 without BOM.

## Validation

After code edits:

1. Run `ruff check <changed_file.py>`.
2. Run `python -c "from <module> import *; print('OK')"` for changed modules.
3. Report what was synchronized:
   - design docs changed
   - Python code changed
   - template/style changed
   - code index changed
   - glossary changed

## Safety

- Do not silently rewrite broad architecture.
- Do not add behavior that is not supported by existing documents.
- If a design document is ambiguous, clarify with the user before implementing.
- If multiple sources disagree, prefer this order unless the user says otherwise:
  1. explicit user instruction
  2. `docs/大纲.md` (project architecture constitution)
  3. specific design document (`docs/strategy设计详解.md`, `docs/ui.md`)
  4. `docs/代码索引.md`
  5. existing code

---

## Worked Example：自选股删除按钮（Template / Style Changed → sync ui.md）

以最近一次真实变更为例——在自选股每行末尾加 `−` 删除按钮。

### 代码变更（`git diff`）

**`templates/index.html`：**
- 表头 `<th>` 加一列 `<th></th>`
- 每行加 `<td><button class="btn-del" onclick="removeFromWatchlist(...)">−</button></td>`（server 渲染 + JS 渲染两处）
- 新增 `async function removeFromWatchlist(code)`（调用 `/api/watchlist/toggle`，然后 `reloadWatchlist()`）

**`static/style.css`：**
- 新增 `.btn-del` 类（圆形 22×22，红色透明，hover 加深）

### Skill 触发的同步动作

1. **识别变更类型** → Template / Style Changed
2. **检查 git diff 确认影响范围**：
   - `templates/index.html`：新增 UI 按钮 + JS 函数
   - `static/style.css`：新增 CSS 类
3. **同步 `docs/ui.md`**：
   - **自选股区表格**：操作列新增 `−` 按钮，触发 `removeFromWatchlist(code)`
   - **JS 函数速查表**：新增 `removeFromWatchlist` 行
   - **CSS 类速查表**：新增 `.btn-del` 行
   - **状态机**：「自选股 添加 / 删除」流程图中已有删除分支，无需改
4. **同步 `docs/代码索引.md`**：无新增公开 Python 符号，跳过
5. **同步 `docs/中英对照表.md`**：
   - 新增 `移出自选 | removeFromWatchlist | function | index.html`
   - 新增 `删除按钮 | btn-del | class | style.css`
6. **验证**：`ruff check` 无 Python 变更，跳过
7. **输出报告**：
   - template/style changed: `templates/index.html`, `static/style.css`
   - design docs changed: `docs/ui.md`（自选股区 + JS/CSS 速查表）
   - glossary changed: `docs/中英对照表.md`（+2 条）
