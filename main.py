"""Interactive CLI for the Healthcare AI Patient Symptom Triage Concierge."""

import os
import json

from dotenv import load_dotenv
import openai
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from orchestrator import run_triage

load_dotenv()

console = Console()


def print_result(result) -> None:
    """Pretty-print a TriageResult to the console."""
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    if result.guardrail:
        table.add_row("is_health_related", str(result.guardrail.is_health_related))
        table.add_row("no_phi", str(result.guardrail.no_phi))
        table.add_row("needs_escalation", str(result.guardrail.needs_escalation))

    if result.parser:
        table.add_row("intent", result.parser.intent)
        table.add_row("chief_complaint", result.parser.chief_complaint)
        table.add_row("acuity", result.parser.acuity)

    if result.safety:
        table.add_row(
            "compliance_pass",
            str(result.safety.compliance_pass),
        )
        if result.safety.violations:
            table.add_row("violations", ", ".join(result.safety.violations))

    if result.pipeline_blocked:
        table.add_row("pipeline_blocked", f"[red]{result.block_reason}[/red]")

    console.print(table)

    color = "red" if result.escalation_triggered else "green"
    console.print(
        Panel(
            result.final_response,
            title="[bold]Response to Patient[/bold]",
            border_style=color,
        )
    )


def main() -> None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        console.print(
            "[bold red]Error:[/bold red] GROQ_API_KEY not set. "
            "Copy .env.example to .env and add your key."
        )
        return

    client = openai.OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
    )
    console.print(
        Panel(
            "[bold cyan]Healthcare AI – Patient Symptom Triage Concierge[/bold cyan]\n"
            "Type your patient message and press Enter. Type [bold]exit[/bold] to quit.",
            border_style="cyan",
        )
    )

    while True:
        try:
            message = console.input("\n[bold yellow]Patient:[/bold yellow] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not message:
            continue
        if message.lower() in {"exit", "quit", "q"}:
            console.print("[dim]Goodbye.[/dim]")
            break

        with console.status("[bold green]Processing...[/bold green]", spinner="dots"):
            result = run_triage(message, client)

        print_result(result)

        if result.error:
            console.print(f"[dim red]Internal error: {result.error}[/dim red]")


if __name__ == "__main__":
    main()
