"""FastAPI backend – exposes the 3-agent triage pipeline as a REST API."""

import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import openai
from pydantic import BaseModel

from orchestrator import run_triage

load_dotenv()

app = FastAPI(title="Healthcare AI Triage API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client: Optional[openai.OpenAI] = None


def get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured on the server.")
        _client = openai.OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key,
        )
    return _client


class TriageRequest(BaseModel):
    message: str


@app.post("/triage")
def triage_endpoint(req: TriageRequest) -> Dict[str, Any]:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    result = run_triage(req.message, get_client())
    return {
        "guardrail": result.guardrail.model_dump() if result.guardrail else None,
        "parser": result.parser.model_dump() if result.parser else None,
        "safety": result.safety.model_dump() if result.safety else None,
        "final_response": result.final_response,
        "pipeline_blocked": result.pipeline_blocked,
        "block_reason": result.block_reason,
        "escalation_triggered": result.escalation_triggered,
        "error": result.error,
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
