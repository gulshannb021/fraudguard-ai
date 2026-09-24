import json
import sys
from pathlib import Path

# Make sure backend/ is available on the Python path
BACKEND_DIR = Path(__file__).resolve().parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.investigator import Investigator
from app.config import CASES_DIR


def main():
    print("=" * 60)
    print("FraudGuard AI — HHGOA Benchmark Runner")
    print("=" * 60)

    investigator = Investigator()

    try:
        generated_files = investigator.run_all()

        print()
        print("=" * 60)
        print("INVESTIGATION COMPLETE")
        print("=" * 60)

        print(f"Cases generated: {len(generated_files)}")
        print(f"Output directory: {CASES_DIR}")
        print()

        # Validate every generated JSON file
        valid = 0
        invalid = 0

        for file_path in generated_files:

            path = Path(file_path)

            try:
                with path.open(
                    "r",
                    encoding="utf-8",
                ) as file:
                    data = json.load(file)

                required = {
                    "case_id",
                    "case",
                    "evidence_requests",
                    "next_best_actions",
                    "sar",
                    "stop_reason",
                    "tool_calls",
                    "tokens",
                    "latency_s",
                }

                missing = required - set(data.keys())

                if missing:
                    print(
                        f"[INVALID] {path.name}: "
                        f"missing {sorted(missing)}"
                    )
                    invalid += 1
                    continue

                print(
                    f"[OK] {path.name} | "
                    f"verdict={data['case']['verdict']} | "
                    f"pattern={data['case']['pattern']} | "
                    f"probability={data['case']['fraud_probability']}"
                )

                valid += 1

            except Exception as exc:

                print(
                    f"[INVALID] {path.name}: {exc}"
                )

                invalid += 1

        print()
        print("=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

        print(f"Valid JSON cases : {valid}")
        print(f"Invalid cases    : {invalid}")

        if valid == 20 and invalid == 0:
            print()
            print("SUCCESS: All 20 benchmark cases generated successfully.")
        else:
            print()
            print(
                "WARNING: Expected 20 valid benchmark cases."
            )

    finally:
        investigator.close()


if __name__ == "__main__":
    main()