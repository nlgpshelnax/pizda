import argparse
import json
from pathlib import Path

from trip_data.evals import evaluate

parser = argparse.ArgumentParser()
parser.add_argument("--cases", type=Path, default=Path("data/evals/data-cases.json"))
parser.add_argument("--output", type=Path, default=Path(".runtime/data-evals.json"))
args = parser.parse_args()
report = evaluate(args.cases, Path("data/fixtures/sochi.json"))
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False))
raise SystemExit(0 if report["total"] and not report["failed"] else 1)
