import json, os, re
from pathlib import Path

import yaml

from app.llm_client import call_llm

ROOT = Path(__file__).resolve().parent.parent
FAQ_PATH = ROOT / "app" / "faq.json"
PROMPT_DIR = ROOT / "prompts"


def load_faq() -> list[dict]:
    return json.loads(FAQ_PATH.read_text(encoding="utf-8"))


def load_prompt(version: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", version):
        raise ValueError(f"Invalid prompt version name: {version!r}")
    path = PROMPT_DIR / f"{version}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Prompt version '{version}' not found.")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def format_faq(faq: list[dict]) -> str:
    return "\n\n".join(f"Q: {e['question']}\nA: {e['answer']}" for e in faq)


def answer_question(question: str, version: str | None = None) -> dict:
    version = version or os.getenv("PROMPT_VERSION", "v1")
    prompt = load_prompt(version)
    system = prompt["system_prompt"].replace("{faq}", format_faq(load_faq()))
    resp = call_llm(system=system, user=question, settings=prompt["model"])
    return {
        "answer": resp.text,
        "prompt_version": version,
        "latency_ms": resp.latency_ms,
        "prompt_tokens": resp.prompt_tokens,
        "completion_tokens": resp.completion_tokens,
    }