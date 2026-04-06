# Changelog

## v0.1.0 — 2026-04-06

### Added

- Architecture document with full system design
- Module specifications: Intake Processor, Persona Compiler, Orchestrator, Brain Unit
- Data structure definitions: ApplicationRecord, ExpertProfile, ExpertVerdict, FinalAssessment
- Data flow diagrams
- Non-functional requirements (performance, availability, auditability)
- PoC implementation of all core modules:
  - `vr-compile` — regulation Markdown to ExpertProfile JSON
  - `vr-intake` — multimodal intake with 2-pass Q&A validation
  - `vr-orchestrate` — parallel expert model dispatch
  - `vr-brain` — final assessment with conflict resolution
  - `vr-report` — Japanese Markdown report generation
  - `vr-questions` — Q&A sheet generation for applicants
  - `vr-answers` — filled Q&A sheet parser for second-pass intake
- Pydantic data models with Vertex AI `response_schema` enforcement
- Structured JSONL logging to stderr
- ADC authentication via `google-genai` SDK
- Sample regulation document and application data
- E2E test script (`scripts/e2e.sh`)
- 33 unit tests (models, logging, report rendering, Q&A parsing)
