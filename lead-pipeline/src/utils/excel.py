"""Excel read/write helpers. All operations use UTF-8 and openpyxl engine."""
import logging
from pathlib import Path

import openpyxl
import pandas as pd

logger = logging.getLogger(__name__)

FORMULA_ERROR_STRINGS = ("#REF!", "#DIV/0!", "#NAME?", "#VALUE!", "#NULL!", "#N/A", "#NUM!")


def read_sheet(path: Path, sheet_name: str, header_row: int = 0) -> pd.DataFrame:
    """Read an Excel sheet into a DataFrame."""
    return pd.read_excel(
        path,
        sheet_name=sheet_name,
        header=header_row,
        engine="openpyxl",
    )


def write_dataframe_to_xlsx(df: pd.DataFrame, path: Path, sheet_name: str = "Sheet1") -> None:
    """Write a DataFrame to an Excel file with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, sheet_name=sheet_name, engine="openpyxl")
    logger.info("Wrote %d rows to %s [%s]", len(df), path, sheet_name)


def validate_no_formula_errors(path: Path) -> bool:
    """Return True if the workbook contains no formula error strings in cell values."""
    wb = openpyxl.load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and any(
                    err in cell.value for err in FORMULA_ERROR_STRINGS
                ):
                    logger.warning(
                        "Formula error at %s!%s: %s",
                        ws.title,
                        cell.coordinate,
                        cell.value,
                    )
                    return False
    return True
