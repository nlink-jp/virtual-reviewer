"""Tests for data models — serialization, deserialization, validation."""

import json

from virtual_reviewer.models import (
    ApplicationRecord,
    Applicant,
    Conflict,
    DataClassification,
    DataFlow,
    DataStore,
    EncryptionType,
    EvidenceStep,
    ExpertProfile,
    ExpertVerdict,
    FinalAssessment,
    Finding,
    HostingType,
    IntakeAnswer,
    IntakeInput,
    IntakeOutput,
    IntakeQuestion,
    MaterialItem,
    OverallVerdict,
    RegulationRef,
    RiskSummary,
    Service,
    Severity,
    Verdict,
)


class TestApplicationRecord:
    def test_minimal(self):
        record = ApplicationRecord(system_overview="Test system")
        assert record.system_overview == "Test system"
        assert record.data_flows == []
        assert record.services == []

    def test_full_roundtrip(self):
        record = ApplicationRecord(
            application_id="APP-0001",
            applicant=Applicant(
                name="Taro", department="Engineering", contact="taro@example.com"
            ),
            system_overview="A test CRM system",
            data_flows=[
                DataFlow(
                    src="User",
                    dst="CRM",
                    data_type="Customer info",
                    classification=DataClassification.confidential,
                )
            ],
            services=[
                Service(
                    name="SalesHub",
                    vendor="SalesHub Inc.",
                    hosting=HostingType.saas,
                    auth_method="password",
                )
            ],
            data_stores=[
                DataStore(
                    type="cloud",
                    encryption=EncryptionType.both,
                    location="us-east-1",
                    retention="3 years",
                )
            ],
            confidence={"system_overview": 0.95, "data_flows": 0.8},
        )
        json_str = record.model_dump_json()
        restored = ApplicationRecord.model_validate_json(json_str)
        assert restored.application_id == "APP-0001"
        assert restored.data_flows[0].classification == DataClassification.confidential
        assert restored.services[0].hosting == HostingType.saas
        assert restored.confidence["data_flows"] == 0.8

    def test_from_dict(self):
        data = {
            "application_id": "APP-0002",
            "system_overview": "Test",
            "services": [{"name": "Foo", "hosting": "saas"}],
        }
        record = ApplicationRecord.model_validate(data)
        assert record.services[0].name == "Foo"


class TestExpertProfile:
    def test_roundtrip(self):
        profile = ExpertProfile(
            expert_id="auth-access-control",
            domain="Authentication & Access Control",
            system_prompt="You are an authentication expert.",
            regulation_text="## 1.1 Authentication requirements\n...",
            required_fields=["services", "data_flows"],
            regulation_refs=[
                RegulationRef(section_id="1.1", title="Authentication requirements"),
                RegulationRef(section_id="1.2", title="MFA requirements"),
            ],
            version="1.0.0",
        )
        json_str = profile.model_dump_json()
        restored = ExpertProfile.model_validate_json(json_str)
        assert restored.expert_id == "auth-access-control"
        assert len(restored.regulation_refs) == 2
        assert "services" in restored.required_fields


class TestExpertVerdict:
    def test_roundtrip(self):
        verdict = ExpertVerdict(
            expert_id="auth-access-control",
            verdict=Verdict.conditional,
            findings=[
                Finding(
                    regulation_ref="1.2",
                    target_field="services[0].auth_method",
                    severity=Severity.high,
                    finding="MFA is not configured",
                    recommendation="Enable MFA for all users",
                )
            ],
            confidence=0.9,
        )
        json_str = verdict.model_dump_json()
        restored = ExpertVerdict.model_validate_json(json_str)
        assert restored.verdict == Verdict.conditional
        assert restored.findings[0].severity == Severity.high

    def test_verdict_enum_values(self):
        assert Verdict.passed.value == "pass"
        assert Verdict.fail.value == "fail"


