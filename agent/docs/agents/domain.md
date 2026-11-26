# Domain Documentation Configuration

**Layout:** single-context

**Domain docs location:** `docs/` at the repository root

**Key documents consumed:**

- `docs/rules.md` - Working rules for collaboration
- `docs/coding-rules.md` - Coding task conventions and standards
- `docs/PRD.md` - Product requirements and scope
- `docs/architecture/` - System architecture and component docs
- `docs/memory.md` - Decision log and design rationale

**ADR directory:** `docs/implementation/` (not traditional ADR format but contains implementation decisions)

**Consumption rules:**

1. Before coding tasks: Read `docs/rules.md` and `docs/coding-rules.md`
2. For architecture questions: Read relevant docs in `docs/architecture/`
3. For design decisions: Consult `docs/memory.md` for historical context
4. For scope boundaries: Read `docs/PRD.md`

**Legacy file migration:** No legacy CONTEXT.md or CONTEXT-MAP.md files exist.