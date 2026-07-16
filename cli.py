"""
Command-line interface for the CRM AI Copilot. Two modes:

1. Direct command mode -- explicit, scriptable, exact:
     python cli.py calls-by-agent --agent "Priya Sharma"

2. Ask mode -- natural language, routed via nlp_router:
     python cli.py ask "How many calls did Priya Sharma make this week?"
     python cli.py ask            # interactive REPL(Read Evaluate Print Loop) if no question given
"""
import argparse
import json
import sys

from db import get_db
from nlp_router import route_multi
from registry import REGISTRY, run_intent
from rich.console import Console
from rich.json import JSON
from rich.table import Table

console = Console()


def print_result(result: dict, full: bool = False, out_path: str = None):
    if out_path:
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        console.print(f"[green]Wrote full result ({len(result.get('results', result))} "
                       f"top-level items) to {out_path}[/green]")
        return

    results_list = result.get("results")
    if isinstance(results_list, list) and results_list:
        meta = {k: v for k, v in result.items() if k != "results"}
        console.print(JSON(json.dumps(meta, default=str)))
        limit = len(results_list) if full else 25
        table = Table(show_header=True, header_style="bold cyan")
        for key in results_list[0].keys():
            table.add_column(key)
        for row in results_list[:limit]:
            table.add_row(*[str(row.get(c, "")) for c in results_list[0].keys()])
        console.print(table)
        if not full and len(results_list) > limit:
            console.print(f"... and {len(results_list) - limit} more "
                           f"(use --full to show all, or --out result.json to save everything)")
    else:
        console.print(JSON(json.dumps(result, default=str)))


def cmd_ask(args):
    db = get_db()
    if args.question:
        questions = [args.question]
    else:
        console.print("[bold green]CRM AI Copilot[/bold green] -- ask a question "
                       "(examples: 'How many calls did Priya Sharma make this week?', "
                       "'exit' to quit)")
        questions = iter(lambda: console.input("[bold cyan]> [/bold cyan]"), "exit")

    for q in questions:
        if not q.strip():
            continue
        routed = route_multi(q, db)
        routes = routed.get("routes", [])

        if not routes:
            msg = routed.get("note") or (
                "Sorry, I couldn't match that to a supported question. "
                "Try `python cli.py list-intents` to see what's supported."
            )
            console.print(f"[yellow]{msg}[/yellow]")
            continue

        for i, r in enumerate(routes, 1):
            prefix = f"[{i}/{len(routes)}] " if len(routes) > 1 else ""
            console.print(f"[dim]{prefix}-> intent: {r['intent']}  params: {r['params']}  "
                           f"confidence: {r.get('confidence')}[/dim]")
            try:
                result = run_intent(db, r["intent"], **r["params"])
                print_result(result, full=args.full, out_path=args.out)
                if result.get("error"):
                    console.print(f"[yellow]{result['error']}[/yellow]")
            except ValueError as exc:
                console.print(f"[yellow]{exc}[/yellow]")

        if routed.get("note"):
            console.print(f"[yellow]Note: {routed['note']}[/yellow]")


def cmd_list_intents(_args):
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("intent")
    table.add_column("params")
    table.add_column("description")
    for name, entry in REGISTRY.items():
        table.add_row(name, ", ".join(entry["params"]) or "-", entry["description"])
    console.print(table)


def cmd_run(args):
    db = get_db()
    params = dict(kv.split("=", 1) for kv in args.param or [])
    result = run_intent(db, args.intent, **params)
    print_result(result, full=args.full, out_path=args.out)


def build_parser():
    parser = argparse.ArgumentParser(description="CRM AI Copilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", help="Ask a natural-language question")
    p_ask.add_argument("question", nargs="?", help="If omitted, starts an interactive REPL")
    p_ask.add_argument("--full", action="store_true", help="Show all result rows, not just the first 25")
    p_ask.add_argument("--out", help="Write the full JSON result to this file instead of printing a table")
    p_ask.set_defaults(func=cmd_ask)

    p_list = sub.add_parser("list-intents", help="List all supported questions")
    p_list.set_defaults(func=cmd_list_intents)

    p_run = sub.add_parser("run", help="Run a specific intent directly")
    p_run.add_argument("intent", choices=list(REGISTRY.keys()))
    p_run.add_argument("--param", action="append", help="key=value, repeatable")
    p_run.add_argument("--full", action="store_true", help="Show all result rows, not just the first 25")
    p_run.add_argument("--out", help="Write the full JSON result to this file instead of printing a table")
    p_run.set_defaults(func=cmd_run)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
