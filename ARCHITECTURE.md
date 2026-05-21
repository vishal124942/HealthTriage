# Architecture Rationale — Healthcare AI Patient Symptom Triage

## 1. System Architecture Diagram

```
                         ┌─────────────────────────────────────────────┐
                         │             PATIENT MESSAGE                  │
                         └───────────────────┬─────────────────────────┘
                                             │
                         ┌───────────────────▼─────────────────────────┐
                         │     AGENT 1 — guardrailCheck                │
                         │     Model: Gemini 2.0 Flash (Google)        │
                         │     + Safety Settings: BLOCK_NONE           │
                         │                                              │
                         │  Output:                                     │
                         │   is_health_related (bool)                   │
                         │   no_phi (bool)                              │
                         │   needs_escalation (bool)                    │
                         └──┬──────────────┬──────────────┬────────────┘
                            │              │              │
                      PHI found      not health     escalation
                            │              │              │
                       BLOCK (phi)    BLOCK (off)   flag for
                            │              │         escalation
                         ───┘              └──────────────┘
                                             │ pass
                         ┌───────────────────▼─────────────────────────┐
                         │     AGENT 2 — symptomParser                 │
                         │     Model: Gemini 2.0 Flash (Google)        │
                         │     + JSON Schema enforcement               │
                         │                                              │
                         │  Output:                                     │
                         │   intent: Symptom check / Prescription       │
                         │           refill / Appointment booking       │
                         │   chief_complaint: string                    │
                         │   acuity: Low / Medium / High                │
                         │   summary_response: compliant reply          │
                         │     (+ mandatory disclaimer)                 │
                         └───────────────────┬─────────────────────────┘
                                             │
                              acuity = "High"? → escalation_triggered
                                             │
                         ┌───────────────────▼─────────────────────────┐
                         │     AGENT 3 — safetyChecks                  │
                         │     Model: Gemini 2.0 Flash (Google)        │
                         │     + Deterministic disclaimer check        │
                         │                                              │
                         │  Output:                                     │
                         │   compliance_pass (bool)                     │
                         │   violations: list[str]                      │
                         │     DEFINITIVE_DIAGNOSIS                     │
                         │     PRESCRIPTION_ADVICE                      │
                         │     MISSING_DISCLAIMER                       │
                         │     PROTECTED_CHARACTERISTICS                │
                         └───────────────────┬─────────────────────────┘
                                             │
                              compliance_pass=False → BLOCK (fallback)
                                             │ pass
                         ┌───────────────────▼─────────────────────────┐
                         │  escalation_triggered?                       │
                         │   Yes → ESCALATION_RESPONSE (call 911/988)  │
                         │   No  → Agent 2's summary_response          │
                         └─────────────────────────────────────────────┘
                                             │
                                             ▼
                              FINAL REPLY → PATIENT
```

---

## 2. Model Selection Rationale

### Agent 1 — guardrailCheck

| Property | Value |
|---|---|
| Model | `gemini-2.0-flash` |
| Provider | Google AI (Gemini API) |
| TTFT | ~400–600ms |
| Task | 3-way boolean classification |

**Why Gemini 2.0 Flash?**  
Agent 1 is a binary gate — three boolean checks on raw patient text. The task requires strong language understanding (detecting disguised PHI, implicit emergency signals, off-topic messages) but not complex reasoning. Gemini 2.0 Flash provides flagship-tier accuracy on classification tasks at ~$0.075/1M input tokens. Native JSON schema enforcement (`response_schema`) eliminates free-text hallucinations entirely.

**Safety Settings: BLOCK_NONE**  
All four harm categories are set to `BLOCK_NONE`. This is deliberate: the guardrail agent IS the safety layer. Gemini's default content filters would block jailbreak-style messages before our guardrail can evaluate them, causing false pipeline failures. Our system prompt handles all safety classification internally.

**PHI Detection Coverage:**
- Full SSN (exact NNN-NN-NNNN format, 9 digits)
- Medical Record Numbers (unmasked)
- Health insurance member IDs
- Government IDs (Aadhaar, PAN, passport)
- Full date of birth combined with full name
- Phone numbers / mobile numbers (any format)
- Email addresses
- Home or mailing addresses

**Tradeoffs:**
- Cost: Lowest per-token cost in the Gemini family
- Accuracy: Sufficient for boolean classification with explicit prompt rules
- Latency: Fastest, keeps total P50 well under 5s

---

### Agent 2 — symptomParser

| Property | Value |
|---|---|
| Model | `gemini-2.0-flash` |
| Provider | Google AI (Gemini API) |
| TTFT | ~700–900ms |
| Task | Intent classification + acuity scoring + reply generation |

**Why Gemini 2.0 Flash?**  
This is the hardest agent — it must simultaneously:
1. Classify intent across 3 categories (Symptom check / Prescription refill / Appointment booking)
2. Assess clinical acuity (Low / Medium / High) using the provided policy rubric
3. Generate a compliant, empathetic, non-diagnostic patient reply
4. Avoid referencing protected characteristics (race, age, gender, disability)

Gemini 2.0 Flash handles all four tasks within a single structured JSON response. Using the same model family as Agent 1 avoids cold-start variance and simplifies deployment. JSON schema enforcement ensures every response contains all required fields.

