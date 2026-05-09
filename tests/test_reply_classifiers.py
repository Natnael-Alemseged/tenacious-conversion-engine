from __future__ import annotations

import logging

from agent.workflows.reply_intent import classify_reply_intent
from agent.workflows.warm_reply_classifier import classify_warm_reply


class FakeClient:
    def __init__(self, content: str) -> None:
        self.content = content

    def generate_text(self, **_: object) -> str:
        return self.content


def test_reply_intent_logs_parse_failure_without_raw_content(caplog) -> None:
    caplog.set_level(logging.WARNING)
    raw = "not json: prospect@example.com wants pricing"

    result = classify_reply_intent(
        subject="Pricing",
        body="Can you send pricing?",
        client=FakeClient(raw),
    )

    assert result.intent == "other"
    assert result.confidence == 0.0
    assert result.notes == "parse_failed"
    assert "reply_intent_parse_failed" in caplog.text
    assert raw not in caplog.text


def test_reply_intent_logs_invalid_intent_without_raw_content(caplog) -> None:
    caplog.set_level(logging.WARNING)

    result = classify_reply_intent(
        subject="Pricing",
        body="Can you send pricing?",
        client=FakeClient('{"intent": "unsupported", "confidence": 0.8, "notes": "x"}'),
    )

    assert result.intent == "other"
    assert result.confidence == 0.0
    assert result.notes == "invalid_intent"
    assert "reply_intent_invalid_intent" in caplog.text


def test_warm_reply_logs_parse_failure_and_marks_fallback(caplog) -> None:
    caplog.set_level(logging.WARNING)
    raw = "not json: remove prospect@example.com"

    result = classify_warm_reply(
        subject="Re: hello",
        body="Please remove me from this list.",
        client=FakeClient(raw),
    )

    assert result.reply_class == "hard_no"
    assert result.confidence == 0.9
    assert result.notes == "parse_failed:heuristic_hard_no"
    assert "warm_reply_parse_failed" in caplog.text
    assert raw not in caplog.text


def test_warm_reply_logs_invalid_class_and_marks_fallback(caplog) -> None:
    caplog.set_level(logging.WARNING)

    result = classify_warm_reply(
        subject="Re: hello",
        body="Can you send more info?",
        client=FakeClient('{"reply_class": "mystery", "confidence": 0.7}'),
    )

    assert result.reply_class == "curious"
    assert result.notes == "invalid_class:heuristic_curious"
    assert "warm_reply_invalid_class" in caplog.text
