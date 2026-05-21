"""Agent 3 – safetyChecks: Reviews the generated reply before it reaches the patient."""

import time
from typing import List

from pydantic import BaseModel
from google import genai
from google.genai import types


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

Be strict. Even subtle diagnostic implications or specific drug recommendations are violations."""


def run(
    reply: str,
    client: genai.Client,
    model: str = "gemini-2.0-flash",
    max_retries: int = 3,
) -> SafetyOutput:
    """Run the safety checks agent with rule-based override and exponential-backoff retry."""
    has_disclaimer = DISCLAIMER.lower() in reply.lower()

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=f"Review this response:\n\n{reply}",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=SafetyOutput,
                    temperature=0,
                    safety_settings=[
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,        threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,        threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,  threshold=types.HarmBlockThreshold.BLOCK_NONE),
                        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,  threshold=types.HarmBlockThreshold.BLOCK_NONE),
                    ],
                ),
            )
            try:
                text = response.text
            except Exception as blocked_exc:
                raise RuntimeError(f"Gemini blocked the response: {blocked_exc}") from blocked_exc
            result = SafetyOutput.model_validate_json(text)

            if not has_disclaimer and "MISSING_DISCLAIMER" not in result.violations:
                result.violations.append("MISSING_DISCLAIMER")
                result.compliance_pass = False

            return result
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
    raise RuntimeError(
        f"Safety checks agent failed after {max_retries} attempts: {last_error}"
    )
