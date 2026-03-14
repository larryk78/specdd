# specdd

A prototype implementation of a requirements engineering framework for AI-assisted development, based on IREB standards.

The concept is the work of [Gero Blomeyer](https://www.linkedin.com/in/gero-blomeyer-b32105136/). This is an unofficial prototype — I couldn't wait for the real thing.

The core idea: LLMs generate vague code from vague requirements. This framework forces a decomposition cascade that eliminates ambiguity before any code is written.

## The Problem

When you ask an LLM to "build a login system", you get something that roughly looks like a login system. When requirements are underspecified, the LLM fills in the gaps with assumptions — and those assumptions are often wrong.

## The Solution

Decompose requirements top-down through four levels of increasing specificity:

| Level | Name | Purpose |
|-------|------|---------|
| **URS** | User Requirement Spec | What the user wants, in their words |
| **SRS** | System Requirement Spec | Observable behaviors that satisfy the URS |
| **DDS** | Design Decision Spec | Concrete design choices that realize each SRS |
| **DTC** | Design Test Case | A single GIVEN/WHEN/THEN scenario — unambiguous and testable |

By the time you reach DTC level, there is no room for misinterpretation. The test scenario *is* the spec.

## Usage

Copy `CLAUDE.md` and an empty `reqs.yaml` into your project. Claude Code will follow the requirements-driven workflow automatically:

1. Claude elicits requirements before writing any code
2. Claude writes `reqs.yaml` with the full URS→SRS→DDS→DTC hierarchy
3. Code is generated from DTCs, with requirement IDs referenced in comments
4. `reqs.yaml` is kept up to date as the conversation progresses

## Files

```
specdd/
├── CLAUDE.md                          # Instructions for Claude Code
├── reqs.yaml                          # Requirements (single source of truth)
├── scripts/
│   ├── interactive_lastenheft.py      # TUI tree browser (curses, vim keybindings)
│   └── validate_reqs.py               # Formal checker (11 errors, 5 warnings)
└── .git/hooks/pre-commit              # Marks requirements needs_review on commit
```

The scripts and hook are a prototype UI — the primary artifact is `reqs.yaml` and the workflow defined in `CLAUDE.md`.

## reqs.yaml Schema

Requirements are a flat dict keyed by ID. Hierarchy is encoded via the `parent` field.

```yaml
schema_version: "1.0"

counters:
  URS: 1
  SRS: 2
  DDS: 1
  DTC: 3

requirements:
  URS-001:
    id: URS-001
    type: URS
    title: "User-facing goal"
    status: active        # active | inactive | needs_review
    parent: null
    description: |
      ...

  DTC-001:
    id: DTC-001
    type: DTC
    title: "Specific scenario"
    status: active
    parent: DDS-001
    description: |
      ...
    test_scenario: |
      GIVEN ...
      WHEN ...
      THEN ...
```

## Validation

```bash
python3 scripts/validate_reqs.py
```

Checks for duplicate IDs, hierarchy violations, circular references, missing fields, invalid statuses, and more. Run with `--exit-code` to get exit 1 on errors (used by the pre-commit hook).

## Pre-commit Hook

Install once per repo:

```bash
cp .git/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

On each commit, the hook scans staged diffs for requirement ID references (e.g. `# DDS-001`) and marks those requirements `needs_review` in `reqs.yaml` — signaling that the implementation changed and the spec should be verified.

## Dependencies

```bash
pip install pyyaml
```
