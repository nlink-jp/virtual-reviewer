# CLAUDE.md — virtual-reviewer

**Organization rules (mandatory): https://github.com/nlink-jp/.github/blob/main/CONVENTIONS.md**

## This project

AI-powered security review system (Virtual Reviewer). Uses LLM expert models
with full regulation context to perform automated first-pass security reviews,
replacing RAG-based retrieval with direct regulation application.

**Status: Design phase.** Architecture defined, data structures defined,
implementation pending.

## Key structure

```
docs/design/
  architecture.md        ← Full architecture document
```

## Architecture overview

1. Intake Processor: Multimodal LLM converts diverse application materials into structured ApplicationRecord
2. Persona Compiler: Offline pipeline that compiles regulation documents into expert model definitions
3. Orchestrator: Routes ApplicationRecord to relevant expert models, collects verdicts
4. Brain Unit: Integrates expert verdicts, resolves conflicts, produces FinalAssessment

Infrastructure: Google Cloud Vertex AI API (unified endpoint, model swappable via config)
