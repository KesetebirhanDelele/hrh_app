from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# openai stub (same guard as test_llm_temperature.py)
# ---------------------------------------------------------------------------
if not hasattr(sys.modules.get("openai"), "OpenAI"):
    _openai_stub = MagicMock()
    _openai_stub.OpenAI = MagicMock
    _openai_stub.RateLimitError = type("RateLimitError", (Exception,), {})
    _openai_stub.APIConnectionError = type("APIConnectionError", (Exception,), {})
    sys.modules["openai"] = _openai_stub
    sys.modules.pop("app.analyze.llm", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_response(content: str = '{"ok": true}') -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    resp.usage = None
    return resp


def _mock_openai_client(monkeypatch, side_effects: list):
    """
    Patch llm_mod.OpenAI so that create() yields *side_effects* in order.
    Each element is either an exception instance (raised) or None (success).
    After the list is exhausted, returns a successful response.
    """
    import app.analyze.llm as llm_mod

    call_idx = {"n": 0}

    def _create(**kwargs):
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(side_effects) and side_effects[idx] is not None:
            raise side_effects[idx]
        return _fake_response()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _create
    monkeypatch.setattr(llm_mod, "OpenAI", MagicMock(return_value=mock_client))
    return mock_client


class _StubRateLimitError(Exception):
    """Lightweight stand-in for openai.RateLimitError with optional headers."""
    def __init__(self, message: str = "rate limited", headers: dict | None = None) -> None:
        super().__init__(message)
        _fake = MagicMock()
        _fake.headers = headers or {}
        self.response = _fake


class _StubAPIConnectionError(Exception):
    """Lightweight stand-in for openai.APIConnectionError."""


def _make_rate_limit_error(retry_after: str | None = None) -> Exception:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return _StubRateLimitError(headers=headers)


def _make_conn_error() -> Exception:
    return _StubAPIConnectionError("connection failed")


def _patch_exc_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace RateLimitError and APIConnectionError in llm_mod with stubs."""
    import app.analyze.llm as llm_mod
    monkeypatch.setattr(llm_mod, "RateLimitError", _StubRateLimitError)
    monkeypatch.setattr(llm_mod, "APIConnectionError", _StubAPIConnectionError)


# ---------------------------------------------------------------------------
# Adaptive throttle tests
# ---------------------------------------------------------------------------

class TestAdaptiveThrottling:

    def test_no_sleep_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful call must not trigger any time.sleep."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("HRH_SOFT_RPS", raising=False)
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        sleep_calls: list[float] = []
        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleep_calls.append(s))
        _mock_openai_client(monkeypatch, [])  # no errors

        llm_mod.generate_json("test prompt", job_id="domain_lessons_option_b")

        assert sleep_calls == [], f"Expected no sleep on success; got {sleep_calls}"

    def test_rate_limit_uses_retry_after_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """On 429 with Retry-After: 10 header, sleep(10) is used."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("HRH_SOFT_RPS", raising=False)
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        sleep_calls: list[float] = []
        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleep_calls.append(s))
        _mock_openai_client(monkeypatch, [_make_rate_limit_error(retry_after="10")])

        llm_mod.generate_json("test prompt")

        assert len(sleep_calls) == 1, f"Expected 1 sleep; got {sleep_calls}"
        assert sleep_calls[0] == 10.0, f"Expected sleep(10), got sleep({sleep_calls[0]})"

    def test_rate_limit_exponential_backoff_no_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """On 429 without Retry-After, uses exponential backoff with jitter."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("HRH_RL_BACKOFF_BASE_SECONDS", "2.0")
        monkeypatch.setenv("HRH_RL_BACKOFF_MAX_SECONDS", "30.0")
        monkeypatch.setenv("HRH_RL_JITTER_SECONDS", "0.0")  # zero jitter for determinism
        monkeypatch.delenv("HRH_SOFT_RPS", raising=False)
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        sleep_calls: list[float] = []
        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleep_calls.append(s))
        _mock_openai_client(monkeypatch, [
            _make_rate_limit_error(),
            _make_rate_limit_error(),
        ])

        llm_mod.generate_json("test prompt")

        assert len(sleep_calls) == 2
        # attempt 0: base * 2^0 = 2.0; attempt 1: base * 2^1 = 4.0
        assert sleep_calls[0] == pytest.approx(2.0, abs=0.01)
        assert sleep_calls[1] == pytest.approx(4.0, abs=0.01)
        assert sleep_calls[1] > sleep_calls[0], "Backoff must grow with attempts"

    def test_backoff_capped_at_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Backoff never exceeds HRH_RL_BACKOFF_MAX_SECONDS."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("HRH_RL_BACKOFF_BASE_SECONDS", "10.0")
        monkeypatch.setenv("HRH_RL_BACKOFF_MAX_SECONDS", "15.0")
        monkeypatch.setenv("HRH_RL_JITTER_SECONDS", "0.0")
        monkeypatch.setenv("HRH_RL_MAX_RETRIES", "5")
        monkeypatch.delenv("HRH_SOFT_RPS", raising=False)
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        sleep_calls: list[float] = []
        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleep_calls.append(s))
        _mock_openai_client(monkeypatch, [_make_rate_limit_error()] * 4)

        llm_mod.generate_json("test prompt")

        assert all(s <= 15.0 for s in sleep_calls), (
            f"Some sleep exceeded MAX_BACKOFF=15.0: {sleep_calls}"
        )

    def test_api_connection_error_small_backoff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """APIConnectionError uses small backoff (≤16s), not the 429 backoff."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("HRH_RL_BACKOFF_BASE_SECONDS", "60.0")  # large 429 base
        monkeypatch.setenv("HRH_RL_JITTER_SECONDS", "0.0")
        monkeypatch.delenv("HRH_SOFT_RPS", raising=False)
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        sleep_calls: list[float] = []
        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleep_calls.append(s))
        _mock_openai_client(monkeypatch, [_make_conn_error()])

        llm_mod.generate_json("test prompt")

        assert len(sleep_calls) == 1
        assert sleep_calls[0] < 5.0, (
            f"Connection error backoff should be small (< 5s); got {sleep_calls[0]}"
        )

    def test_rate_limit_log_message_produced(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """[RATE LIMIT] log line is printed on 429."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("HRH_RL_JITTER_SECONDS", "0.0")
        monkeypatch.delenv("HRH_SOFT_RPS", raising=False)
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
        _mock_openai_client(monkeypatch, [_make_rate_limit_error()])

        llm_mod.generate_json("test prompt")

        out = capsys.readouterr().out
        assert "[RATE LIMIT] 429" in out, f"Expected [RATE LIMIT] log; got:\n{out}"

    def test_soft_rps_adds_pre_call_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HRH_SOFT_RPS=2 causes a ~0.5s sleep before the API call."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("HRH_SOFT_RPS", "2")  # 0.5s between calls
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        sleep_calls: list[float] = []
        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleep_calls.append(s))
        _mock_openai_client(monkeypatch, [])  # success immediately

        llm_mod.generate_json("test prompt")

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.5, abs=0.01)

    def test_soft_rps_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HRH_SOFT_RPS unset → no pre-call sleep."""
        monkeypatch.setenv("HRH_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("HRH_SOFT_RPS", raising=False)
        _patch_exc_classes(monkeypatch)
        import app.analyze.llm as llm_mod

        sleep_calls: list[float] = []
        monkeypatch.setattr(llm_mod.time, "sleep", lambda s: sleep_calls.append(s))
        _mock_openai_client(monkeypatch, [])

        llm_mod.generate_json("test prompt")

        assert sleep_calls == []


def test_llm_retry_repairs_schema_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Forces first LLM attempt to fail schema validation (missing generated_at),
    then returns a valid payload on the second attempt.
    """
    # Import here so monkeypatching targets are available
    import app.analyze.llm as llm_mod
    import app.app as app_mod

    calls = {"n": 0}

    bad_payload = {
        "job_id": "phase1_discovery_qa",
        "spec_id": "phase1_discovery_questions_ethiopia_v1",
        # generated_at intentionally missing -> should fail schema
        "country": {"name": "Ethiopia", "iso3": "ETH"},
        "questions": [
            {
                "question_id": "P1_Q1",
                "question": "Stub question",
                "answer": "Stub answer",
                "evidence": {"quality": "none", "rationale": "no sources", "citations": []},
                "tags": []
            }
        ]
    }

    good_payload = {
        "job_id": "phase1_discovery_qa",
        "spec_id": "phase1_discovery_questions_ethiopia_v1",
        "generated_at": "2026-02-04",
        "country": {"name": "Ethiopia", "iso3": "ETH"},
        "questions": [
            {
                "question_id": "P1_Q1",
                "question": "Stub question",
                "answer": "Stub answer",
                "evidence": {"quality": "none", "rationale": "no sources", "citations": []},
                "tags": []
            }
        ]
    }

    def fake_generate_json(prompt: str, provider=None, model=None, repair_instructions=None, job_id=None):
        calls["n"] += 1
        text = json.dumps(bad_payload if calls["n"] == 1 else good_payload)
        return llm_mod.LLMResponse(text=text)

    # Patch the LLM call so we never hit the network
    monkeypatch.setattr(llm_mod, "generate_json", fake_generate_json)

    # Run the CLI entrypoint programmatically
    exit_code = app_mod.main([
        "run",
        "--job", "phase1_discovery_qa",
        "--mode", "llm",
        "--spec-id", "phase1_discovery_questions_ethiopia_v1",
        "--country-name", "Ethiopia",
        "--country-iso3", "ETH"
    ])

    assert exit_code == 0
    assert calls["n"] == 2  # proves retry happened

    # Find the most recent timestamped folder
    job_output_dir = Path("outputs/phase1_discovery_qa")
    matching_files = []
    for folder in job_output_dir.iterdir():
        if folder.is_dir():
            json_file = folder / "output_llm.json"
            if json_file.exists():
                matching_files.append(json_file)

    assert len(matching_files) > 0, "No output_llm.json found in timestamped folders"

    # Get the most recent file
    matching_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out_path = matching_files[0]

    assert out_path.exists()

    # Clean up the entire timestamped folder
    import shutil
    shutil.rmtree(out_path.parent, ignore_errors=True)
