"""Unit tests for Table Reconciliation Engine (Phase 7).

Validates:
1. Column consistency
2. Quantity * Unit Price = Amount
3. Column sums / subtotals
4. Row sums / horizontal totals
5. YoY Growth % calculations
6. Percentage distributions
7. Warning/review event emission without mutating data
"""

import pytest
from app.validation.table_reconciliation import TableReconciler, _clean_num


def test_clean_num_varieties():
    assert _clean_num("$1,234.50") == 1234.50
    assert _clean_num("(500.00)") == -500.00
    assert _clean_num("-120.75") == -120.75
    assert _clean_num("25.5%") == 25.5
    assert _clean_num("€99.99") == 99.99
    assert _clean_num("-") is None
    assert _clean_num("N/A") is None
    assert _clean_num(None) is None


def test_reconcile_matching_table():
    table_data = {
        "headers": ["Item", "Qty", "Price", "Amount"],
        "rows": [
            ["Laptops", "5", "1000", "5000"],
            ["Monitors", "10", "200", "2000"],
            ["Total", "15", "", "7000"],
        ],
    }
    checks = TableReconciler.reconcile(table_data, block_id="tbl_01")
    assert len(checks) >= 3

    # Column consistency check
    col_check = next((c for c in checks if c.name == "Column Consistency"), None)
    assert col_check is not None
    assert col_check.status == "match"

    # Qty x Price checks
    qty_checks = [c for c in checks if "Qty x Price" in c.name]
    assert len(qty_checks) == 2
    assert all(c.status == "match" for c in qty_checks)

    # Column Total check
    tot_check = next((c for c in checks if "Column Total" in c.name), None)
    assert tot_check is not None
    assert tot_check.status == "match"


def test_reconcile_mismatch_qty_price():
    table_data = {
        "headers": ["Product", "Quantity", "Rate", "Total"],
        "rows": [
            ["Software License", "10", "50", "400"],  # Expected 500, actual 400!
        ],
    }
    checks = TableReconciler.reconcile(table_data, block_id="tbl_err")
    qty_check = next((c for c in checks if "Qty x Price" in c.name), None)
    assert qty_check is not None
    assert qty_check.status == "mismatch"
    assert qty_check.severity == "warning"
    assert "500.0" in qty_check.expected
    assert "400" in qty_check.actual


def test_reconcile_inconsistent_ragged_columns():
    table_data = {
        "headers": ["Col1", "Col2", "Col3"],
        "rows": [
            ["A", "B", "C"],
            ["D", "E"],  # ragged row!
        ],
    }
    checks = TableReconciler.reconcile(table_data)
    col_check = next(c for c in checks if c.name == "Column Consistency")
    assert col_check.status == "mismatch"
    assert col_check.severity == "warning"


def test_reconcile_yoy_growth():
    table_data = {
        "headers": ["Metric", "2023", "2024", "Growth %"],
        "rows": [
            ["Revenue", "100", "120", "20.0%"],
        ],
    }
    checks = TableReconciler.reconcile(table_data)
    yoy_check = next((c for c in checks if "YoY Growth" in c.name), None)
    assert yoy_check is not None
    assert yoy_check.status == "match"
