from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

# Compatibility guard: openai < 1.0 (Python 3.11 env) doesn't export the `OpenAI`
# class. Inject a minimal stub so app.analyze.llm can be imported for unit-testing
# regardless of which openai package version is installed.
if not hasattr(sys.modules.get("openai"), "OpenAI"):
    _openai_stub = MagicMock()
    _openai_stub.OpenAI = MagicMock
    _openai_stub.RateLimitError = type("RateLimitError", (Exception,), {})
    sys.modules["openai"] = _openai_stub
    sys.modules.pop("app.analyze.llm", None)  # force re-import against our stub


def _mock_openai(monkeypatch, response_text: str = '{"ok": true}'):
    """Patch app.analyze.llm.OpenAI; return the mock create() callable."""
    import app.analyze.llm as llm_mod

    fake_resp = MagicMock()
    fake_resp.choices[0].message.content = response_text
    mock_create = MagicMock(return_value=fake_resp)
    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create
    monkeypatch.setattr(llm_mod, "OpenAI", MagicMock(return_value=mock_client))
    return mock_create


def test_temperature_zero_for_domain_solutions(monkeypatch):
    """generate_json passes temperature=0 when job_id == 'domain_solutions_from_evidence'."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    mock_create = _mock_openai(monkeypatch)

    llm_mod.generate_json("test prompt", job_id="domain_solutions_from_evidence")

    assert mock_create.call_args.kwargs.get("temperature") == 0


def test_temperature_zero_for_domain_lessons(monkeypatch):
    """generate_json passes temperature=0 when job_id == 'domain_lessons_option_b'."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    mock_create = _mock_openai(monkeypatch)

    llm_mod.generate_json("test prompt", job_id="domain_lessons_option_b")

    assert mock_create.call_args.kwargs.get("temperature") == 0


def test_max_completion_tokens_set_for_structured_jobs(monkeypatch):
    """generate_json passes max_completion_tokens=16384 for both structured extraction jobs."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod

    for job_id in ("domain_solutions_from_evidence", "domain_lessons_option_b"):
        mock_create = _mock_openai(monkeypatch)
        llm_mod.generate_json("test prompt", job_id=job_id)
        assert mock_create.call_args.kwargs.get("max_completion_tokens") == 16384, job_id


def test_max_completion_tokens_absent_for_other_jobs(monkeypatch):
    """generate_json does NOT set max_completion_tokens for non-structured jobs."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    mock_create = _mock_openai(monkeypatch)

    llm_mod.generate_json("test prompt", job_id="rrr_evidence_matrix")

    assert "max_completion_tokens" not in mock_create.call_args.kwargs


def test_no_temperature_for_other_job(monkeypatch):
    """generate_json does NOT set temperature for other job IDs."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    mock_create = _mock_openai(monkeypatch)

    llm_mod.generate_json("test prompt", job_id="rrr_evidence_matrix")

    assert "temperature" not in mock_create.call_args.kwargs


def test_no_temperature_when_job_id_omitted(monkeypatch):
    """generate_json does NOT set temperature when job_id is not provided."""
    monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    import app.analyze.llm as llm_mod
    mock_create = _mock_openai(monkeypatch)

    llm_mod.generate_json("test prompt")

    assert "temperature" not in mock_create.call_args.kwargs
