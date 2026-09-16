"""Every query tool the pipeline calls, checked at import time.

A tool listed here must be invoked by src/pipeline.py - `verify_tools_are_used`
asserts that, so the registry cannot claim a connection that does not exist.
"""

from __future__ import annotations

from src.tools._executor import assert_no_model_arguments
from src.tools.bcde import get_bcde_blwl, get_bcde_cic
from src.tools.bep import get_bep_approval
from src.tools.t24 import get_cashflow_pdld, get_collateral, get_t24_facilities
from src.tools.virac import get_virac_financials


ALL_TOOLS = (
    get_bep_approval,
    get_bcde_cic,
    get_bcde_blwl,
    get_t24_facilities,
    get_collateral,
    get_cashflow_pdld,
    get_virac_financials,
)

assert_no_model_arguments(ALL_TOOLS)
