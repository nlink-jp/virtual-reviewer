"""Tests for vr-questions and vr-answers modules."""

from virtual_reviewer.models import (
    ApplicationRecord,
    IntakeOutput,
    IntakeQuestion,
)
from virtual_reviewer.questions import render
from virtual_reviewer.answers import parse_qa_sheet, run


class TestQuestionsRender:
    def _make_output(self, questions=None) -> IntakeOutput:
        record = ApplicationRecord(
            application_id="APP-2024-0001",
        )
        record.applicant.name = "田中太郎"
        record.applicant.department = "営業企画部"
        return IntakeOutput(
            record=record,
            questions=questions or [],
        )

    def test_header(self):
        output = self._make_output(
            questions=[
                IntakeQuestion(
                    field="data_stores",
                    question="暗号化方式は何ですか？",
                    reason="データ保護規定の評価に必要",
                )
            ]
        )
        md = render(output)
        assert "セキュリティレビュー 追加質問シート" in md
        assert "APP-2024-0001" in md
        assert "田中太郎" in md
        assert "営業企画部" in md

    def test_questions_rendered(self):
        output = self._make_output(
            questions=[
                IntakeQuestion(
                    field="data_stores",
                    question="暗号化方式は何ですか？",
                    reason="データ保護規定の評価に必要",
                ),
                IntakeQuestion(
                    field="services",
                    question="SLAの内容は？",
                    reason="可用性評価に必要",
                ),
            ]
        )
        md = render(output)
        assert "## 質問 1" in md
        assert "## 質問 2" in md
        assert "`data_stores`" in md
        assert "暗号化方式は何ですか？" in md
        assert "（ここに回答を記入してください）" in md

    def test_no_questions(self):
        output = self._make_output(questions=[])
        md = render(output)
        assert "追加質問はありません" in md


class TestAnswersParse:
    def test_parse_filled_sheet(self):
        markdown = """\
# セキュリティレビュー 追加質問シート

- **申請ID**: APP-2024-0001

## 質問 1

- **対象項目**: `data_stores`
- **質問理由**: データ保護規定の評価に必要

**質問**: 暗号化方式は何ですか？

**回答**:

```
AES-256で保存時暗号化を実施しています
```

## 質問 2

- **対象項目**: `services`
- **質問理由**: 可用性評価に必要

**質問**: SLAの内容は？

**回答**:

```
稼働率99.9%のSLAが提供されています
```
"""
        answers = parse_qa_sheet(markdown)
        assert len(answers) == 2
        assert answers[0]["field"] == "data_stores"
        assert "AES-256" in answers[0]["response"]
        assert answers[1]["field"] == "services"
        assert "99.9%" in answers[1]["response"]

    def test_skip_unanswered(self):
        markdown = """\
## 質問 1

- **対象項目**: `data_stores`
- **質問理由**: 必要

**質問**: 暗号化方式は？

**回答**:

```
（ここに回答を記入してください）
```
"""
        answers = parse_qa_sheet(markdown)
        assert len(answers) == 0

    def test_partial_answers(self):
        markdown = """\
## 質問 1

- **対象項目**: `data_stores`
- **質問理由**: 必要

**質問**: 暗号化方式は？

**回答**:

```
AES-256
```

## 質問 2

- **対象項目**: `services`
- **質問理由**: 必要

**質問**: SLAは？

**回答**:

```
（ここに回答を記入してください）
```
"""
        answers = parse_qa_sheet(markdown)
        assert len(answers) == 1
        assert answers[0]["field"] == "data_stores"


class TestAnswersRun:
    def test_produces_intake_input(self):
        output = IntakeOutput(
            record=ApplicationRecord(
                application_id="APP-0001",
                system_overview="テストシステム",
            ),
            questions=[
                IntakeQuestion(
                    field="data_stores",
                    question="暗号化方式は？",
                    reason="必要",
                ),
            ],
        )

        qa_markdown = """\
## 質問 1

- **対象項目**: `data_stores`
- **質問理由**: 必要

**質問**: 暗号化方式は？

**回答**:

```
AES-256
```
"""
        result = run(output, qa_markdown)
        assert result.answers is not None
        assert len(result.answers) == 1
        assert result.answers[0].field == "data_stores"
        assert result.answers[0].response == "AES-256"
        assert len(result.materials) == 1
