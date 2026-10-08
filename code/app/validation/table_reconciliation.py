"""Deterministic table validation and reconciliation engine.

Runs arithmetic and structural integrity checks:
1. Column/row consistency
2. Subtotal vs component sums
3. Total vs subtotal
4. Quantity * Unit Price = Amount
5. Percentage relationships
6. Year-over-Year (YoY) calculations

Mismatches emit ValidationEvents without corrupting extracted data.
"""

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass
class ReconciliationCheck:
    name: str
    expected: str
    actual: str
    difference: str
    status: str  # match, mismatch, unable_to_check
    severity: str  # info, warning, error
    block_id: str | None = None
    table_index: int = 0
    row_index: int | None = None
    col_index: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _clean_num(val: Any) -> float | None:
    """Parse numeric values from table cells, handling currencies, commas, parentheses."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in ("-", "—", "N/A", "na", "null"):
        return None
    # Remove currency symbols and spaces
    s = re.sub(r"[\$,€,£,¥]", "", s).strip()
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    elif s.endswith("%"):
        s = s[:-1].strip()

    s = s.replace(",", "")
    try:
        val_float = float(s)
        return -val_float if is_negative else val_float
    except ValueError:
        return None


class TableReconciler:
    TOLERANCE = 0.05  # 5 cents / 0.05% tolerance for rounding

    @classmethod
    def reconcile(cls, table_data: dict[str, Any], block_id: str | None = None) -> list[ReconciliationCheck]:
        """Run all deterministic validation checks on a structured table."""
        checks: list[ReconciliationCheck] = []
        headers = [str(h).strip() for h in table_data.get("headers", [])]
        rows = table_data.get("rows", [])

        if not rows:
            return checks

        # 1. Structural column consistency check
        expected_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
        inconsistent_rows = [i for i, r in enumerate(rows) if len(r) != expected_cols]
        if inconsistent_rows:
            checks.append(
                ReconciliationCheck(
                    name="Column Consistency",
                    expected=f"{expected_cols} columns per row",
                    actual=f"Rows {inconsistent_rows[:3]} have different column count",
                    difference=f"{len(inconsistent_rows)} ragged rows",
                    status="mismatch",
                    severity="warning",
                    block_id=block_id,
                )
            )
        else:
            checks.append(
                ReconciliationCheck(
                    name="Column Consistency",
                    expected=f"{expected_cols} columns",
                    actual=f"{expected_cols} columns",
                    difference="0",
                    status="match",
                    severity="info",
                    block_id=block_id,
                )
            )

        # 2. Check: Quantity * Unit Price = Total / Amount
        cls._check_qty_price(headers, rows, checks, block_id)

        # 3. Check: Column Sum / Subtotal vs Component rows
        cls._check_column_totals(headers, rows, checks, block_id)

        # 4. Check: Row Sums / Totals across categories
        cls._check_row_totals(headers, rows, checks, block_id)

        # 5. Check: YoY Growth % = (Current - Prior) / Prior
        cls._check_yoy_growth(headers, rows, checks, block_id)

        # 6. Check: Percentage shares sum to ~100%
        cls._check_percentages(headers, rows, checks, block_id)

        return checks

    @classmethod
    def _check_qty_price(cls, headers: list[str], rows: list[list[Any]], checks: list[ReconciliationCheck], block_id: str | None):
        h_lower = [h.lower() for h in headers]
        qty_idx = next((i for i, h in enumerate(h_lower) if any(k in h for k in ("qty", "quantity", "units"))), None)
        price_idx = next((i for i, h in enumerate(h_lower) if any(k in h for k in ("price", "rate", "unit cost"))), None)
        amt_idx = next((i for i, h in enumerate(h_lower) if any(k in h for k in ("amount", "total", "line total", "ext price"))), None)

        if qty_idx is not None and price_idx is not None and amt_idx is not None:
            for r_idx, row in enumerate(rows):
                if len(row) <= max(qty_idx, price_idx, amt_idx):
                    continue
                q = _clean_num(row[qty_idx])
                p = _clean_num(row[price_idx])
                a = _clean_num(row[amt_idx])
                if q is not None and p is not None and a is not None and q > 0 and p > 0:
                    expected = round(q * p, 2)
                    diff = round(abs(expected - a), 2)
                    if diff <= cls.TOLERANCE:
                        checks.append(ReconciliationCheck(
                            name=f"Qty x Price (Row {r_idx + 1})",
                            expected=f"${expected:,.2f}",
                            actual=f"${a:,.2f}",
                            difference="0.00",
                            status="match",
                            severity="info",
                            block_id=block_id,
                            row_index=r_idx,
                        ))
                    else:
                        checks.append(ReconciliationCheck(
                            name=f"Qty x Price Mismatch (Row {r_idx + 1})",
                            expected=f"${expected:,.2f}",
                            actual=f"${a:,.2f}",
                            difference=f"${diff:,.2f}",
                            status="mismatch",
                            severity="error",
                            block_id=block_id,
                            row_index=r_idx,
                        ))

    @classmethod
    def _check_column_totals(cls, headers: list[str], rows: list[list[Any]], checks: list[ReconciliationCheck], block_id: str | None):
        total_rows = []
        for r_idx, row in enumerate(rows):
            first_cell = str(row[0]).strip().lower() if row else ""
            if any(k in first_cell for k in ("total", "subtotal", "sum", "consolidated")):
                total_rows.append((r_idx, first_cell, row))

        num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
        for col_idx in range(1, num_cols):
            col_name = headers[col_idx] if col_idx < len(headers) else f"Col {col_idx}"
            for total_r_idx, label, t_row in total_rows:
                if col_idx >= len(t_row):
                    continue
                actual_total = _clean_num(t_row[col_idx])
                if actual_total is None:
                    continue

                # Sum numeric rows above this total row
                component_sum = 0.0
                component_count = 0
                for r_idx in range(total_r_idx):
                    if col_idx < len(rows[r_idx]):
                        val = _clean_num(rows[r_idx][col_idx])
                        if val is not None:
                            component_sum += val
                            component_count += 1

                if component_count >= 2:
                    diff = round(abs(component_sum - actual_total), 2)
                    check_name = f"{label.title()} Check ({col_name})"
                    if diff <= cls.TOLERANCE or (actual_total != 0 and diff / abs(actual_total) < 0.005):
                        checks.append(ReconciliationCheck(
                            name=check_name,
                            expected=f"{component_sum:,.2f}",
                            actual=f"{actual_total:,.2f}",
                            difference="0.00",
                            status="match",
                            severity="info",
                            block_id=block_id,
                            row_index=total_r_idx,
                            col_index=col_idx,
                        ))
                    else:
                        checks.append(ReconciliationCheck(
                            name=f"{check_name} Mismatch",
                            expected=f"{component_sum:,.2f}",
                            actual=f"{actual_total:,.2f}",
                            difference=f"{diff:,.2f}",
                            status="mismatch",
                            severity="warning",
                            block_id=block_id,
                            row_index=total_r_idx,
                            col_index=col_idx,
                        ))

    @classmethod
    def _check_row_totals(cls, headers: list[str], rows: list[list[Any]], checks: list[ReconciliationCheck], block_id: str | None):
        h_lower = [h.lower() for h in headers]
        total_col_idx = next((i for i, h in enumerate(h_lower) if h in ("total", "sum")), None)
        if total_col_idx is not None and total_col_idx > 1:
            for r_idx, row in enumerate(rows):
                first_cell = str(row[0]).strip().lower() if row else ""
                if "total" in first_cell:
                    continue
                if total_col_idx < len(row):
                    actual_row_total = _clean_num(row[total_col_idx])
                    if actual_row_total is not None:
                        comp_sum = 0.0
                        comp_count = 0
                        for c_idx in range(1, total_col_idx):
                            val = _clean_num(row[c_idx])
                            if val is not None:
                                comp_sum += val
                                comp_count += 1
                        if comp_count >= 2:
                            diff = round(abs(comp_sum - actual_row_total), 2)
                            if diff <= cls.TOLERANCE:
                                checks.append(ReconciliationCheck(
                                    name=f"Row Total (Row {r_idx + 1}: {row[0]})",
                                    expected=f"{comp_sum:,.2f}",
                                    actual=f"{actual_row_total:,.2f}",
                                    difference="0.00",
                                    status="match",
                                    severity="info",
                                    block_id=block_id,
                                    row_index=r_idx,
                                ))
                            else:
                                checks.append(ReconciliationCheck(
                                    name=f"Row Total Mismatch (Row {r_idx + 1})",
                                    expected=f"{comp_sum:,.2f}",
                                    actual=f"{actual_row_total:,.2f}",
                                    difference=f"{diff:,.2f}",
                                    status="mismatch",
                                    severity="warning",
                                    block_id=block_id,
                                    row_index=r_idx,
                                ))

    @classmethod
    def _check_yoy_growth(cls, headers: list[str], rows: list[list[Any]], checks: list[ReconciliationCheck], block_id: str | None):
        h_lower = [h.lower() for h in headers]
        growth_idx = next((i for i, h in enumerate(h_lower) if any(k in h for k in ("growth", "change", "yoy", "%"))), None)
        # Find years like 2023, 2024
        year_cols = []
        for i, h in enumerate(headers):
            m = re.search(r"\b(20\d\d)\b", h)
            if m:
                year_cols.append((int(m.group(1)), i))
        year_cols.sort(key=lambda x: x[0])

        if len(year_cols) >= 2 and growth_idx is not None:
            prior_idx = year_cols[-2][1]
            curr_idx = year_cols[-1][1]
            for r_idx, row in enumerate(rows):
                if len(row) <= max(prior_idx, curr_idx, growth_idx):
                    continue
                prior = _clean_num(row[prior_idx])
                curr = _clean_num(row[curr_idx])
                actual_pct = _clean_num(row[growth_idx])
                if prior is not None and curr is not None and actual_pct is not None and prior != 0:
                    expected_pct = round(((curr - prior) / abs(prior)) * 100, 1)
                    # actual_pct could be 0.12 or 12
                    norm_actual = actual_pct if abs(actual_pct) > 1.0 else actual_pct * 100
                    diff = round(abs(expected_pct - norm_actual), 1)
                    if diff <= 1.0:
                        checks.append(ReconciliationCheck(
                            name=f"YoY Growth (Row {r_idx + 1})",
                            expected=f"{expected_pct:.1f}%",
                            actual=f"{norm_actual:.1f}%",
                            difference="0.0%",
                            status="match",
                            severity="info",
                            block_id=block_id,
                            row_index=r_idx,
                        ))
                    else:
                        checks.append(ReconciliationCheck(
                            name=f"YoY Growth Mismatch (Row {r_idx + 1})",
                            expected=f"{expected_pct:.1f}%",
                            actual=f"{norm_actual:.1f}%",
                            difference=f"{diff:.1f}%",
                            status="mismatch",
                            severity="warning",
                            block_id=block_id,
                            row_index=r_idx,
                        ))

    @classmethod
    def _check_percentages(cls, headers: list[str], rows: list[list[Any]], checks: list[ReconciliationCheck], block_id: str | None):
        h_lower = [h.lower() for h in headers]
        pct_idx = next((i for i, h in enumerate(h_lower) if any(k in h for k in ("share", "percent", "pct", "%"))), None)
        if pct_idx is not None:
            pct_values = []
            for row in rows:
                if pct_idx < len(row):
                    v = _clean_num(row[pct_idx])
                    if v is not None:
                        pct_values.append(v if abs(v) > 1.0 else v * 100)
            if len(pct_values) >= 2:
                total_pct = sum(pct_values)
                # If sum is near 100
                if 95 <= total_pct <= 105:
                    diff = round(abs(total_pct - 100.0), 1)
                    checks.append(ReconciliationCheck(
                        name="Percentage Share Sum",
                        expected="100.0%",
                        actual=f"{total_pct:.1f}%",
                        difference=f"{diff:.1f}%",
                        status="match" if diff <= 1.5 else "mismatch",
                        severity="info" if diff <= 1.5 else "warning",
                        block_id=block_id,
                    ))