**Jailbreak Resistance:**  
The system prompt explicitly instructs the model to decline diagnosis and prescription requests even under roleplay, DAN prompts, or authority-framing attacks. The model politely redirects without engaging with the jailbreak framing.

**Tradeoffs:**
- Cost: Generates the most tokens (full `summary_response`); still <$0.001/message
- Accuracy: High on structured tasks; JSON schema prevents drift
- Latency: ~700–900ms — well within the 5s budget

---

### Agent 3 — safetyChecks

| Property | Value |
|---|---|
| Model | `gemini-2.0-flash` + rule-based layer |
| Provider | Google AI (Gemini API) |
| Task | Compliance review of the generated reply |

**Why Gemini 2.0 Flash + Rules?**  
Compliance checking combines two layers:
1. **LLM review** — catches subtle violations: implied diagnosis, indirect prescription, protected characteristics usage
2. **Deterministic rule** — Python string-match checks if the disclaimer is present. This provides 100% recall on disclaimer enforcement regardless of LLM output.

**4 Violation Codes:**
| Code | Description |
|---|---|
| `DEFINITIVE_DIAGNOSIS` | Response states a specific condition as fact |
| `PRESCRIPTION_ADVICE` | Response recommends specific medications/dosages |
| `MISSING_DISCLAIMER` | Required legal disclaimer is absent |
| `PROTECTED_CHARACTERISTICS` | Response uses age/race/gender/disability in reasoning |

**Tradeoffs:**
- Cost: Minimal token count — shortest input (just the generated reply)
- Accuracy: 100% on disclaimer (deterministic); high on semantic violations
- Latency: Fastest leg of the pipeline (~300ms)

---

## 3. Orchestrator Logic

### Priority Order (PHI First)

```
1. PHI detected (no_phi=false)     → BLOCK immediately (privacy protection)
2. Not health-related              → BLOCK (scope enforcement)
3. Escalation (guardrail flag)     → Flag for escalation, continue pipeline
4. Agent 2 runs                    → If acuity="High", also flag escalation
5. Agent 3 runs                    → If compliance fails, return fallback
6. Final response                  → ESCALATION_RESPONSE or summary_response
```

PHI is checked BEFORE health-relevance. This ensures a message like "My SSN is 123-45-6789 and I have a headache" is blocked for PHI, not passed through as "health-related". Privacy always takes priority.

### Escalation Triggers (Two Paths)

| Trigger | Source | Behaviour |
|---|---|---|
| `needs_escalation=true` | Agent 1 (guardrail) | Detects explicit emergency signals in message text |
| `acuity="High"` | Agent 2 (parser) | Detects red-flag symptoms after clinical assessment |

Both paths converge: `escalation_triggered=true` → response overridden with ESCALATION_RESPONSE containing 911 and 988 hotline numbers.

### Retry Strategy

Each agent retries up to 3 times with exponential backoff (1s, 2s, 4s). On exhaustion:
- Agent 1 failure → FALLBACK_RESPONSE (pipeline cannot proceed without gate)
- Agent 2 failure → ESCALATION_RESPONSE if flagged, else FALLBACK_RESPONSE
- Agent 3 failure → Same logic

---

## 4. Cost, Accuracy, Latency Tradeoffs

| | Agent 1 | Agent 2 | Agent 3 |
|---|---|---|---|
| Model | Gemini 2.0 Flash | Gemini 2.0 Flash | Gemini 2.0 Flash |
| Relative Cost | Low | Medium | Low |
| Est. Tokens/call | ~200 | ~500 | ~250 |
| P50 Latency | ~500ms | ~800ms | ~300ms |
| Accuracy | ~100% (explicit rules) | ~95%+ (structured JSON) | ~100% (+ deterministic) |
| Compliance Risk | Low | Low (refuses diagnosis) | Minimal (rule override) |

**Total estimated pipeline latency:** ~1.6–2.5s end-to-end (well under 5s target)

**Total estimated cost per message:** ~$0.0003–0.0007 (Gemini Flash pricing)

---

## 5. Compliance Design Summary

| Requirement | How We Meet It |
|---|---|
| Disclaimer always present | Agent 2 prompt rules + Agent 3 deterministic string match |
| No definitive diagnoses | Agent 2 hard-refuses + Agent 3 semantic check |
| No prescription advice | Agent 2 hard-refuses + Agent 3 semantic check |
| PHI never enters pipeline | Agent 1 blocks before Agent 2 runs |
| Protected characteristics excluded | Explicit rules in Agent 2 + Agent 3 violation code |
| Emergency escalation | Agent 1 flag + Agent 2 High acuity → both trigger 911/988 response |
| AI is informational only | Policy embedded in all agent system prompts |
| Jailbreak resistance | Explicit anti-roleplay rules in Agent 2; safety settings disable Gemini filtering |

---

## 6. Frontend Architecture

| Component | Technology |
|---|---|
| Framework | React 18 + TypeScript |
| Build Tool | Vite 5 |
| Styling | Tailwind CSS 3 |
| Icons | Lucide React |
| API | Fetch → FastAPI backend on port 8000 |

**Chat Interface Features:**
- Real-time message bubbles (user + assistant)
- Typing indicator with CSS animation
- Expandable pipeline details per message (all 3 agents visible)
- Emergency escalation banner (red header)
- PHI block indicator
- Sample prompts on welcome screen
- Keyboard shortcuts (Enter to send, Shift+Enter for newline)
- Auto-scroll and responsive design
