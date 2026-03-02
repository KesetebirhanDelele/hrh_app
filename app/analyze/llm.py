from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI, RateLimitError


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
      - HRH_OPENAI_MODEL: optional (default: gpt-4o-mini)
    """
    provider = (provider or os.getenv("HRH_LLM_PROVIDER", "")).strip().lower()
    if not provider:
        raise LLMNotConfigured("Set HRH_LLM_PROVIDER=openai and OPENAI_API_KEY.")

    if provider != "openai":
        raise LLMNotConfigured(f"Unsupported provider '{provider}'. Only 'openai' is implemented.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMNotConfigured("Missing OPENAI_API_KEY. Set it in your environment.")

    model = model or os.getenv("HRH_OPENAI_MODEL", "gpt-4o")

    client = OpenAI(api_key=api_key)

    # Force JSON-only behavior via instruction + response format.
    system_text = (
        "You must output ONLY valid JSON that matches the requested schema. "
        "No markdown, no commentary, no code fences, no trailing text. "
        "If you are given validation errors, fix the JSON to satisfy them."
    )
    if repair_instructions:
        system_text += "\n\nVALIDATION ERRORS TO FIX:\n" + repair_instructions

    _STRUCTURED_EXTRACTION_JOBS = {"domain_solutions_from_evidence", "domain_lessons_option_b"}
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

    max_retries = 5
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
            break
        except RateLimitError as e:
            if retry == max_retries - 1:
                raise
            wait = min(2 ** retry * 30, 120)  # 30s, 60s, 120s, 120s
            print(f"  Rate limited, waiting {wait}s before retry ({retry + 1}/{max_retries})...")
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
