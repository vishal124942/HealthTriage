# Healthcare AI – Patient Symptom Triage Concierge

A multi-agent AI system that triages patient messages using three sequential agents:
- **Agent 1 – guardrailCheck**: PHI detection, health-relevance check, emergency escalation
- **Agent 2 – symptomParser**: Intent classification, acuity scoring, structured reply
- **Agent 3 – safetyChecks**: Compliance review of the generated reply

## Setup

```bash
# 1. Clone / navigate to project directory
cd ey_project

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your Google API key
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=...
```

## Run the interactive triage console

```bash
python main.py
```

## Run the evaluation harness

```bash
python evaluation/eval_harness.py
```

Or with pytest:

```bash
pytest evaluation/eval_harness.py -v
```

## Project Structure

```
ey_project/
├── agents/
│   ├── guardrail_agent.py       # Agent 1 – Intake Guardrails   (gemini-2.0-flash)
│   ├── symptom_parser_agent.py  # Agent 2 – Inquiry Inference   (gemini-2.0-flash)
│   └── safety_checks_agent.py   # Agent 3 – Compliance          (gemini-2.0-flash + rules)
├── orchestrator.py              # Pipeline orchestration + fallback logic
├── main.py                      # Interactive CLI
├── evaluation/
│   ├── test_cases.json          # 20 evaluation cases
│   └── eval_harness.py          # Evaluation script + pytest suite
├── docs/
│   ├── architecture_rationale.md
│   └── executive_email.md
├── requirements.txt
└── .env.example
```

## Architecture

```
Patient Message
      │
      ▼
┌─────────────────────────────────┐
│  Agent 1: guardrailCheck        │  gpt-4o-mini
│  • is_health_related            │
│  • no_phi                       │
│  • needs_escalation             │
└─────────────┬───────────────────┘
              │
   ┌──────────┴──────────┐
   │ Blocked?             │ Continue
   ▼                      ▼
Not health /     ┌─────────────────────────────────┐
PHI detected     │  Agent 2: symptomParser          │  gpt-4o-mini
→ early exit     │  • intent                        │
                 │  • chief_complaint               │
                 │  • acuity (Low/Medium/High)      │
                 │  • summary_response              │
                 └──────────────┬──────────────────┘
                                │
                   Escalation?  ├──► Override → ESCALATION_RESPONSE
                                ▼
                 ┌─────────────────────────────────┐
                 │  Agent 3: safetyChecks          │  gpt-4o-mini + rules
                 │  • compliance_pass              │
                 │  • violations                   │
                 └──────────────┬──────────────────┘
                                │
                 Fail? ─────────┴──► Fallback response
                                │
                                ▼
                         Final Response to Patient
```
