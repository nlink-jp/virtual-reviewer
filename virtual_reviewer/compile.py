"""vr-compile: Persona Compiler.

Reads regulation Markdown from stdin, splits it into semantic units,
and generates ExpertProfile JSON files in the output directory.

Usage:
    vr-compile --output-dir profiles/ < regulations.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from virtual_reviewer import log as vr_log
from virtual_reviewer.llm import generate
from virtual_reviewer.models import ExpertProfile


class ExpertProfileList(BaseModel):
    """Wrapper for LLM response schema — list of expert profiles."""

    profiles: list[ExpertProfile] = Field(description="List of expert profiles")

MODULE = "compiler"

SYSTEM_PROMPT = """\
あなたはセキュリティ規定の分析者です。
セキュリティ規定文書を独立した専門領域に分割してください。

各領域（通常は章単位）について ExpertProfile を生成してください:

1. expert_id: 短い kebab-case 識別子（例: "auth-access-control"）
2. domain: 人間が読める領域名（規定文書の言語で記述）
3. system_prompt: この領域の専門家レビュワーとして動作するLLMへのシステムプロンプト。
   以下を指示すること:
   - 担当規定に基づき申請を評価する
   - severity, regulation_ref, recommendation を含む構造化された指摘を出力する
   - 規定中の例外条件・否定条件を漏れなく考慮する
   - すべてのテキスト出力（finding, recommendation 等）は日本語で記述する
4. regulation_text: この領域の規定セクション全文
5. required_fields: この専門家が必要とする ApplicationRecord のフィールド
   （system_overview, data_flows, services, data_stores, applicant から選択）
6. regulation_refs: 対象セクションのIDとタイトルの一覧
7. version: デフォルトは "1.0.0"

JSON で応答してください。
"""


def run(regulation_text: str, output_dir: Path) -> list[ExpertProfile]:
    """Compile regulation text into expert profiles."""
    vr_log.info(MODULE, "compile_start", "Starting regulation compilation")

    user_prompt = f"""\
Split the following regulation document into expert domains and generate
an ExpertProfile for each domain.

---
{regulation_text}
---
"""
    response = generate(
        MODULE,
        SYSTEM_PROMPT,
        user_prompt,
        temperature=0.1,
        response_schema=ExpertProfileList,
    )

    result = ExpertProfileList.model_validate_json(response)
    profiles = result.profiles

    output_dir.mkdir(parents=True, exist_ok=True)
    for profile in profiles:
        out_path = output_dir / f"{profile.expert_id}.json"
        out_path.write_text(
            profile.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        vr_log.info(
            MODULE,
            "profile_written",
            f"Wrote {out_path}",
            expert_id=profile.expert_id,
            domain=profile.domain,
        )

    vr_log.info(
        MODULE,
        "compile_done",
        f"Generated {len(profiles)} expert profiles",
        count=len(profiles),
    )
    return profiles


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile regulation Markdown into ExpertProfile JSON files"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("profiles"),
        help="Directory to write ExpertProfile JSON files (default: profiles/)",
    )
    args = parser.parse_args()

    regulation_text = sys.stdin.read()
    if not regulation_text.strip():
        vr_log.error(MODULE, "empty_input", "No regulation text provided on stdin")
        sys.exit(1)

    run(regulation_text, args.output_dir)


if __name__ == "__main__":
    main()
