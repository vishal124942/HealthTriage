"""
Evaluation harness for the Healthcare AI Patient Symptom Triage system.

Run as a standalone script:
    python evaluation/eval_harness.py

Run via pytest:
    pytest evaluation/eval_harness.py -v
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest
from dotenv import load_dotenv
import openai
from rich.console import Console
from rich.table import Table
from rich import box

sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator import run_triage, TriageResult

load_dotenv()

TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"
DISCLAIMER = (
    "This is not a medical diagnosis. Please consult a licensed healthcare provider "
    "for personalized medical advice."
)

console = Console()


# ── Data loading ──────────────────────────────────────────────────────────────

def load_test_cases() -> List[Dict]:
    with open(TEST_CASES_PATH) as f:
        return json.load(f)


# ── Single-case evaluation ────────────────────────────────────────────────────

def evaluate_case(case: Dict, client: openai.OpenAI) -> Dict[str, Any]:
    """Run one test case through the pipeline and evaluate against expectations."""
    start = time.perf_counter()
    result: TriageResult = run_triage(case["input"], client)
    latency = time.perf_counter() - start

    expected = case["expected"]
    assertions: Dict[str, bool] = {}

    # ── Guardrail assertions ──────────────────────────────────────────────────
    if result.guardrail:
        assertions["is_health_related"] = (
            result.guardrail.is_health_related == expected["is_health_related"]
        )
        assertions["no_phi"] = result.guardrail.no_phi == expected["no_phi"]
        assertions["needs_escalation"] = (
            result.guardrail.needs_escalation == expected["needs_escalation"]
        )
    else:
        assertions["is_health_related"] = False
        assertions["no_phi"] = False
        assertions["needs_escalation"] = False

    # ── Intent assertion (skip if expected is null) ───────────────────────────
    expected_intent = expected.get("intent")
    if expected_intent is None:
        assertions["intent"] = True
    elif result.parser:
        assertions["intent"] = result.parser.intent == expected_intent
    else:
        assertions["intent"] = False

    # ── Acuity assertion (skip if expected is null) ───────────────────────────
    expected_acuity = expected.get("acuity")
    if expected_acuity is None:
        assertions["acuity"] = True
    elif result.parser:
        assertions["acuity"] = result.parser.acuity == expected_acuity
    else:
        assertions["acuity"] = False

    # ── Compliance assertion ──────────────────────────────────────────────────
    expected_compliance = expected.get("compliance_pass", True)
    if result.safety:
        assertions["compliance_pass"] = (
            result.safety.compliance_pass == expected_compliance
        )
    elif result.pipeline_blocked:
        assertions["compliance_pass"] = True
    else:
        assertions["compliance_pass"] = False

    # ── Disclaimer assertion (health-related messages only) ───────────────────
    if expected.get("is_health_related", True):
        assertions["disclaimer_present"] = (
            DISCLAIMER.lower() in result.final_response.lower()
        )
    else:
        assertions["disclaimer_present"] = True

    return {
        "id": case["id"],
        "tag": case["tag"],
        "description": case["description"],
        "passed": all(assertions.values()),
        "assertions": assertions,
        "latency": latency,
        "block_reason": result.block_reason,
        "violations": result.safety.violations if result.safety else [],
        "error": result.error,
    }


# ── Reporting ─────────────────────────────────────────────────────────────────

def _pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "N/A"
    return f"{numerator / denominator * 100:.0f}%  ({numerator}/{denominator})"


def print_summary(results: List[Dict]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    latencies = [r["latency"] for r in results]

    console.rule("[bold cyan]Evaluation Summary[/bold cyan]")

    metric_table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    metric_table.add_column("Metric", style="bold")
    metric_table.add_column("Result")
    metric_table.add_column("Goal")

    for field, goal in [
        ("is_health_related", "100%"),
        ("no_phi", "100%"),
        ("needs_escalation", "100%"),
    ]:
        vals = [r["assertions"][field] for r in results if field in r["assertions"]]
        metric_table.add_row(
            f"Guardrail – {field}", _pct(sum(vals), len(vals)), goal
        )

    for field, label, goal in [
        ("intent", "Intent classification", "≥90%"),
        ("acuity", "Acuity classification", "≥85%"),
    ]:
        vals = [
            r["assertions"][field]
            for r in results
            if field in r["assertions"] and r["assertions"].get("is_health_related", True)
        ]
        metric_table.add_row(label, _pct(sum(vals), len(vals)), goal)

    comp_vals = [r["assertions"]["compliance_pass"] for r in results]
    metric_table.add_row(
        "Compliance pass rate", _pct(sum(comp_vals), len(comp_vals)), "100%"
    )

    disc_vals = [r["assertions"]["disclaimer_present"] for r in results]
    metric_table.add_row(
        "Disclaimer present", _pct(sum(disc_vals), len(disc_vals)), "100%"
    )

    p50 = statistics.median(latencies)
    p95 = sorted(latencies)[int(0.95 * len(latencies))]
    metric_table.add_row(f"P50 latency", f"{p50:.2f}s", "<5s")
    metric_table.add_row(f"P95 latency", f"{p95:.2f}s", "—")

    console.print(metric_table)

    overall_color = "green" if passed == total else "yellow"
    console.print(
        f"\n[bold {overall_color}]Overall: {passed}/{total} cases passed "
        f"({passed / total * 100:.0f}%)[/bold {overall_color}]"
    )

    failures = [r for r in results if not r["passed"]]
    if failures:
        console.print("\n[bold red]Failed cases:[/bold red]")
        for f in failures:
            failed_fields = [k for k, v in f["assertions"].items() if not v]
            console.print(
                f"  [red]✗[/red] {f['id']} ({f['tag']}): {failed_fields}"
            )
    else:
        console.print("\n[bold green]All cases passed! ✓[/bold green]")


def print_per_case_table(results: List[Dict]) -> None:
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Tag")
    table.add_column("Pass?")
    table.add_column("Latency")
    table.add_column("Block Reason / Violations")

    for r in results:
        status = "[green]✓ PASS[/green]" if r["passed"] else "[red]✗ FAIL[/red]"
        note = r["block_reason"] or (", ".join(r["violations"]) if r["violations"] else "—")
        table.add_row(r["id"], r["tag"], status, f"{r['latency']:.2f}s", note)

    console.print(table)


# ── Main runner ───────────────────────────────────────────────────────────────

def run_evaluation() -> List[Dict]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        console.print(
            "[bold red]Error:[/bold red] GROQ_API_KEY not set. "
            "Copy .env.example to .env and add your key."
        )
        sys.exit(1)

    client = openai.OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
    )
    test_cases = load_test_cases()

    console.print(
        f"[bold cyan]Running {len(test_cases)} evaluation cases...[/bold cyan]\n"
    )

    results: List[Dict] = []
    for i, case in enumerate(test_cases, 1):
        console.print(
            f"  [{i:2d}/{len(test_cases)}] [dim]{case['id']}[/dim] "
            f"{case['description'][:55]}..."
        )
        eval_result = evaluate_case(case, client)
        results.append(eval_result)

        status = "[green]PASS[/green]" if eval_result["passed"] else "[red]FAIL[/red]"
        console.print(
            f"           {status} | {eval_result['latency']:.2f}s"
        )
        if not eval_result["passed"]:
            failed = [k for k, v in eval_result["assertions"].items() if not v]
            console.print(f"           [red]Failed: {failed}[/red]")

    console.print()
    print_per_case_table(results)
    print_summary(results)
    return results


# ── Pytest integration ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def groq_client():
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set")
    return openai.OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
    )


@pytest.mark.parametrize(
    "case",
    load_test_cases(),
    ids=[c["id"] for c in load_test_cases()],
)
def test_triage_case(case, groq_client):
    """Parametrised pytest test – one test per evaluation case."""
    result = evaluate_case(case, groq_client)
    failed_assertions = {k: v for k, v in result["assertions"].items() if not v}
    assert not failed_assertions, (
        f"{case['id']} ({case['tag']}) – failed assertions: {list(failed_assertions.keys())}\n"
        f"Block reason: {result['block_reason']}\nError: {result['error']}"
    )


if __name__ == "__main__":
    run_evaluation()
