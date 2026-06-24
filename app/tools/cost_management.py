"""Tools for Azure Cost Management — spend queries and budgets.

Both features use the ARM REST API directly.  The Cost Management query
endpoint uses Microsoft.CostManagement/query (POST); budgets use
Microsoft.Consumption/budgets (GET).

Required role: Cost Management Reader (or Contributor) on the target scope.
"""
import requests
from config import credential
from tools.base import Tool

_ARM_BASE = "https://management.azure.com"
_COST_API = "2023-11-01"
_BUDGET_API = "2021-10-01"

_VALID_TIMEFRAMES = frozenset({
    "MonthToDate", "BillingMonthToDate",
    "TheLastMonth", "TheLastBillingMonth",
    "TheLastQuarter", "TheLastYear",
    "Custom",
})
_VALID_GROUP_BY = frozenset({
    "ResourceGroupName", "ServiceName", "ResourceType",
    "Location", "MeterSubCategory", "ResourceId",
})
_VALID_GRANULARITY = frozenset({"None", "Daily", "Monthly"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token() -> str:
    return credential.get_token("https://management.azure.com/.default").token


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _post(url: str, body: dict) -> dict:
    resp = requests.post(url, headers=_headers(), json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _get_req(url: str) -> dict:
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _scope_path(subscription_id: str, resource_group: str | None) -> str:
    base = f"/subscriptions/{subscription_id}"
    return f"{base}/resourceGroups/{resource_group}" if resource_group else base


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def _query_costs(
    subscription_id: str,
    timeframe: str = "MonthToDate",
    start_date: str | None = None,
    end_date: str | None = None,
    resource_group: str | None = None,
    group_by: str | None = None,
    granularity: str = "None",
) -> str:
    if timeframe not in _VALID_TIMEFRAMES:
        return f"[Error] Invalid timeframe '{timeframe}'. Valid: {', '.join(sorted(_VALID_TIMEFRAMES))}."
    if group_by and group_by not in _VALID_GROUP_BY:
        return f"[Error] Invalid group_by '{group_by}'. Valid: {', '.join(sorted(_VALID_GROUP_BY))}."
    if granularity not in _VALID_GRANULARITY:
        return f"[Error] Invalid granularity '{granularity}'. Valid: None, Daily, Monthly."
    if timeframe == "Custom" and not (start_date and end_date):
        return "[Error] start_date and end_date are required when timeframe is 'Custom'."

    dataset: dict = {
        "granularity": granularity,
        "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
    }
    if group_by:
        dataset["grouping"] = [{"type": "Dimension", "name": group_by}]

    body: dict = {"type": "ActualCost", "timeframe": timeframe, "dataset": dataset}
    if timeframe == "Custom":
        body["timePeriod"] = {"from": start_date, "to": end_date}

    scope = _scope_path(subscription_id, resource_group)
    url = f"{_ARM_BASE}{scope}/providers/Microsoft.CostManagement/query?api-version={_COST_API}"

    props = _post(url, body).get("properties", {})
    col_names = [c["name"] for c in props.get("columns", [])]
    rows = props.get("rows", [])

    if not rows:
        scope_label = f"resource group '{resource_group}'" if resource_group else f"subscription {subscription_id}"
        return f"No cost data for {scope_label} in timeframe '{timeframe}'."

    # Locate columns by name — the API returns them in varying order.
    col_map = {name: i for i, name in enumerate(col_names)}
    cost_col = next((n for n in col_names if n.lower() in ("cost", "pretaxcost")), col_names[0])
    currency_col = next((n for n in col_names if "currency" in n.lower()), None)
    date_col = next((n for n in col_names if n.lower() in ("usagedate", "billingmonth")), None)
    known = {cost_col, currency_col, date_col} - {None}
    group_col = next((n for n in col_names if n not in known), None) if group_by else None

    cost_idx = col_map[cost_col]
    currency = rows[0][col_map[currency_col]] if currency_col else "USD"
    date_idx = col_map[date_col] if date_col else None
    group_idx = col_map[group_col] if group_col else None

    scope_label = f"resource group '{resource_group}'" if resource_group else f"subscription {subscription_id}"
    header_parts = [f"Cost report — {timeframe}, {scope_label}"]
    if group_by:
        header_parts.append(f"grouped by {group_by}")
    if granularity != "None":
        header_parts.append(f"granularity={granularity}")
    lines = [", ".join(header_parts)]

    if granularity == "None":
        sorted_rows = sorted(rows, key=lambda r: float(r[cost_idx]), reverse=True)
        total = sum(float(r[cost_idx]) for r in sorted_rows)
        for row in sorted_rows:
            cost = float(row[cost_idx])
            label = str(row[group_idx]) if group_idx is not None else "Total"
            if not label:
                label = "(unassigned)"
            lines.append(f"  {label:<45}  {cost:>12.4f} {currency}")
        if group_by and len(sorted_rows) > 1:
            lines.append(f"  {'TOTAL':<45}  {total:>12.4f} {currency}")
    else:
        for row in rows:
            cost = float(row[cost_idx])
            date_val = str(row[date_idx])[:10] if date_idx is not None else ""
            group_val = str(row[group_idx]) if group_idx is not None else ""
            label = f"[{date_val}]" + (f"  {group_val}" if group_val else "")
            lines.append(f"  {label:<55}  {cost:>12.4f} {currency}")

    if props.get("nextLink"):
        lines.append("  (results truncated — narrow the time range or scope to see all)")

    return "\n".join(lines)


def _list_budgets(
    subscription_id: str,
    resource_group: str | None = None,
) -> str:
    scope = _scope_path(subscription_id, resource_group)
    url = f"{_ARM_BASE}{scope}/providers/Microsoft.Consumption/budgets?api-version={_BUDGET_API}"
    budgets = _get_req(url).get("value", [])

    scope_label = f"resource group '{resource_group}'" if resource_group else f"subscription {subscription_id}"
    if not budgets:
        return f"No budgets found for {scope_label}."

    lines = [f"Budgets for {scope_label}:"]
    for b in budgets:
        props = b.get("properties", {})
        name = b.get("name", "n/a")
        limit = float(props.get("amount", 0))
        time_grain = props.get("timeGrain", "n/a")
        current_spend = props.get("currentSpend", {})
        current = float(current_spend.get("amount", 0))
        currency = current_spend.get("unit", "USD")
        forecast_obj = props.get("forecastSpend", {})
        forecast = float(forecast_obj.get("amount")) if forecast_obj.get("amount") is not None else None

        pct = (current / limit * 100) if limit else 0
        bar_len = 20
        filled = min(int(pct / 5), bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)

        line = (
            f"  {name}\n"
            f"    [{bar}] {pct:.0f}%  "
            f"spent={current:.2f} / limit={limit:.2f} {currency}  ({time_grain})"
        )
        if forecast is not None:
            line += f"  forecast={forecast:.2f}"

        # Flag any breached notification thresholds
        for notif in props.get("notifications", {}).values():
            if notif.get("enabled") and pct >= notif.get("threshold", 100):
                line += f"  [ALERT: {notif['threshold']}% threshold breached]"
                break

        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="query_costs",
        description=(
            "Query Azure Cost Management to see actual spend for a subscription or resource group. "
            "Supports grouping by ResourceGroupName, ServiceName, ResourceType, Location, "
            "MeterSubCategory, or ResourceId. "
            "Use timeframe='MonthToDate' for current month, 'TheLastMonth' for last month, "
            "or 'Custom' with start_date/end_date for a specific range. "
            "Set granularity='Daily' or 'Monthly' to get a time series instead of totals."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "timeframe": {
                    "type": "string",
                    "default": "MonthToDate",
                    "description": (
                        "Time period to query. "
                        "One of: MonthToDate, BillingMonthToDate, TheLastMonth, "
                        "TheLastBillingMonth, TheLastQuarter, TheLastYear, Custom."
                    ),
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format. Required when timeframe is 'Custom'.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format. Required when timeframe is 'Custom'.",
                },
                "resource_group": {
                    "type": "string",
                    "description": "Scope the query to a single resource group. Omit for the entire subscription.",
                },
                "group_by": {
                    "type": "string",
                    "description": (
                        "Break down results by this dimension. "
                        "One of: ResourceGroupName, ServiceName, ResourceType, Location, "
                        "MeterSubCategory, ResourceId."
                    ),
                },
                "granularity": {
                    "type": "string",
                    "default": "None",
                    "description": "Time granularity. One of: None (totals), Daily, Monthly.",
                },
            },
            "required": ["subscription_id"],
        },
        func=_query_costs,
    ),
    Tool(
        name="list_budgets",
        description=(
            "List Azure Cost Management budgets for a subscription or resource group, showing "
            "the limit, current spend, percentage used, and whether any alert thresholds are breached."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "subscription_id": {"type": "string"},
                "resource_group": {
                    "type": "string",
                    "description": "List budgets scoped to this resource group. Omit for subscription-level budgets.",
                },
            },
            "required": ["subscription_id"],
        },
        func=_list_budgets,
    ),
]
