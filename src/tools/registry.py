"""Every query tool the pipeline calls, checked at import time.

A tool listed here must be invoked by src/pipeline.py - `verify_tools_are_used`
asserts that, so the registry cannot claim a connection that does not exist.
"""

from __future__ import annotations

from src.tools._executor import assert_no_model_arguments, assert_registry_is_sound
from src.tools.amc import get_amc_recovery_list
from src.tools.los import (
    get_los_approval,
    get_los_financials_online,
    get_los_shareholders,
    get_los_sitevisit_online,
)
from src.tools.blwl import get_blacklist_watchlist
from src.tools.cic import (
    get_cic_collateral,
    get_cic_debt_groups,
    get_cic_shareholder_debt_groups,
)
from src.tools.portfolio import get_portfolio
from src.tools.t24 import (
    get_cashflow_pdld,
    get_collateral,
    get_outstanding,
    get_t24_facilities,
    get_transaction_summary,
)
from src.tools.virac import get_virac_financials


ALL_TOOLS = (
    get_los_approval,
    get_los_shareholders,
    get_los_sitevisit_online,
    get_los_financials_online,
    get_cic_debt_groups,
    get_cic_shareholder_debt_groups,
    get_cic_collateral,
    get_blacklist_watchlist,
    get_amc_recovery_list,
    get_t24_facilities,
    get_collateral,
    get_outstanding,
    get_portfolio,
    get_cashflow_pdld,
    get_transaction_summary,
    get_virac_financials,
)

assert_registry_is_sound(ALL_TOOLS)
assert_no_model_arguments(ALL_TOOLS)
