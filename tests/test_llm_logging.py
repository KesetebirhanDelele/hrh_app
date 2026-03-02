"""Unit tests for structured LLM call logging in generate_json."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# Compatibility guard: openai < 1.0 doesn't export OpenAI class.
if not hasattr(sys.modules.get("openai"), "OpenAI"):
    _openai_stub = MagicMock()
    _openai_stub.OpenAI = MagicMock
    _openai_stub.RateLimitError = type("RateLimitError", (Exception,), {})
    sys.modules["openai"] = _openai_stub
    sys.modules.pop("app.analyze.llm", None)


def _make_fake_resp(response_text: str = '{"ok": true}', include_usage: bool = True):
    fake_resp = MagicMock()
    fake_resp.choices[0].message.content = response_text
    if include_usage:
        fake_resp.usage.prompt_tokens = 100
        fake_resp.usage.completion_tokens = 50
        fake_resp.usage.total_tokens = 150
    else:
        fake_resp.usage = None
    return fake_resp


def _patch_openai(monkeypatch, fake_resp):
    import app.analyze.llm as llm_mod

    mock_create = MagicMock(return_value=fake_resp)
    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create
    monkeypatch.setattr(llm_mod, "OpenAI", MagicMock(return_value=mock_client))
    return mock_create


# ---------------------------------------------------------------------------
# Settings line
# ---------------------------------------------------------------------------

def test_settings_line_contains_required_fields(monkeypatch, capsys):
    """The pre-call log line must include job_id, model, temperature, max_completion_tokens."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("HRH_OPENAI_MODEL", "gpt-4o")

    import app.analyze.llm as llm_mod
    _patch_openai(monkeypatch, _make_fake_resp())

    llm_mod.generate_json("prompt", job_id="domain_solutions_from_evidence")

    out = capsys.readouterr().out
    settings_line = next(l for l in out.splitlines() if l.startswith("[LLM] job_id="))
    assert "job_id=domain_solutions_from_evidence" in settings_line
    assert "model=gpt-4o" in settings_line
    assert "temperature=0" in settings_line
    assert "max_completion_tokens=16384" in settings_line


def test_settings_line_temperature_unset_for_other_jobs(monkeypatch, capsys):
    """temperature=unset logged for jobs outside the structured-extraction set."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    _patch_openai(monkeypatch, _make_fake_resp())

    llm_mod.generate_json("prompt", job_id="rrr_evidence_matrix")

    out = capsys.readouterr().out
    settings_line = next(l for l in out.splitlines() if l.startswith("[LLM] job_id="))
    assert "temperature=unset" in settings_line
    assert "job_id=rrr_evidence_matrix" in settings_line


def test_settings_line_excerpts_logged_when_provided(monkeypatch, capsys):
    """n_excerpts and total_chars appear in the settings line when passed."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    _patch_openai(monkeypatch, _make_fake_resp())

    llm_mod.generate_json("prompt", job_id="rrr_evidence_matrix", n_excerpts=42, total_chars=78000)

    out = capsys.readouterr().out
    settings_line = next(l for l in out.splitlines() if l.startswith("[LLM] job_id="))
    assert "n_excerpts=42" in settings_line
    assert "total_chars=78000" in settings_line


def test_settings_line_excerpts_na_when_not_provided(monkeypatch, capsys):
    """n_excerpts and total_chars show n/a when omitted."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    _patch_openai(monkeypatch, _make_fake_resp())

    llm_mod.generate_json("prompt")

    out = capsys.readouterr().out
    settings_line = next(l for l in out.splitlines() if l.startswith("[LLM] job_id="))
    assert "n_excerpts=n/a" in settings_line
    assert "total_chars=n/a" in settings_line


# ---------------------------------------------------------------------------
# Usage line
# ---------------------------------------------------------------------------

def test_usage_tokens_logged_when_present(monkeypatch, capsys):
    """Token counts are logged after a successful response."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    _patch_openai(monkeypatch, _make_fake_resp(include_usage=True))

    llm_mod.generate_json("prompt")

    out = capsys.readouterr().out
    usage_line = next(l for l in out.splitlines() if l.startswith("[LLM] usage:"))
    assert "prompt_tokens=100" in usage_line
    assert "completion_tokens=50" in usage_line
    assert "total_tokens=150" in usage_line


def test_missing_usage_handled_safely(monkeypatch, capsys):
    """When resp.usage is None, 'unavailable' is logged and no exception is raised."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    _patch_openai(monkeypatch, _make_fake_resp(include_usage=False))

    # Must not raise
    llm_mod.generate_json("prompt")

    out = capsys.readouterr().out
    usage_line = next(l for l in out.splitlines() if l.startswith("[LLM] usage:"))
    assert "unavailable" in usage_line
