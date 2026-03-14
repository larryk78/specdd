# todo-cli — example

This is a worked example of the specdd requirements-driven development workflow.

## The original prompt

> "Build me a simple task tracker I can use from the terminal."

That's it. Intentionally vague.

## What happened next

Before writing any code, the requirements were elicited and decomposed:

1. **Elicitation** — three clarifying questions resolved ambiguity about sync, visibility of completed tasks, and scope of edit/delete
2. **URS** — two user requirements captured what was actually wanted
3. **SRS** — five system behaviors defined how the system would satisfy them
4. **DDS** — four design decisions made concrete choices (argparse subcommands, data model, storage path, id lookup)
5. **DTC** — nine GIVEN/WHEN/THEN scenarios left nothing ambiguous

Only then was `todo.py` written — directly from the DTCs, with `# DDS-NNN` comments linking each function back to its design decision.

## Usage

```bash
python3 todo.py add "buy milk"
python3 todo.py add "call dentist"
python3 todo.py list
python3 todo.py done 1
python3 todo.py list
```

## Files

- `reqs.yaml` — full requirements tree (read this first)
- `todo.py` — implementation derived from the DTCs
