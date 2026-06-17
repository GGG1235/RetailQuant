---
description: Behavioral guidelines to reduce common LLM coding mistakes. Use when writing, reviewing, or refactoring code to avoid overcomplication, make surgical changes, surface assumptions, and define verifiable success criteria.
alwaysApply: true
---

# behavioral guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it. Do one simplification pass only — don't loop.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Preserve original file encoding exactly (no BOM add/remove, no UTF-8/GBK conversion).
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" ¡ú "Write tests for invalid inputs, then make them pass"
- "Fix the bug" ¡ú "Write a test that reproduces it, then make it pass"
- "Refactor X" ¡ú "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] ¡ú verify: [check]
2. [Step] ¡ú verify: [check]
3. [Step] ¡ú verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Seven Code Principles

Use these principles as a practical checklist when implementing or reviewing code:

1. **Single Responsibility Principle (SRP)**  
   One function or module should have one clear purpose, so changes in requirements only affect a small, predictable area.

2. **Open-Closed Principle (OCP)**  
   Prefer extending behavior over modifying stable code paths, to reduce regression risk in existing features.

3. **Liskov Substitution Principle (LSP)**  
   Derived types should be safely usable anywhere the base type is expected, without changing program correctness.

4. **Interface Segregation Principle (ISP)**  
   Keep interfaces focused and minimal, so callers depend only on methods they actually use.

5. **Dependency Inversion Principle (DIP)**  
   Depend on abstractions instead of concrete implementations, which lowers coupling and improves testability.

6. **Don't Repeat Yourself (DRY)**  
   Avoid duplicated logic and duplicated business rules; centralize shared behavior to keep maintenance cost low.

7. **Keep It Simple, Stupid (KISS)**  
   Choose the simplest design that solves the current requirement; avoid speculative complexity and premature abstraction.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
