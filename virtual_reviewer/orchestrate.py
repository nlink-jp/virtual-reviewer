"""vr-orchestrate: Orchestrator.

Reads ApplicationRecord JSON (extracted from IntakeOutput) from stdin,
dispatches to expert models in parallel, and outputs ExpertVerdict[] JSON.

The orchestrator loads expert profiles from --profiles-dir and runs each
expert against the application data.

Usage:
    cat record.json | vr-orchestrate --profiles-dir profiles/

In the pipeline (extracts .record from IntakeOutput automatically):
    cat app.json | vr-intake --profiles-dir profiles/ | vr-orchestrate --profiles-dir profiles/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from virtual_reviewer import log as vr_log
from virtual_reviewer.llm import generate
from virtual_reviewer.models import (
    ApplicationRecord,
    ExpertProfile,
    ExpertVerdict,
)

MODULE = "orchestrator"

EXPERT_USER_PROMPT_TEMPLATE = """\
以下の申請内容を、あなたの担当規定に基づいて評価してください。

## 申請データ

{application_json}

## 指示

1. 担当領域の各規定を申請データと照合してください。
2. 各指摘について以下を記述してください:
   - regulation_ref: 該当する規定のセクションID
   - target_field: ApplicationRecord のどのフィールドに関する指摘か
   - severity: critical, high, medium, low, info のいずれか
   - finding: 問題の内容（日本語で記述）
   - recommendation: 推奨対策（日本語で記述）
3. 総合判定を設定: pass, fail, conditional, insufficient_info
4. 確信度スコアを設定（0.0〜1.0）

JSON形式で応答: {{"expert_id": "{expert_id}", "verdict": "...", "findings": [...], "confidence": ...}}
"""


def _load_profiles(profiles_dir: Path) -> list[ExpertProfile]:
    """Load all expert profiles from directory."""
    profiles = []
    for p in sorted(profiles_dir.glob("*.json")):
        profile = ExpertProfile.model_validate_json(p.read_text(encoding="utf-8"))
        profiles.append(profile)
    return profiles


def _run_expert(
    profile: ExpertProfile, application_record: ApplicationRecord
) -> ExpertVerdict:
    """Run a single expert model against the application."""
    vr_log.info(
        MODULE,
        "expert_dispatch",
        f"Dispatching to expert: {profile.expert_id}",
        expert_id=profile.expert_id,
        domain=profile.domain,
    )

    app_json = application_record.model_dump_json(indent=2, ensure_ascii=False)
    user_prompt = EXPERT_USER_PROMPT_TEMPLATE.format(
        application_json=app_json,
        expert_id=profile.expert_id,
    )

    response = generate(
        "expert",
        profile.system_prompt,
        user_prompt,
        temperature=0.1,
        response_schema=ExpertVerdict,
    )

    verdict = ExpertVerdict.model_validate_json(response)
    vr_log.info(
        MODULE,
        "expert_done",
        f"Expert {profile.expert_id}: {verdict.verdict.value} "
        f"({len(verdict.findings)} findings)",
        expert_id=profile.expert_id,
        verdict=verdict.verdict.value,
        findings_count=len(verdict.findings),
        confidence=verdict.confidence,
    )
    return verdict


def run(
    application_record: ApplicationRecord, profiles_dir: Path
) -> list[ExpertVerdict]:
    """Dispatch application to all experts and collect verdicts."""
    profiles = _load_profiles(profiles_dir)
    if not profiles:
        vr_log.error(MODULE, "no_profiles", f"No profiles found in {profiles_dir}")
        sys.exit(1)

    vr_log.info(
        MODULE,
        "orchestrate_start",
        f"Dispatching to {len(profiles)} expert(s)",
        application_id=application_record.application_id,
        expert_count=len(profiles),
    )

    verdicts: list[ExpertVerdict] = []
    with ThreadPoolExecutor(max_workers=len(profiles)) as executor:
        futures = {
            executor.submit(_run_expert, p, application_record): p
            for p in profiles
        }
        for future in as_completed(futures):
            profile = futures[future]
            try:
                verdict = future.result()
                verdicts.append(verdict)
            except Exception as e:
                vr_log.error(
                    MODULE,
                    "expert_error",
                    f"Expert {profile.expert_id} failed: {e}",
                    expert_id=profile.expert_id,
                    error=str(e),
                )

    vr_log.info(
        MODULE,
        "orchestrate_done",
        f"Collected {len(verdicts)} verdict(s)",
        application_id=application_record.application_id,
        verdicts_count=len(verdicts),
    )
    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Route ApplicationRecord to expert models and collect verdicts"
    )
    parser.add_argument(
        "--profiles-dir",
        type=Path,
        default=Path("profiles"),
        help="Directory containing ExpertProfile JSON files (default: profiles/)",
    )
    args = parser.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        vr_log.error(MODULE, "empty_input", "No input provided on stdin")
        sys.exit(1)

    data = json.loads(raw)

    # Accept either IntakeOutput (has .record) or raw ApplicationRecord
    if "record" in data:
        record = ApplicationRecord.model_validate(data["record"])
    else:
        record = ApplicationRecord.model_validate(data)

    verdicts = run(record, args.profiles_dir)

    output_json = json.dumps(
        [v.model_dump(mode="json") for v in verdicts],
        indent=2,
        ensure_ascii=False,
    )

    input_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]
    output_hash = hashlib.sha256(output_json.encode()).hexdigest()[:16]
    vr_log.info(
        MODULE,
        "output",
        "Writing ExpertVerdict[] to stdout",
        input_hash=f"sha256:{input_hash}",
        output_hash=f"sha256:{output_hash}",
    )

    print(output_json)


if __name__ == "__main__":
    main()
