#!/usr/bin/env bash
# E2E test script for virtual-reviewer pipeline.
# All intermediate files are written to workspace/.
#
# Usage:
#   ./scripts/e2e.sh
#
# Prerequisites:
#   - VR_PROJECT_ID or GOOGLE_CLOUD_PROJECT is set
#   - gcloud auth application-default login

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE="$PROJECT_DIR/workspace"
SAMPLE="$PROJECT_DIR/sample"

mkdir -p "$WORKSPACE/profiles"

echo "=== Step 1: vr-compile ==="
uv run vr-compile --output-dir "$WORKSPACE/profiles" < "$SAMPLE/regulations.md"

echo ""
echo "=== Step 2: vr-intake ==="
cat "$SAMPLE/application.json" \
  | uv run vr-intake --profiles-dir "$WORKSPACE/profiles" \
  > "$WORKSPACE/intake_output.json"

echo ""
echo "=== Step 3: vr-orchestrate ==="
cat "$WORKSPACE/intake_output.json" \
  | uv run vr-orchestrate --profiles-dir "$WORKSPACE/profiles" \
  > "$WORKSPACE/verdicts.json"

echo ""
echo "=== Step 4: vr-brain ==="
cat "$WORKSPACE/verdicts.json" \
  | uv run vr-brain \
  > "$WORKSPACE/assessment.json"

echo ""
echo "=== Step 5: vr-report ==="
cat "$WORKSPACE/assessment.json" \
  | uv run vr-report \
  > "$WORKSPACE/report.md"

echo ""
echo "=== Done ==="
echo "Results in $WORKSPACE/"
echo "  assessment.json  — structured data"
echo "  report.md        — human-readable report"
