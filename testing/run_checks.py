"""Run every testing/checks/verify_*.py.

One deliberate difference from SME_creditmemo's runner: there is no
"skipped for missing data" state. In this project missing data is a conclusion
to be asserted, not a reason for a check to excuse itself.
"""

import subprocess
import sys
from pathlib import Path

CHECKS = Path(__file__).resolve().parent / "checks"


def main() -> int:
    scripts = sorted(CHECKS.glob("verify_*.py"))
    if not scripts:
        print("No checks found in testing/checks/")
        return 1

    failures: list[str] = []
    for script in scripts:
        print(f"{script.stem}")
        result = subprocess.run(
            [sys.executable, script.name], cwd=CHECKS,
            capture_output=True, text=True,
        )
        sys.stdout.write(result.stdout)
        if result.returncode != 0:
            sys.stdout.write(result.stderr)
            failures.append(script.stem)

    passed = len(scripts) - len(failures)
    print(f"\npassed {passed} | failed {len(failures)}")
    if failures:
        print("failed: " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
