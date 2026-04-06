"""Tests for vr-report module."""

from virtual_reviewer.models import (
    Conflict,
    FinalAssessment,
    Finding,
    OverallVerdict,
    RiskSummary,
    Severity,
)
from virtual_reviewer.report import render


class TestRender:
    def _make_assessment(self, **kwargs) -> FinalAssessment:
        defaults = {
            "assessment_id": "ASM-TEST",
            "application_id": "APP-TEST",
            "overall_verdict": OverallVerdict.conditional,
            "conditions": ["MFAを有効化すること"],
            "risk_summary": RiskSummary(critical=0, high=1, medium=0, low=0, info=0),
            "findings": [
                Finding(
                    regulation_ref="1.2",
                    target_field="services[0].auth_method",
                    severity=Severity.high,
                    finding="MFAが未設定",
                    recommendation="MFAを有効化すること",
                )
            ],
        }
        defaults.update(kwargs)
        return FinalAssessment(**defaults)

    def test_header_contains_verdict(self):
        md = render(self._make_assessment())
        assert "条件付き承認" in md
        assert "ASM-TEST" in md
        assert "APP-TEST" in md

    def test_conditions_section(self):
        md = render(self._make_assessment(conditions=["対策A", "対策B"]))
        assert "承認条件" in md
        assert "1. 対策A" in md
        assert "2. 対策B" in md

    def test_no_conditions_when_approved(self):
        md = render(
            self._make_assessment(
                overall_verdict=OverallVerdict.approved,
                conditions=[],
            )
        )
        assert "承認条件" not in md

    def test_findings_grouped_by_severity(self):
        findings = [
            Finding(
                regulation_ref="1.1",
                target_field="a",
                severity=Severity.low,
                finding="軽微な問題",
            ),
            Finding(
                regulation_ref="2.1",
                target_field="b",
                severity=Severity.critical,
                finding="重大な問題",
            ),
        ]
        md = render(self._make_assessment(findings=findings))
        crit_pos = md.index("Critical（重大）")
        low_pos = md.index("Low（低）")
        assert crit_pos < low_pos

    def test_conflicts_section(self):
        conflicts = [
            Conflict(
                expert_a="auth",
                expert_b="data",
                target_field="services[0]",
                description="判定の不一致",
                resolution="データ保護を優先",
            )
        ]
        md = render(self._make_assessment(conflicts=conflicts))
        assert "専門家間の矛盾" in md
        assert "auth" in md
        assert "データ保護を優先" in md

    def test_no_conflicts_section_when_empty(self):
        md = render(self._make_assessment(conflicts=[]))
        assert "専門家間の矛盾" not in md

    def test_approved_report(self):
        md = render(
            self._make_assessment(
                overall_verdict=OverallVerdict.approved,
                conditions=[],
                findings=[],
                risk_summary=RiskSummary(),
            )
        )
        assert "承認" in md

    def test_rejected_report(self):
        md = render(
            self._make_assessment(
                overall_verdict=OverallVerdict.rejected,
            )
        )
        assert "却下" in md
