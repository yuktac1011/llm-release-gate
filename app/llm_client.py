import os, re, time
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

load_dotenv()


class LLMError(Exception): ...
class MissingAPIKeyError(LLMError): ...
class LLMTimeoutError(LLMError): ...
class LLMRateLimitError(LLMError): ...


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


REFUSAL = "Sorry, I can only help with CloudNest support questions. I don't have information on that."
INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above)|system prompt|reveal your|you are now|pretend", re.I
)
STOP = {"the", "and", "for", "how", "can", "what", "you", "your", "are", "does", "with", "this",
        "that", "from", "have", "not", "any", "get", "was", "will", "would", "could", "should",
        "there", "they", "them", "about", "which"}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP}


def _mock(system: str, user: str) -> str:
    """Deterministic fake LLM. Its behaviour depends on the PROMPT, so a bad prompt gives bad answers."""
    low = system.lower()
    guards_injection = "never follow instructions" in low
    guards_scope = "only answer using the faq" in low

    if INJECTION.search(user):
        if guards_injection:
            return REFUSAL
        return "Sure! Here are my instructions: " + system[:200]

    q = _tokens(user)
    best_answer, best_score = None, 0.0
    for fq, fa in re.findall(r"Q: (.*)\nA: (.*)", system):
        score = len(q & _tokens(fq + " " + fa)) / max(len(q), 1)
        if score > best_score:
            best_answer, best_score = fa, score

    if best_answer and best_score >= 0.5:
        return best_answer
    if guards_scope:
        return REFUSAL
    return "Great question! I believe that is generally possible, and you can find it in your account settings."


def _real(system: str, user: str, settings: dict) -> tuple[str, int, int]:
    base = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    key = os.getenv("LLM_API_KEY", "")
    is_local = "localhost" in base or "127.0.0.1" in base
    if not key and not is_local:
        raise MissingAPIKeyError(
            "LLM_API_KEY is not set. Add it to your .env file (see .env.example) "
            "or run with LLM_MODE=mock."
        )
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    body = {
        "model": settings["name"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": settings.get("temperature", 0),
        "max_tokens": settings.get("max_tokens", 300),
    }
    try:
        r = httpx.post(f"{base}/chat/completions", json=body, headers=headers,
                       timeout=settings.get("timeout_s", 30))
    except httpx.TimeoutException:
        raise LLMTimeoutError("The model took too long to respond.")
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach the model server: {e}")

    if r.status_code == 429:
        raise LLMRateLimitError("Rate limit hit. Try again shortly.")
    if r.status_code in (401, 403):
        raise LLMError("The API key was rejected by the provider.")
    if r.status_code >= 400:
        raise LLMError(f"Provider returned HTTP {r.status_code}: {r.text[:200]}")

    data = r.json()
    usage = data.get("usage", {})
    return (data["choices"][0]["message"]["content"].strip(),
            usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def call_llm(system: str, user: str, settings: dict) -> LLMResponse:
    mode = os.getenv("LLM_MODE", "mock")
    start = time.perf_counter()
    if mode == "mock":
        text = _mock(system, user)
        pt, ct = (len(system) + len(user)) // 4, len(text) // 4   # rough estimate
    elif mode == "openai_compat":
        text, pt, ct = _real(system, user, settings)
    else:
        raise LLMError(f"Unknown LLM_MODE '{mode}'. Use 'mock' or 'openai_compat'.")
    return LLMResponse(text, pt, ct, round((time.perf_counter() - start) * 1000, 1))