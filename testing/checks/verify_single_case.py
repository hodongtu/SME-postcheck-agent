"""One run reviews one dossier, and says so loudly when it cannot.

Upload boxes are the subdirectories of a case, so a caller who points at the
parent folder holding several cases would have two customers' documents merged
into one Facts, and the rules would grade a dossier that does not exist. That
failure is silent and severe, which is why read_case_documents raises rather
than warns - and why this check exists to keep it raising.
"""

from _harness import report
import shutil
import sys
import tempfile
from pathlib import Path


def _build_case(root: Path, case_id: str, filename: str) -> None:
    box = root / case_id / "ho_so_phap_ly"
    box.mkdir(parents=True, exist_ok=True)
    (box / filename).write_text("MST: 0101234567\n", encoding="utf-8")


def main() -> int:
    from src.config import Config
    from src.pipeline import MultipleCasesError, read_case_documents

    problems: list[str] = []
    workspace = Path(tempfile.mkdtemp(prefix="postcheck_single_case_"))
    try:
        _build_case(workspace, "case_a", "giay_dang_ky_kinh_doanh_a.txt")
        _build_case(workspace, "case_b", "giay_dang_ky_kinh_doanh_b.txt")

        # Pointing at the parent of two cases must raise.
        try:
            read_case_documents(workspace, Config())
        except MultipleCasesError:
            pass
        except Exception as exc:                      # noqa: BLE001
            problems.append(
                f"pointing at a parent of two cases raised {type(exc).__name__}, "
                f"expected MultipleCasesError"
            )
        else:
            problems.append(
                "pointing at a parent of two cases was accepted - two customers' "
                "documents would be merged into one Facts"
            )

        # Pointing at one case must work and see only that case's files.
        documents = read_case_documents(workspace / "case_a", Config())
        names = sorted(document.filename for document in documents)
        if names != ["giay_dang_ky_kinh_doanh_a.txt"]:
            problems.append(f"a single case read the wrong files: {names}")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    return report(
        problems,
        "a directory holding two dossiers raises; a single case directory reads "
        "only its own files",
    )


if __name__ == "__main__":
    sys.exit(main())
