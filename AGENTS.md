# AGENTS.md — virtual-reviewer

## Project Overview

AI-powered security review system that uses LLM expert models to automate
first-pass evaluation of security review requests. Each expert model holds
full regulation text in context (no RAG retrieval). Modules communicate via
structured JSON over stdin/stdout following UNIX philosophy.

## Architecture

Seven CLI modules connected by JSON pipes:

1. `vr-compile` — Offline: regulation Markdown → ExpertProfile JSON files
2. `vr-intake` — Multimodal LLM converts application materials → structured ApplicationRecord (2-pass Q&A)
3. `vr-orchestrate` — Routes ApplicationRecord to expert models in parallel, collects ExpertVerdict[]
4. `vr-brain` — Integrates verdicts, resolves conflicts, produces FinalAssessment
5. `vr-report` — Renders FinalAssessment as Japanese Markdown report (no LLM)
6. `vr-questions` — Generates Q&A sheet from intake questions (no LLM)
7. `vr-answers` — Parses filled Q&A sheet, produces IntakeInput for second pass (no LLM)

## Key Files

```
virtual_reviewer/
  models.py        — Pydantic data models (ApplicationRecord, ExpertProfile, etc.)
  llm.py           — Vertex AI client wrapper (google-genai SDK, ADC)
  log.py           — Structured JSON logging to stderr
  compile.py       — vr-compile entry point
  intake.py        — vr-intake entry point
  orchestrate.py   — vr-orchestrate entry point
  brain.py         — vr-brain entry point
  report.py        — vr-report entry point
  questions.py     — vr-questions entry point
  answers.py       — vr-answers entry point
sample/
  regulations.md   — Sample security regulations for testing
  application.json — Sample application input for testing
workspace/         — E2E test artifacts (not committed)
scripts/
  e2e.sh           — One-shot E2E pipeline test
tests/             — Unit tests (33 tests)
docs/design/
  architecture.md  — Full architecture document
```

## Running

```bash
# Prerequisites
gcloud auth application-default login
export VR_PROJECT_ID=your-project-id

# Compile regulations into expert profiles
vr-compile --output-dir profiles/ < sample/regulations.md

# Full pipeline
cat sample/application.json \
  | vr-intake --profiles-dir profiles/ \
  | vr-orchestrate --profiles-dir profiles/ \
  | vr-brain \
  | tee workspace/assessment.json \
  | vr-report > workspace/report.md

# Or use the E2E script
bash scripts/e2e.sh
```

## Design Constraints

- stdin/stdout for data, stderr for logs (JSONL)
- All inter-module data is typed JSON (Pydantic models with response_schema)
- No RAG — experts hold full regulation text in LLM context
- ADC authentication (no credentials in code)
- All text output (findings, recommendations, reports) in Japanese