class TestFinalAssessment:
    def test_roundtrip(self):
        assessment = FinalAssessment(
            assessment_id="ASM-0001",
            application_id="APP-0001",
            overall_verdict=OverallVerdict.conditional,
            conditions=["Enable MFA", "Move data to JP region"],
            conflicts=[
                Conflict(
                    expert_a="auth",
                    expert_b="data-protection",
                    target_field="services[0]",
                    description="Auth allows, data protection rejects",
                    resolution="Data protection takes precedence",
                )
            ],
            risk_summary=RiskSummary(critical=0, high=2, medium=1, low=0, info=1),
            findings=[
                Finding(
                    regulation_ref="1.2",
                    target_field="services[0].auth_method",
                    severity=Severity.high,
                    finding="MFA not configured",
                    recommendation="Enable MFA",
                )
            ],
            model_versions={"brain": "gemini-2.5-pro"},
        )
        json_str = assessment.model_dump_json()
        restored = FinalAssessment.model_validate_json(json_str)
        assert restored.overall_verdict == OverallVerdict.conditional
        assert restored.risk_summary.high == 2
        assert len(restored.conflicts) == 1


class TestIntakeIO:
    def test_intake_input_first_pass(self):
        inp = IntakeInput(
            materials=[
                MaterialItem(type="text", content="Test application"),
            ],
            answers=None,
        )
        assert inp.answers is None
        json_str = inp.model_dump_json()
        restored = IntakeInput.model_validate_json(json_str)
        assert restored.answers is None

    def test_intake_input_second_pass(self):
        inp = IntakeInput(
            materials=[MaterialItem(type="text", content="Test")],
            answers=[
                IntakeAnswer(
                    field="data_stores",
                    question="Where is data stored?",
                    response="AWS S3 in ap-northeast-1",
                )
            ],
        )
        assert len(inp.answers) == 1

    def test_intake_input_with_file(self):
        inp = IntakeInput(
            materials=[
                MaterialItem(type="text", content="See attached diagram"),
                MaterialItem(
                    type="file", path="/tmp/diagram.png", mime_type="image/png"
                ),
            ],
        )
        assert inp.materials[1].path == "/tmp/diagram.png"

    def test_intake_output_with_questions(self):
        record = ApplicationRecord(
            application_id="APP-0001",
            system_overview="Test",
        )
        output = IntakeOutput(
            record=record,
            questions=[
                IntakeQuestion(
                    field="data_stores",
                    question="Where is data stored?",
                    reason="Required for data protection evaluation",
                )
            ],
        )
        json_str = output.model_dump_json()
        restored = IntakeOutput.model_validate_json(json_str)
        assert len(restored.questions) == 1
        assert restored.record.application_id == "APP-0001"

    def test_intake_output_complete(self):
        record = ApplicationRecord(
            application_id="APP-0001",
            system_overview="Test",
        )
        output = IntakeOutput(record=record, questions=[])
        assert output.questions == []


class TestPipelineDataFlow:
    """Test that data flows correctly between module boundaries."""

    def test_intake_to_orchestrator(self):
        """Orchestrator can extract record from IntakeOutput."""
        record = ApplicationRecord(
            application_id="APP-0001",
            system_overview="Test system",
            services=[Service(name="TestSvc", auth_method="SSO")],
        )
        intake_output = IntakeOutput(record=record, questions=[])
        data = json.loads(intake_output.model_dump_json())

        # Orchestrator extracts .record from IntakeOutput
        assert "record" in data
        extracted = ApplicationRecord.model_validate(data["record"])
        assert extracted.application_id == "APP-0001"

    def test_orchestrator_to_brain(self):
        """Brain can parse ExpertVerdict[] JSON array."""
        verdicts = [
            ExpertVerdict(
                expert_id="auth",
                verdict=Verdict.passed,
                findings=[],
                confidence=0.95,
            ),
            ExpertVerdict(
                expert_id="data-protection",
                verdict=Verdict.conditional,
                findings=[
                    Finding(
                        regulation_ref="2.2",
                        target_field="data_stores[0].encryption",
                        severity=Severity.high,
                        finding="No encryption",
                        recommendation="Enable encryption",
                    )
                ],
                confidence=0.9,
            ),
        ]
        json_str = json.dumps(
            [v.model_dump(mode="json") for v in verdicts],
            ensure_ascii=False,
        )
        restored = [ExpertVerdict.model_validate(v) for v in json.loads(json_str)]
        assert len(restored) == 2
        assert restored[1].findings[0].severity == Severity.high
