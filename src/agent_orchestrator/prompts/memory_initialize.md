# Memory Initialization Agent

Bootstrap the AGENTS.md memory system for this repository. Your job is to find the **hard-won knowledge** - things that would cause debugging sessions or confusion.

## What Belongs in AGENTS.md

Only capture knowledge that meets this bar:

| Type | Example | Why it matters |
|------|---------|----------------|
| **Foot-guns** | "save() doesn't flush - call flush() or lose data" | Prevents data loss bugs |
| **Non-obvious behavior** | "Cron runs UTC but logs local time" | Saves debugging |
| **Why decisions** | "Vendored X because they break semver" | Prevents re-litigation |
| **Workarounds** | "M1 needs DOCKER_DEFAULT_PLATFORM=linux/amd64" | Unblocks developers |
| **Test quirks** | "Integration tests need Redis running" | Unblocks CI |
| **Cross-cutting rules** | "All errors must extend AppError" | Consistency |

## What Does NOT Belong

- What files exist (use `ls`)
- What functions do (read the code)
- Line numbers (they change)
- Architecture descriptions (explore the code)
- Standard patterns (developers know these)
- Anything in README

## Your Task

1. **Explore the codebase** looking specifically for:
   - Code comments mentioning gotchas, warnings, or "note:"
   - Complex conditional logic that suggests edge cases
   - Environment variable requirements not in README
   - Test setup that isn't obvious
   - Build/deploy quirks

2. **Create minimal AGENTS.md files** only where you find genuinely hard-to-discover knowledge:
   - Most directories need NO AGENTS.md
   - Root level: only repo-wide gotchas
   - Subdirectories: only if there are local foot-guns

3. **Format**: Keep it tight
```markdown
# AGENTS.md

## Gotchas
- Entry 1
- Entry 2
```

No empty sections. No fluff. Aim for <15 lines per file.

## Output

List what you found and created. If you found nothing worth recording, that's a valid outcome - report "No high-value knowledge found" and create no files.
