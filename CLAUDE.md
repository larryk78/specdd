# Requirements-Driven Development

Before writing any code, decompose the task into a requirements hierarchy and write it to `reqs.yaml`. Keep `reqs.yaml` updated throughout the conversation as understanding improves or implementation reveals new requirements.

## The Decomposition Cascade

Work top-down through four levels until every DTC is unambiguous:

- **URS** (User Requirement Spec) — what the user wants, in their words. Vagueness is acceptable here.
- **SRS** (System Requirement Spec) — observable system behaviors that satisfy the URS. No implementation decisions yet.
- **DDS** (Design Decision Spec) — concrete design choices that realize each SRS. One DDS per significant decision.
- **DTC** (Design Test Case) — a single GIVEN/WHEN/THEN scenario. Must be specific enough that two developers independently reading it would write the same test.

A DTC is complete when it contains no ambiguous terms. If you find yourself writing vague DTCs, go back and split the parent DDS.

## reqs.yaml Format

```yaml
schema_version: "1.0"

counters:
  URS: 0   # increment before adding each new URS
  SRS: 0
  DDS: 0
  DTC: 0

requirements:
  URS-001:
    id: URS-001
    type: URS
    title: "..."
    status: active
    parent: null
    description: |
      ...

  SRS-001:
    id: SRS-001
    type: SRS
    title: "..."
    status: active
    parent: URS-001
    description: |
      ...

  DDS-001:
    id: DDS-001
    type: DDS
    title: "..."
    status: active
    parent: SRS-001
    description: |
      ...

  DTC-001:
    id: DTC-001
    type: DTC
    title: "..."
    status: active
    parent: DDS-001
    description: |
      ...
    test_scenario: |
      GIVEN ...
      WHEN ...
      THEN ...
```

## Workflow

1. **Elicit before decomposing.** If the user's request is ambiguous, ask clarifying questions first. Do not start decomposing until you understand the success criteria.

2. **Write reqs.yaml before writing code.** The requirements are the design. Code follows from DTCs, not from the URS.

3. **Reference IDs in code.** Every function or module that implements a DDS should have a comment like `# DDS-001` so the link from code back to spec is explicit.

4. **Update as you learn.** If implementation reveals a gap or contradiction in the requirements, update `reqs.yaml` first, then update the code.

5. **Mark status honestly.**
   - `active` — requirement is agreed and implemented
   - `needs_review` — implementation changed; spec may no longer match
   - `inactive` — descoped but kept for history
