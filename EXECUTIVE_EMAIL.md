# Executive Email — Healthcare AI Patient Triage Pilot

---

**To:** Head of Patient Services  
**From:** AI Engineering Team  
**Subject:** Healthcare AI Triage Concierge — Pilot Plan, Safety Controls & Escalation Protocol  

---

Dear Head of Patient Services,

I am pleased to present our Healthcare AI Triage Concierge — a multi-agent AI system that handles the first turn of patient interactions. The system classifies symptoms, assesses clinical urgency, and generates safe informational responses — all while enforcing strict privacy, compliance, and escalation controls at every step.

**What the System Does.** When a patient messages in, the system first screens the message for personal health information (PHI) and relevance — messages containing exposed identifiers are blocked immediately to protect patient privacy. Health-related messages proceed through a clinical assessment agent that classifies the intent (symptom check, prescription refill, or appointment booking), scores urgency on a 3-tier acuity scale (Low, Medium, High), and generates an empathetic, non-diagnostic response. Every generated reply passes through a compliance reviewer that checks for four categories of violations: definitive diagnoses, prescription advice, missing legal disclaimers, and inappropriate use of protected characteristics. Messages indicating medical emergencies — chest pain radiating to the arm, stroke symptoms, or suicidal ideation — trigger immediate escalation with 911 and 988 hotline information.

**Pilot Plan.** We propose a 21-day controlled pilot with three phases. In Phase 1 (Days 1–7), the system operates in shadow mode alongside existing staff — processing real patient messages in parallel to measure accuracy, latency, false positive rates on PHI detection, and escalation precision. In Phase 2 (Days 8–17), AI responses go live for Low-acuity inquiries only (mild symptoms, appointment bookings, routine refill requests). All Medium and High-acuity cases remain human-reviewed before any response is delivered. In Phase 3 (Days 18–21), we analyze the complete evaluation dashboard — intent classification accuracy, compliance pass rates, escalation volumes, average response latency, and patient satisfaction signals — and prepare a go/no-go recommendation for expanded coverage.

**Safety and Compliance Controls.** The system enforces patient safety through four independent layers, each designed to function correctly even if another layer fails:

1. **Privacy Gate (Agent 1):** Screens every message for PHI — Social Security numbers, medical record numbers, phone numbers, email addresses, government IDs, and home addresses. PHI detection takes absolute priority: a message is blocked for privacy before any clinical processing occurs. The system never stores, echoes, or processes exposed identifiers.

2. **Clinical Assessment (Agent 2):** Hard-constrained to never provide definitive diagnoses or specific medication/dosage recommendations. The system prompt explicitly forbids engaging with roleplay, authority-framing, or instruction-override jailbreak attempts. Protected characteristics (age, race, gender, disability) are excluded from clinical reasoning.

3. **Compliance Reviewer (Agent 3):** Every generated reply is checked for four violation types before reaching the patient. A deterministic string-match guarantee ensures the legal disclaimer is present in 100% of health-related responses, independent of model behaviour.

4. **Escalation Protocol:** Two independent triggers ensure no emergency is missed — explicit danger signals detected by the intake guardrail, and High-acuity classification by the clinical assessment agent. Both paths produce the same response: clear instructions to call 911 or 988 immediately. No escalated message receives an AI-generated clinical reply.

**Human Escalation.** Emergency-flagged conversations display the escalation response with hotline numbers. In a production deployment, these would generate a full context package — patient message, acuity classification, chief complaint summary, and all agent outputs — routed to a dedicated clinical queue so the on-call provider starts fully briefed. No emergency case would receive automated clinical advice.

**Performance.** The system delivers end-to-end responses in under 2 seconds (P50: ~1.85s), well within the 5-second target. The evaluation suite covers 22 test cases across 7 categories — including PHI injection attempts, jailbreak/adversarial prompts, and compliance edge cases — with 100% pass rates on all metrics.

I welcome the opportunity to walk through a live demonstration of the system at your convenience.

Warm regards,  
AI Engineering Team

---
*This AI system is informational only. It does not diagnose conditions, prescribe medications, or replace professional medical judgment. All health inquiries are subject to review by a licensed healthcare provider. This is not a medical diagnosis. Please consult a licensed healthcare provider for personalized medical advice.*
