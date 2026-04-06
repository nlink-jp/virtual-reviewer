# virtual-reviewer

AI-powered security review system that automates first-pass evaluation of security review requests using LLM expert models.

> **Status: PoC (Proof of Concept).** Architecture defined, core pipeline implemented and verified.

## Concept

Traditional RAG-based approaches hit a ceiling: review quality is bounded by retrieval accuracy. virtual-reviewer eliminates retrieval entirely — each expert model holds the full text of its assigned regulations in context, enabling precise application of rules including negations, exceptions, and cross-references.

## Design Philosophy

Follows the UNIX philosophy: each module does one thing well, communicates via JSON on stdin/stdout, and logs to stderr.

```bash
# Full pipeline
cat application.json \
  | vr-intake --profiles-dir profiles/ \
  | vr-orchestrate --profiles-dir profiles/ \
  | vr-brain \
  | tee assessment.json \
  | vr-report > report.md
```

## Architecture

```
Regulation (.md) → vr-compile → Expert Profiles (offline)

Application Materials → vr-intake → vr-orchestrate → vr-brain → vr-report
(multimodal)           (structured)  (expert models)   (final)    (Markdown)
```

### Modules

| Command | Role | Model | LLM |
|---|---|---|---|
| `vr-compile` | Compile regulation Markdown into expert definitions | gemini-2.5-pro | Yes |
| `vr-intake` | Convert application materials into structured data (multimodal, 2-pass Q&A) | gemini-2.5-pro | Yes |
| `vr-orchestrate` | Route to expert models in parallel, collect verdicts | gemini-2.5-flash / pro | Yes |
| `vr-brain` | Resolve conflicts, assess combined risk, produce final verdict | gemini-2.5-pro | Yes |
| `vr-report` | Render FinalAssessment as Japanese Markdown report | — | No |
| `vr-questions` | Generate Q&A sheet from intake questions | — | No |
| `vr-answers` | Parse filled Q&A sheet, produce second-pass IntakeInput | — | No |

All LLM modules use Google Cloud Vertex AI API via `google-genai` SDK with ADC authentication. Models are swappable via environment variables.

## Key Design Decisions

- **No RAG**: Expert models hold full regulation text in context — no retrieval needed
- **UNIX philosophy**: stdin/stdout JSON, stderr JSONL logs, pipe-composable
- **Structured inter-module communication**: Pydantic-validated JSON schemas, not natural language
- **Interactive intake**: Multimodal LLM parses application materials, generates Q&A sheet for missing info
- **Audit trail**: SHA-256 hash chain across all module boundaries for tamper detection
- **Distributed execution**: Modules are location-transparent — SSH pipes work without code changes

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Google Cloud project with Vertex AI API enabled
- ADC configured: `gcloud auth application-default login`

### Installation

```bash
uv sync
```

### Configuration

```bash
export VR_PROJECT_ID=your-gcp-project-id
# Optional overrides:
# export VR_LOCATION=asia-northeast1
# export VR_MODEL_INTAKE=gemini-2.5-pro
# export VR_MODEL_ORCHESTRATOR=gemini-2.5-flash
```

## Usage

### 1. Compile regulations into expert profiles

```bash
vr-compile --output-dir profiles/ < sample/regulations.md
```

### 2. Run the review pipeline

```bash
# First pass — may generate follow-up questions
cat sample/application.json \
  | vr-intake --profiles-dir profiles/ \
  > workspace/intake_output.json

# Generate Q&A sheet for applicant
cat workspace/intake_output.json | vr-questions > workspace/qa_sheet.md

# After applicant fills in answers, run second pass
cat workspace/intake_output.json \
  | vr-answers workspace/qa_sheet_filled.md \
  | vr-intake --profiles-dir profiles/ \
  > workspace/intake_final.json

# Run expert evaluation and final assessment
cat workspace/intake_final.json \
  | vr-orchestrate --profiles-dir profiles/ \
  | vr-brain \
  | tee workspace/assessment.json \
  | vr-report > workspace/report.md
```

### One-shot E2E test

```bash
bash scripts/e2e.sh
```

## Documentation

- [Architecture](docs/design/architecture.md) — Full system design, module specifications, and data structure definitions

## License

MIT
