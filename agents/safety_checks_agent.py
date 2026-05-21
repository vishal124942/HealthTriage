"""Agent 3 – safetyChecks: Reviews the generated reply before it reaches the patient."""

import time
from typing import List

import openai
from pydantic import BaseModel


DISCLAIMER = (
    "This is not a medical diagnosis. Please consult a licensed healthcare provider "
    "for personalized medical advice."
)


class SafetyOutput(BaseModel):
    compliance_pass: bool
    violations: List[str]


SYSTEM_PROMPT = """You are a clinical compliance review agent. You will receive an \
AI-generated healthcare response and must check it for policy violations.

Check for these violations (use the exact codes below):

1. DEFINITIVE_DIAGNOSIS
   The response makes a definitive diagnosis.
   Examples: "You have pneumonia.", "This is definitely a heart attack.", "You definitely have X."

2. PRESCRIPTION_ADVICE
   The response recommends specific medications, dosages, or advises stopping medications.
   Examples: "Take 10 mg of X twice a day.", "Stop taking Y.", "You should use Z."

3. MISSING_DISCLAIMER
   The response does NOT contain this exact text:
   "This is not a medical diagnosis. Please consult a licensed healthcare provider for \
personalized medical advice."

4. PROTECTED_CHARACTERISTICS
   The response references or uses the patient's protected characteristics (race, religion, \
gender, age, disability, or similar) as part of clinical reasoning or in the reply.
   Examples: "Given your age, you likely have X.", "As a woman, you may be prone to Y."

Return:
- compliance_pass: true ONLY if violations is an empty array.
- violations: array of applicable violation codes, or [] if none.

Be strict. Even subtle diagnostic implications or specific drug recommendations are violations.

You MUST respond with a JSON object containing exactly these fields:
{"compliance_pass": bool, "violations": [str]}"""


def run(
    reply: str,
    client: openai.OpenAI,
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct",
    max_retries: int = 3,
) -> SafetyOutput:
    """Run the safety checks agent with rule-based override and exponential-backoff retry."""
    has_disclaimer = DISCLAIMER.lower() in reply.lower()

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Review this response:\n\n{reply}"},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            result = SafetyOutput.model_validate_json(response.choices[0].message.content)

            if not has_disclaimer and "MISSING_DISCLAIMER" not in result.violations:
                result.violations.append("MISSING_DISCLAIMER")
                result.compliance_pass = False

            return result
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                wait = 15 if "429" in str(exc) or "rate_limit" in str(exc).lower() else 5 * (attempt + 1)
                time.sleep(wait)
    raise RuntimeError(
        f"Safety checks agent failed after {max_retries} attempts: {last_error}"
    )
