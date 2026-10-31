Review the plan in context against actual codebase. Check for:
- Missing dependencies or methods that don't exist
- Schema/contract gaps between services
- Edge cases not covered
- Implementation blockers

For multi-phase, multi-module plans also check:
- **File overlap** — multiple phases modifying the same file (flag as risk, suggest restructuring)
- **Implicit dependencies** — Phase B says "depends on Phase A" without specifying what exactly (types? running code? migration state?). Each dependency must name the concrete artifact.
- **Contract completeness** — if a phase consumes types/interfaces from an earlier phase, verify those are fully defined in the plan, not left as "TBD" or "see Phase N"

Report in chat with uncertainties. Update the plan with straight forward findings. Do not create new files.