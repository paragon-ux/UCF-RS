# Agent Guidance

UCF-RS is separate from Reqtrace. Keep the implementation local, explicit, and
append-only.

- Do not add source-persisted citations by default.
- Do not infer evidence from surrounding context, symbol names, AST identity, or fuzzy matches.
- Mutating commands must append operation and citation-index records.
- Use `python -m unittest discover -s tests` before reporting changes.
- Use `python scripts/ucf_rs.py status --strict` for project-level validation when examples contain UCF-RS state.
