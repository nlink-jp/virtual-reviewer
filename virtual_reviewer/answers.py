"""vr-answers: Q&A Sheet Parser.

Reads IntakeOutput JSON from stdin and a filled-in Q&A Markdown sheet,
then produces IntakeInput JSON for the second pass of vr-intake.

Usage:
    cat intake_output.json | vr-answers qa_sheet_filled.md > intake_pass2.json
    cat intake_pass2.json | vr-intake --profiles-dir profiles/
"""

from __future__ import annotations

import argparse
import re
import sys

from virtual_reviewer.models import IntakeAnswer, IntakeInput, IntakeOutput, MaterialItem

MODULE = "answers"


def parse_qa_sheet(markdown: str) -> list[dict[str, str]]:
    """Parse a filled-in Q&A Markdown sheet and extract answers.

    Expected format per question block:
        ## 質問 N
        - **対象項目**: `field_name`
        ...
        **質問**: question text
        **回答**:
        ```
        answer text
        ```
    """
    answers: list[dict[str, str]] = []

    blocks = re.split(r"^## 質問 \d+", markdown, flags=re.MULTILINE)

    for block in blocks[1:]:  # skip header before first question
        field_match = re.search(r"\*\*対象項目\*\*:\s*`([^`]+)`", block)
        question_match = re.search(r"\*\*質問\*\*:\s*(.+)", block)
        answer_match = re.search(r"\*\*回答\*\*:\s*\n+```\n(.*?)\n```", block, re.DOTALL)

        if not all([field_match, question_match, answer_match]):
            continue

        answer_text = answer_match.group(1).strip()
        if answer_text == "（ここに回答を記入してください）":
            continue  # unanswered

        answers.append({
            "field": field_match.group(1),
            "question": question_match.group(1).strip(),
            "response": answer_text,
        })

    return answers


def run(intake_output: IntakeOutput, qa_markdown: str) -> IntakeInput:
    """Combine original materials with answers into a second-pass IntakeInput."""
    parsed = parse_qa_sheet(qa_markdown)

    intake_answers = [
        IntakeAnswer(
            field=a["field"],
            question=a["question"],
            response=a["response"],
        )
        for a in parsed
    ]

    # Reconstruct materials from the original record as text
    materials = [
        MaterialItem(
            type="text",
            content=intake_output.record.model_dump_json(indent=2, ensure_ascii=False),
        )
    ]

    return IntakeInput(
        materials=materials,
        answers=intake_answers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse filled Q&A sheet and produce IntakeInput for second pass"
    )
    parser.add_argument(
        "qa_sheet",
        help="Path to the filled-in Q&A Markdown sheet",
    )
    args = parser.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        print("Error: No input on stdin (expected IntakeOutput JSON)", file=sys.stderr)
        sys.exit(1)

    intake_output = IntakeOutput.model_validate_json(raw)

    qa_markdown = open(args.qa_sheet, encoding="utf-8").read()

    result = run(intake_output, qa_markdown)
    print(result.model_dump_json(indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
