from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm_client import LLMError, LLMRateLimitError, LLMTimeoutError, MissingAPIKeyError
from app.service import answer_question

app = FastAPI(title="CloudNest Support Answers")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    prompt_version: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/answer")
def answer(req: AskRequest):
    try:
        return answer_question(req.question, req.prompt_version)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except MissingAPIKeyError as e:
        raise HTTPException(503, str(e))
    except LLMTimeoutError as e:
        raise HTTPException(504, str(e))
    except LLMRateLimitError as e:
        raise HTTPException(429, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))