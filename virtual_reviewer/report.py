"""vr-report: Report Generator.

Reads FinalAssessment JSON from stdin and outputs a human-readable
Markdown report to stdout. Pure transformation, no LLM call.

Usage:
    cat assessment.json | vr-report
    cat verdicts.json | vr-brain | tee assessment.json | vr-report > report.md
"""

from __future__ import annotations

import sys

from virtual_reviewer.models import (
    FinalAssessment,
    Finding,
    OverallVerdict,
    Severity,
)

MODULE = "report"

VERDICT_LABEL = {
    OverallVerdict.approved: "承認",
    OverallVerdict.rejected: "却下",
    OverallVerdict.conditional: "条件付き承認",
}

SEVERITY_LABEL = {
    Severity.critical: "Critical（重大）",
    Severity.high: "High（高）",
    Severity.medium: "Medium（中）",
    Severity.low: "Low（低）",
    Severity.info: "Info（情報）",
}

SEVERITY_ORDER = [
    Severity.critical,
    Severity.high,
    Severity.medium,
    Severity.low,
    Severity.info,
]


def _findings_by_severity(findings: list[Finding]) -> dict[Severity, list[Finding]]:
    grouped: dict[Severity, list[Finding]] = {}
    for f in findings:
        grouped.setdefault(f.severity, []).append(f)
    return grouped


def render(assessment: FinalAssessment) -> str:
    """Render a FinalAssessment as a Markdown report."""
    lines: list[str] = []

    # Header
    verdict = VERDICT_LABEL[assessment.overall_verdict]
    lines.append(f"# セキュリティレビュー判定結果 — {verdict}")
    lines.append("")
    lines.append(f"- **判定ID**: {assessment.assessment_id}")
    if assessment.application_id:
        lines.append(f"- **申請ID**: {assessment.application_id}")
    lines.append(f"- **判定日時**: {assessment.assessed_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"- **総合判定**: **{verdict}**")
    lines.append("")

    # Risk Summary
    rs = assessment.risk_summary
    lines.append("## リスクサマリー")
    lines.append("")
    lines.append("| 深刻度 | 件数 |")
    lines.append("|--------|------|")
    lines.append(f"| Critical（重大） | {rs.critical} |")
    lines.append(f"| High（高） | {rs.high} |")
    lines.append(f"| Medium（中） | {rs.medium} |")
    lines.append(f"| Low（低） | {rs.low} |")
    lines.append(f"| Info（情報） | {rs.info} |")
    lines.append("")

    # Conditions
    if assessment.conditions:
        lines.append("## 承認条件")
        lines.append("")
        lines.append("本申請の承認にあたり、以下の条件を**すべて**満たす必要があります:")
        lines.append("")
        for i, cond in enumerate(assessment.conditions, 1):
            lines.append(f"{i}. {cond}")
        lines.append("")

    # Conflicts
    if assessment.conflicts:
        lines.append("## 専門家間の矛盾")
        lines.append("")
        for conflict in assessment.conflicts:
            lines.append(
                f"- **{conflict.expert_a}** vs **{conflict.expert_b}** "
                f"（対象: `{conflict.target_field}`）"
            )
            lines.append(f"  - 内容: {conflict.description}")
            lines.append(f"  - 解消: {conflict.resolution}")
        lines.append("")

    # Findings
    if assessment.findings:
        lines.append("## 指摘事項の詳細")
        lines.append("")
        grouped = _findings_by_severity(assessment.findings)
        for severity in SEVERITY_ORDER:
            findings = grouped.get(severity, [])
            if not findings:
                continue
            lines.append(f"### {SEVERITY_LABEL[severity]}")
            lines.append("")
            for f in findings:
                lines.append(f"#### [{f.regulation_ref}] {f.target_field}")
                lines.append("")
                lines.append(f"**指摘内容**: {f.finding}")
                lines.append("")
                if f.recommendation:
                    lines.append(f"**推奨対策**: {f.recommendation}")
                    lines.append("")

    # Metadata
    if assessment.model_versions:
        lines.append("---")
        lines.append("")
        lines.append("## メタデータ")
        lines.append("")
        lines.append("| 項目 | 値 |")
        lines.append("|------|---|")
        for k, v in assessment.model_versions.items():
            lines.append(f"| モデル ({k}) | {v} |")
        if assessment.evidence_chain:
            for step in assessment.evidence_chain:
                lines.append(
                    f"| 証跡 ステップ{step.step} ({step.module}) "
                    f"| in:`{step.input_hash[:24]}` out:`{step.output_hash[:24]}` |"
                )
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        print("Error: No input provided on stdin", file=sys.stderr)
        sys.exit(1)

    assessment = FinalAssessment.model_validate_json(raw)
    print(render(assessment))


if __name__ == "__main__":
    main()
