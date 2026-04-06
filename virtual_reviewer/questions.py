"""vr-questions: Q&A Sheet Generator.

Reads IntakeOutput JSON from stdin and outputs a Markdown Q&A sheet
for the applicant to fill in. Pure transformation, no LLM call.

Usage:
    cat intake_output.json | vr-questions > qa_sheet.md

After the applicant fills in the answers, convert back to IntakeInput:
    cat intake_output.json | vr-answers qa_sheet.md > intake_input_pass2.json
"""

from __future__ import annotations

import sys

from virtual_reviewer.models import IntakeOutput

MODULE = "questions"


def render(output: IntakeOutput) -> str:
    """Render an IntakeOutput's questions as a Markdown Q&A sheet."""
    lines: list[str] = []

    lines.append("# セキュリティレビュー 追加質問シート")
    lines.append("")
    if output.record.application_id:
        lines.append(f"- **申請ID**: {output.record.application_id}")
    if output.record.applicant.name:
        lines.append(f"- **申請者**: {output.record.applicant.name}")
    if output.record.applicant.department:
        lines.append(f"- **部署**: {output.record.applicant.department}")
    lines.append("")

    if not output.questions:
        lines.append("追加質問はありません。申請内容は十分です。")
        return "\n".join(lines)

    lines.append("以下の項目について追加情報をご回答ください。")
    lines.append("「回答」欄に記入のうえ、セキュリティ部門へご返送ください。")
    lines.append("")

    for i, q in enumerate(output.questions, 1):
        lines.append(f"## 質問 {i}")
        lines.append("")
        lines.append(f"- **対象項目**: `{q.field}`")
        lines.append(f"- **質問理由**: {q.reason}")
        lines.append("")
        lines.append(f"**質問**: {q.question}")
        lines.append("")
        lines.append("**回答**:")
        lines.append("")
        lines.append("```")
        lines.append("（ここに回答を記入してください）")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        print("Error: No input provided on stdin", file=sys.stderr)
        sys.exit(1)

    output = IntakeOutput.model_validate_json(raw)
    print(render(output))


if __name__ == "__main__":
    main()
