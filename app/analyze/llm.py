from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Optional

from openai import APIConnectionError, OpenAI, RateLimitError


# ---------------------------------------------------------------------------
# Adaptive rate-limit constants (all env-overridable)
# ---------------------------------------------------------------------------

def _rl_base() -> float:
    return float(os.getenv("HRH_RL_BACKOFF_BASE_SECONDS", "1.0"))


def _rl_max() -> float:
    return float(os.getenv("HRH_RL_BACKOFF_MAX_SECONDS", "30.0"))


def _rl_jitter() -> float:
    return float(os.getenv("HRH_RL_JITTER_SECONDS", "1.0"))


def _rl_max_retries() -> int:
    return int(os.getenv("HRH_RL_MAX_RETRIES", "5"))


def _soft_rps() -> Optional[float]:
    """If HRH_SOFT_RPS is set, return requests-per-second limit; else None (disabled)."""
    v = os.getenv("HRH_SOFT_RPS", "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _extract_retry_after(exc: RateLimitError) -> Optional[float]:
    """Return server-requested wait in seconds from response headers, or None."""
    try:
        headers = exc.response.headers  # type: ignore[attr-defined]
        ra = headers.get("Retry-After", "").strip()
        if ra.isdigit():
            return float(ra)
        # x-ratelimit-reset-requests / x-ratelimit-reset-tokens: "1.5s", "60s"
        for hdr in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
            val = headers.get(hdr, "").strip().rstrip("s")
            if val:
                try:
                    return float(val)
                except ValueError:
                    pass
    except Exception:
        pass
    return None


@dataclass(frozen=True)
class LLMNotConfigured(RuntimeError):
    message: str = "LLM mode not configured. Set HRH_LLM_PROVIDER and OPENAI_API_KEY."

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class LLMResponse:
    text: str


def generate_json(
    prompt: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    repair_instructions: Optional[str] = None,
    job_id: Optional[str] = None,
    n_excerpts: Optional[int] = None,
    total_chars: Optional[int] = None,
) -> LLMResponse:
    """
    Generate JSON-only output from an LLM.

    Env vars:
      - HRH_LLM_PROVIDER: must be 'openai' for now
      - OPENAI_API_KEY: required
      - HRH_OPENAI_MODEL: optional (default: gpt-5.3)
    """
    provider = (provider or os.getenv("HRH_LLM_PROVIDER", "")).strip().lower()
    if not provider:
        raise LLMNotConfigured("Set HRH_LLM_PROVIDER=openai and OPENAI_API_KEY.")

    if provider != "openai":
        raise LLMNotConfigured(f"Unsupported provider '{provider}'. Only 'openai' is implemented.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMNotConfigured("Missing OPENAI_API_KEY. Set it in your environment.")

    model = model or os.getenv("HRH_OPENAI_MODEL", "gpt-5.3")

    client = OpenAI(api_key=api_key)

    # Force JSON-only behavior via instruction + response format.
    system_text = (
        "You must output ONLY valid JSON that matches the requested schema. "
        "No markdown, no commentary, no code fences, no trailing text. "
        "If you are given validation errors, fix the JSON to satisfy them."
    )
    if repair_instructions:
        system_text += "\n\nVALIDATION ERRORS TO FIX:\n" + repair_instructions

    _STRUCTURED_EXTRACTION_JOBS = {"domain_solutions_from_evidence", "domain_lessons_option_b", "domain_lessons_planner"}
    extra_kwargs = (
        {"temperature": 0, "max_completion_tokens": 16384}
        if job_id in _STRUCTURED_EXTRACTION_JOBS
        else {}
    )

    # Log call settings (once, before retry loop — settings are constant across retries)
    temp_str = str(extra_kwargs["temperature"]) if "temperature" in extra_kwargs else "unset"
    mct_str = str(extra_kwargs["max_completion_tokens"]) if "max_completion_tokens" in extra_kwargs else "unset"
    excerpts_str = str(n_excerpts) if n_excerpts is not None else "n/a"
    chars_str = str(total_chars) if total_chars is not None else "n/a"
    print(
        f"[LLM] job_id={job_id or 'none'} model={model} "
        f"temperature={temp_str} max_completion_tokens={mct_str} "
        f"n_excerpts={excerpts_str} total_chars={chars_str}"
    )

    # Optional soft RPS throttle: tiny pre-call sleep to smooth burst traffic.
    _rps = _soft_rps()
    if _rps and _rps > 0:
        time.sleep(1.0 / _rps)

    max_retries = _rl_max_retries()
    for retry in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                **extra_kwargs,
            )
            break  # success — no sleep
        except RateLimitError as e:
            if retry == max_retries - 1:
                raise
            wait = _extract_retry_after(e)
            if wait is None:
                wait = min(_rl_base() * (2 ** retry), _rl_max()) + random.uniform(0, _rl_jitter())
            print(f"  [RATE LIMIT] 429; sleeping {wait:.1f}s (attempt {retry + 1}/{max_retries})")
            time.sleep(wait)
        except APIConnectionError as e:
            if retry == max_retries - 1:
                raise
            wait = min(1.0 * (2 ** retry), 16.0) + random.uniform(0, 0.5)
            print(f"  [CONN ERROR] {type(e).__name__}; sleeping {wait:.1f}s (attempt {retry + 1}/{max_retries})")
            time.sleep(wait)

    # Log token usage
    usage = getattr(resp, "usage", None)
    if usage:
        print(
            f"[LLM] usage: prompt_tokens={usage.prompt_tokens} "
            f"completion_tokens={usage.completion_tokens} "
            f"total_tokens={usage.total_tokens}"
        )
    else:
        print("[LLM] usage: unavailable")

    # Extract text from response
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI returned empty response.")
    return LLMResponse(text=text)
