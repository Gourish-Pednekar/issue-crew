"""Summarize eval/results.csv as markdown tables.

Usage: python eval/summarize.py [--model openai/gpt-oss-120b]
"""
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent / "results.csv"


def to_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_true(value):
    return str(value).strip().lower() == "true"


def nums(rows, field):
    vals = [to_num(r[field]) for r in rows]
    return [v for v in vals if v is not None]


def mean_or_dash(vals, fmt):
    return fmt.format(statistics.mean(vals)) if vals else "-"


def summarize(rows):
    n = len(rows)
    resolved = sum(is_true(r["resolved"]) for r in rows)
    reviewed = [r for r in rows if r["approved"] not in ("", None)]
    approved = sum(is_true(r["approved"]) for r in reviewed)
    tokens = nums(rows, "tokens")
    return {
        "runs": n,
        "resolved": f"{resolved}/{n}",
        "approved": f"{approved}/{len(reviewed)}" if reviewed else "-",
        "tokens": mean_or_dash(tokens, "{:,.0f}"),
        "range": f"{min(tokens):,.0f}-{max(tokens):,.0f}" if tokens else "-",
        "steps": mean_or_dash(nums(rows, "steps"), "{:.1f}"),
        "seconds": mean_or_dash(nums(rows, "seconds"), "{:.0f}"),
    }


def print_table(title, grouped, label_cols):
    print(f"\n### {title}\n")
    header = label_cols + [
        "runs", "resolved", "approved", "mean tokens",
        "token range", "mean steps", "mean seconds",
    ]
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for key in sorted(grouped):
        s = summarize(grouped[key])
        cells = list(key) + [
            s["runs"], s["resolved"], s["approved"], s["tokens"],
            s["range"], s["steps"], s["seconds"],
        ]
        print("| " + " | ".join(str(c) for c in cells) + " |")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="only include rows for this model")
    args = parser.parse_args()

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.model:
        rows = [r for r in rows if r["model"] == args.model]
    if not rows:
        raise SystemExit("no rows to summarize")

    by_task = defaultdict(list)
    by_agent = defaultdict(list)
    for r in rows:
        by_task[(r["task"], r["agent"])].append(r)
        by_agent[(r["agent"],)].append(r)

    print(f"Model(s): {', '.join(sorted({r['model'] for r in rows}))}")
    print_table("Per task", by_task, ["task", "agent"])
    print_table("Per agent (all tasks)", by_agent, ["agent"])


if __name__ == "__main__":
    main()