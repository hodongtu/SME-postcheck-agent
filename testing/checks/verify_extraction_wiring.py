"""The extraction registry points at real SME_creditmemo functions.

Each pass names a chain builder, an extract function, two PostcheckDocument
slots, a Config attribute and a document-matrix predicate. Every one of those
is a place the wiring can silently drift, and drift shows up as an empty
extraction rather than an error - which the rules would then read as missing
data and report as an unchecked criterion.
"""

from _harness import report
import inspect
import sys


def main() -> int:
    from dataclasses import fields
    from src.agents.documents import document_matrix
    from src.config import Config
    from src.passes import EXTRACTION_PASSES, ExtractionPass
    from src.types import PostcheckDocument

    problems: list[str] = []
    document_fields = set(PostcheckDocument.__dataclass_fields__)
    config_fields = set(Config.__dataclass_fields__)

    if "batch" in {field.name for field in fields(ExtractionPass)}:
        problems.append(
            "ExtractionPass still has a 'batch' field - post-check runs one "
            "document per call"
        )

    matrix_predicates = {
        name for name in dir(document_matrix)
        if name.startswith("is_") and name.endswith("_type")
    }

    for extraction_pass in EXTRACTION_PASSES:
        label = extraction_pass.label
        for attribute in (extraction_pass.result_attr, extraction_pass.error_attr):
            if attribute not in document_fields:
                problems.append(f"{label}: PostcheckDocument has no '{attribute}'")
        if extraction_pass.llm_attr not in config_fields:
            problems.append(f"{label}: Config has no '{extraction_pass.llm_attr}'")

        predicate = getattr(extraction_pass.applies_to, "__name__", "")
        if predicate not in matrix_predicates:
            problems.append(
                f"{label}: applies_to is '{predicate}', not one of the document "
                f"matrix predicates {sorted(matrix_predicates)}"
            )

        module = getattr(extraction_pass.extract, "__module__", "")
        if not module.startswith("src.agents.extraction."):
            problems.append(
                f"{label}: extract comes from '{module}', expected a module copied "
                f"from SME_creditmemo"
            )
        try:
            inspect.signature(extraction_pass.extract).bind(None, "", "", "")
        except TypeError as exc:
            problems.append(f"{label}: extract does not accept the runner's call - {exc}")
        try:
            inspect.signature(extraction_pass.build_chain).bind(None)
        except TypeError as exc:
            problems.append(f"{label}: build_chain does not accept one llm - {exc}")

    labels = [extraction_pass.label for extraction_pass in EXTRACTION_PASSES]
    if len(set(labels)) != len(labels):
        problems.append("duplicate pass labels")

    return report(problems, f"{len(EXTRACTION_PASSES)} passes wired to {', '.join(labels)}")


if __name__ == "__main__":
    sys.exit(main())
