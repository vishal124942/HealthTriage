"""Pipeline orchestrator: chains Agent 1 → Agent 2 → Agent 3 with fallback handling."""

from dataclasses import dataclass, field
from typing import Optional

import openai

from agents.guardrail_agent import GuardrailOutput, run as run_guardrail
from agents.symptom_parser_agent import SymptomParserOutput, run as run_parser
from agents.safety_checks_agent import SafetyOutput, run as run_safety


FALLBACK_RESPONSE = (
    "Thank you for reaching out. We're unable to process your request at this time. "
    "Please contact our support team or a licensed healthcare provider directly. "
    "This is not a medical diagnosis. Please consult a licensed healthcare provider "
    "for personalized medical advice."
)

ESCALATION_RESPONSE = (
    "Your message suggests you may need immediate medical attention. "
    "Please call emergency services (911) immediately or go to the nearest emergency room. "
    "If you are experiencing thoughts of self-harm, please contact the National Suicide "
    "Prevention Lifeline by calling or texting 988. "
    "This is not a medical diagnosis. Please consult a licensed healthcare provider "
    "for personalized medical advice."
)

NOT_HEALTH_RELATED_RESPONSE = (
    "I can only assist with health-related inquiries such as symptom checks, "
    "prescription refills, or appointment bookings. Please contact us with a "
    "health-related question."
)

PHI_BLOCKED_RESPONSE = (
    "Your message appears to contain sensitive personal health information (PHI). "
    "For your privacy and security, please remove sensitive identifiers such as "
    "Social Security numbers, medical record numbers, or government IDs before "
    "resubmitting. "
    "This is not a medical diagnosis. Please consult a licensed healthcare provider "
    "for personalized medical advice."
)


@dataclass
class TriageResult:
    patient_message: str
    guardrail: Optional[GuardrailOutput] = None
    parser: Optional[SymptomParserOutput] = None
    safety: Optional[SafetyOutput] = None
    final_response: str = ""
    pipeline_blocked: bool = False
    block_reason: str = ""
    escalation_triggered: bool = False
    error: Optional[str] = None


def run_triage(patient_message: str, client: openai.OpenAI) -> TriageResult:
    """
    Execute the full 3-agent triage pipeline.

    Flow:
      1. Agent 1 (guardrailCheck)   – always runs
      2. Block if not health-related or PHI detected
      3. Agent 2 (symptomParser)    – runs for all valid health messages
      4. Override response if escalation was flagged
      5. Agent 3 (safetyChecks)     – reviews the response to be sent
      6. Return final response or safe fallback
    """
    result = TriageResult(patient_message=patient_message)

    # ── Agent 1: Guardrail ────────────────────────────────────────────────────
    try:
        result.guardrail = run_guardrail(patient_message, client)
    except Exception as exc:
        result.error = str(exc)
        result.final_response = FALLBACK_RESPONSE
        result.pipeline_blocked = True
        result.block_reason = "guardrail_error"
        return result

    if not result.guardrail.no_phi:
        result.pipeline_blocked = True
        result.block_reason = "phi_detected"
        result.final_response = PHI_BLOCKED_RESPONSE
        return result

    if not result.guardrail.is_health_related:
        result.pipeline_blocked = True
        result.block_reason = "not_health_related"
        result.final_response = NOT_HEALTH_RELATED_RESPONSE
        return result

    result.escalation_triggered = result.guardrail.needs_escalation

    # ── Agent 2: Symptom Parser ───────────────────────────────────────────────
    try:
        result.parser = run_parser(patient_message, client)
    except Exception as exc:
        result.error = str(exc)
        result.final_response = (
            ESCALATION_RESPONSE if result.escalation_triggered else FALLBACK_RESPONSE
        )
        result.pipeline_blocked = True
        result.block_reason = "parser_error"
        return result

    # Per PDF: High acuity also triggers escalation regardless of Agent 1's flag.
    if result.parser.acuity == "High":
        result.escalation_triggered = True

    # For escalation cases the response is overridden, but we still keep Agent 2
    # output for acuity/intent evaluation purposes.
    candidate_response = (
        ESCALATION_RESPONSE
        if result.escalation_triggered
        else result.parser.summary_response
    )

    # ── Agent 3: Safety Checks ────────────────────────────────────────────────
    try:
        result.safety = run_safety(candidate_response, client)
    except Exception as exc:
        result.error = str(exc)
        result.final_response = (
            ESCALATION_RESPONSE if result.escalation_triggered else FALLBACK_RESPONSE
        )
        result.pipeline_blocked = True
        result.block_reason = "safety_error"
        return result

    if result.safety.compliance_pass or result.escalation_triggered:
        result.final_response = candidate_response
    else:
        result.pipeline_blocked = True
        result.block_reason = f"compliance_violations: {result.safety.violations}"
        result.final_response = FALLBACK_RESPONSE

    return result
