# Capability Inventory

## Workflow Mode

- Mode: general-delivery
- Rationale: No strong sample or harness signal was detected, so the workflow should treat this as general staged delivery.

## Coverage Guidance

- Use this file before story slicing to avoid converging too early on a thin sample.
- Required capabilities should usually appear in the first story plan or in explicit deferred stories.
- Recommended capabilities should be reflected in future stories unless intentionally deferred.
- Optional capabilities can be left out if the sample is still coherent without them.

## Capability Categories

### Core Contract Usage
- Status: optional
- Owning workflow: demo
- Why: A sample should show the core shape of the contract model before layering on advanced behavior.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Bootstrap one minimal contract example
  - Show raw input validation into a typed model

### Field Validation
- Status: optional
- Owning workflow: demo
- Why: Validation annotations and failure behavior are usually one of the first meaningful capabilities a developer expects to see.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Add one focused validation example
  - Show multiple violations in a single failing payload

### Sanitization And Visibility
- Status: optional
- Owning workflow: demo
- Why: Libraries in this space often distinguish stored/internal fields from public output, so samples should make that explicit.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Show how sensitive fields are removed or redacted
  - Compare validated internal state to sanitized output

### Nested Structures
- Status: optional
- Owning workflow: demo
- Why: Real payloads are rarely flat. Nested structures prove the sample is useful beyond toy fields.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Add one nested contract with raw decoding
  - Show validation across nested structures

### Lifecycle And Field Semantics
- Status: optional
- Owning workflow: demo
- Why: Field-level semantics often separate a realistic sample from a basic tutorial.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Add immutable or reserved field examples
  - Document which fields are persisted vs public

### Custom Validators
- Status: optional
- Owning workflow: demo
- Why: Custom validators show where contract annotations stop and domain-specific rules begin.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Add one contract-level validator
  - Show a failure path for a derived business rule

### Patch And Partial Validation
- Status: optional
- Owning workflow: demo
- Why: If the target is a service or harness, patch and partial flows are often critical to realistic coverage.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Add a patch validation example
  - Add a draft or partial validation path

### Schema And Introspection
- Status: optional
- Owning workflow: demo
- Why: Schema generation is a meaningful differentiator if the library supports introspection or downstream integration.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Add one schema generation example
  - Document how schema output relates to the contract model

### Runtime Integration
- Status: optional
- Owning workflow: demo
- Why: Some workflows need a true service boundary, not just isolated tests. This is where realistic execution enters the sample.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Wrap the contract flow in one runtime entry point
  - Show how validated raw data moves through the service

### Developer Guidance
- Status: optional
- Owning workflow: demo
- Why: Without explicit guidance, even a good sample can feel opaque.
- Why now: This capability is useful but not necessarily needed in the first version.
- Story prompts:
  - Add a README that explains each capability slice
  - Explain how to run and extend the sample
