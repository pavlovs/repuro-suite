"""SUSA-to-Model updater: reads trial balance data, generates PowerShell COM script to update .xlsx financial models."""

from __future__ import annotations

import json
import os
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Accounts that are naturally Haben (credit) → positive in model.
# Used for validation warnings only — sign convention uses S/H flag directly.
POSITIVE_IN_MODEL: set[str] = {
    # Revenue (8xxx Haben-normal)
    "8120",
    "8125",
    "8150",
    "8315",
    "8340",
    "8400",
    "8401",
    "8601",
    "8603",
    "8605",
    "8611",
    "8820",
    "8925",
    # Cost reductions (Skonti/Boni received)
    "3730",
    "3731",
    "3736",
    "3737",
    "3748",
    "3760",
    # Interest / neutral income
    "2520",
    "2650",
    "2658",
    "2660",
    "2684",
    "2700",
    "2705",
    "2732",
    "2735",
    "2742",
    "2743",
    "2749",
    # Tax refunds
    "2203",
    "2210",
    "2281",
    "2283",
}

DEFAULT_SKIP_ACCOUNTS: set[str] = {"2870"}  # Vorabausschüttung — not in P&L models

# Spot-check accounts printed in summary
SPOT_CHECK_ACCOUNTS: list[str] = ["8400", "3400", "4120", "3960"]

# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SourceConfig:
    """One data-source column to write into the model."""

    name: str  # e.g. "fy2025", "ytd2026_apr"
    target_column: int  # Excel column number (8=H, 9=I, …)

    susa_xlsx_path: Optional[str] = None
    susa_json_path: Optional[str] = None
    susa_data: Optional[dict] = (
        None  # {"konto": [saldo, is_soll], …} or {"konto": {"saldo": …, "is_soll": …}}
    )

    # Column indices (0-based) inside SUSA xlsx
    xlsx_account_col: int = 0
    xlsx_saldo_col: int = 5
    xlsx_sh_col: int = 6


@dataclass
class UpdateConfig:
    """Full config for one model-update run."""

    deal_folder: str
    model_subfolder: str
    model_filename: str
    guv_sheet_name: str

    sources: list[SourceConfig]

    header_updates: list[tuple[int, int, str]] = field(default_factory=list)
    crosschecks: dict[str, float] = field(default_factory=dict)
    skip_accounts: set[str] = field(default_factory=lambda: set(DEFAULT_SKIP_ACCOUNTS))

    ps1_output_path: str = ""
    temp_dir: str = r"C:\Users\X1\Documents\CLAUDE_COWORK"


@dataclass
class UpdateResult:
    """Returned by generate_update()."""

    ps1_path: str
    total_writes: int
    skipped: dict[
        str, list[tuple[str, float, bool]]
    ]  # source_name → [(konto, saldo, is_soll), …]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Sign convention
# ---------------------------------------------------------------------------


def model_value(saldo: float, is_soll: bool) -> float:
    """Soll → negative, Haben → positive. Universal for SKR03 GuV accounts."""
    return -saldo if is_soll else saldo


# ---------------------------------------------------------------------------
# SUSA xlsx reader
# ---------------------------------------------------------------------------


def read_susa_xlsx(
    path: str,
    account_col: int = 0,
    saldo_col: int = 5,
    sh_col: int = 6,
) -> dict[str, tuple[float, bool]]:
    """Read SUSA xlsx → {konto_str: (saldo, is_soll)}."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    result: dict[str, tuple[float, bool]] = {}

    for row in ws.iter_rows(min_row=1, values_only=True):
        if row is None:
            continue
        # Ensure row has enough columns
        if len(row) <= max(account_col, saldo_col, sh_col):
            continue

        raw_acct = row[account_col]
        if raw_acct is None:
            continue

        # Parse account number
        try:
            acct_num = int(float(str(raw_acct).strip()))
        except (ValueError, TypeError):
            continue

        if not 2000 <= acct_num <= 9999:
            continue

        raw_saldo = row[saldo_col]
        if raw_saldo is None or raw_saldo == "" or raw_saldo == 0:
            continue

        try:
            saldo = float(raw_saldo)
        except (ValueError, TypeError):
            continue

        raw_sh = row[sh_col]
        if raw_sh is None:
            continue
        sh_str = str(raw_sh).strip().upper()
        is_soll = sh_str.startswith("S")

        konto_str = str(acct_num)
        result[konto_str] = (abs(saldo), is_soll)

    wb.close()
    return result


# ---------------------------------------------------------------------------
# SUSA JSON reader
# ---------------------------------------------------------------------------


def read_susa_json(path: str) -> dict[str, tuple[float, bool]]:
    """Read JSON file → {konto_str: (saldo, is_soll)}."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    result: dict[str, tuple[float, bool]] = {}
    for konto, val in raw.items():
        konto_str = str(int(float(konto)))
        if isinstance(val, dict):
            saldo = float(val["saldo"])
            is_soll = bool(val["is_soll"])
        elif isinstance(val, (list, tuple)):
            saldo = float(val[0])
            is_soll = bool(val[1])
        else:
            raise ValueError(f"Unexpected value type for konto {konto}: {type(val)}")
        result[konto_str] = (abs(saldo), is_soll)

    return result


# ---------------------------------------------------------------------------
# SUSA dict normalizer
# ---------------------------------------------------------------------------


def normalize_susa_dict(data: dict) -> dict[str, tuple[float, bool]]:
    """Normalize inline susa_data to standard format."""
    result: dict[str, tuple[float, bool]] = {}
    for konto, val in data.items():
        konto_str = str(int(float(str(konto))))
        if isinstance(val, dict):
            saldo = float(val["saldo"])
            is_soll = bool(val["is_soll"])
        elif isinstance(val, (list, tuple)):
            saldo = float(val[0])
            is_soll = bool(val[1])
        else:
            raise ValueError(f"Unexpected value type for konto {konto}: {type(val)}")
        result[konto_str] = (abs(saldo), is_soll)
    return result


# ---------------------------------------------------------------------------
# Model reader
# ---------------------------------------------------------------------------


def read_model_account_map(path: str, sheet_name: str) -> dict[str, int]:
    """Read GuV-Konten sheet → {konto_str: row_number}."""
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet_name]
    result: dict[str, int] = {}

    for row_idx, row in enumerate(
        ws.iter_rows(min_row=1, min_col=2, max_col=2, values_only=True), start=1
    ):
        cell_val = row[0]
        if cell_val is None:
            continue
        try:
            acct_num = int(float(str(cell_val).strip()))
        except (ValueError, TypeError):
            continue
        if 2000 <= acct_num <= 9999:
            konto_str = str(acct_num)
            if konto_str in result:
                # Duplicate account — keep first occurrence, warn later
                continue
            result[konto_str] = row_idx

    wb.close()
    return result


# ---------------------------------------------------------------------------
# Resolve source data
# ---------------------------------------------------------------------------


def resolve_source(source: SourceConfig) -> dict[str, tuple[float, bool]]:
    """Load SUSA data from whichever input the source config specifies."""
    if source.susa_data is not None:
        return normalize_susa_dict(source.susa_data)
    elif source.susa_xlsx_path is not None:
        return read_susa_xlsx(
            source.susa_xlsx_path,
            account_col=source.xlsx_account_col,
            saldo_col=source.xlsx_saldo_col,
            sh_col=source.xlsx_sh_col,
        )
    elif source.susa_json_path is not None:
        return read_susa_json(source.susa_json_path)
    else:
        raise ValueError(f"Source '{source.name}' has no data path configured")


# ---------------------------------------------------------------------------
# Validation warnings
# ---------------------------------------------------------------------------


def validate_signs(
    susa_data: dict[str, tuple[float, bool]],
    source_name: str,
) -> list[str]:
    """Warn when accounts have unusual S/H direction."""
    warnings: list[str] = []
    for konto, (saldo, is_soll) in susa_data.items():
        if konto in POSITIVE_IN_MODEL and is_soll:
            warnings.append(
                f"[{source_name}] {konto} is normally Haben but shows Soll "
                f"({saldo:.2f}) — negative value in model"
            )
        elif (
            konto not in POSITIVE_IN_MODEL
            and not is_soll
            and konto.startswith(("3", "4", "6", "7"))
        ):
            warnings.append(
                f"[{source_name}] {konto} is normally Soll but shows Haben "
                f"({saldo:.2f}) — positive value in model (cost reduction?)"
            )
    return warnings


# ---------------------------------------------------------------------------
# PowerShell generator
# ---------------------------------------------------------------------------


def _ps_escape(s: str) -> str:
    """Escape a string for PowerShell single-quoted literal."""
    return s.replace("'", "''")


def generate_ps1(
    config: UpdateConfig,
    account_map: dict[str, int],
    source_data: list[tuple[SourceConfig, dict[str, tuple[float, bool]]]],
) -> tuple[str, int, dict[str, list[tuple[str, float, bool]]]]:
    """Generate PowerShell script content. Returns (script, total_writes, skipped_per_source)."""
    model_path_onedrive = os.path.join(
        config.deal_folder, config.model_subfolder, config.model_filename
    )
    model_path_temp = os.path.join(config.temp_dir, config.model_filename)

    lines: list[str] = []
    total_writes = 0
    skipped: dict[str, list[tuple[str, float, bool]]] = {}

    # Header
    lines.append("# Auto-generated by susa_to_model.py — do not edit manually")
    lines.append(f"# Model: {config.model_filename}")
    lines.append(f"# Sources: {', '.join(s.name for s, _ in source_data)}")
    lines.append("")
    lines.append("$ErrorActionPreference = 'Stop'")
    lines.append("")

    # Kill lingering Excel
    lines.append("# Kill lingering Excel processes")
    lines.append(
        "Get-Process EXCEL -ErrorAction SilentlyContinue | Stop-Process -Force"
    )
    lines.append("Start-Sleep -Seconds 2")
    lines.append("")

    # Copy from OneDrive to temp
    lines.append("# Copy model to local temp (OneDrive causes COM RPC errors)")
    lines.append(f"$srcPath  = '{_ps_escape(model_path_onedrive)}'")
    lines.append(f"$tempPath = '{_ps_escape(model_path_temp)}'")
    lines.append("Copy-Item -Path $srcPath -Destination $tempPath -Force")
    lines.append("Write-Host 'Copied model to temp location'")
    lines.append("")

    # Open Excel COM
    lines.append("# Open via Excel COM")
    lines.append("$xl = New-Object -ComObject Excel.Application")
    lines.append("$xl.Visible = $false")
    lines.append("$xl.DisplayAlerts = $false")
    lines.append("$xl.ScreenUpdating = $false")
    lines.append("$wb = $xl.Workbooks.Open($tempPath)")
    lines.append(f"$ws = $wb.Sheets.Item('{_ps_escape(config.guv_sheet_name)}')")
    lines.append("")

    # Header updates
    if config.header_updates:
        lines.append("# --- Header updates ---")
        for row, col, value in config.header_updates:
            lines.append(
                f"$ws.Cells.Item({row}, {col}).Value2 = '{_ps_escape(str(value))}'"
            )
        lines.append(f"Write-Host 'Wrote {len(config.header_updates)} header cells'")
        lines.append("")

    # Data writes per source
    for source, susa in source_data:
        source_skipped: list[tuple[str, float, bool]] = []
        write_count = 0

        lines.append(f"# --- Source: {source.name} → column {source.target_column} ---")

        # Sort by account number for readability
        for konto in sorted(susa.keys(), key=lambda k: int(k)):
            if konto in config.skip_accounts:
                saldo, is_soll = susa[konto]
                source_skipped.append((konto, saldo, is_soll))
                continue

            if konto not in account_map:
                saldo, is_soll = susa[konto]
                source_skipped.append((konto, saldo, is_soll))
                continue

            row = account_map[konto]
            saldo, is_soll = susa[konto]
            val = model_value(saldo, is_soll)

            # Format value: round to 2 decimals
            val_rounded = round(val, 2)
            lines.append(
                f"$ws.Cells.Item({row}, {source.target_column}).Value2 = {val_rounded}  # {konto}"
            )
            write_count += 1

        lines.append(f"Write-Host 'Wrote {write_count} cells for {source.name}'")
        lines.append("")

        total_writes += write_count
        skipped[source.name] = source_skipped

    # Save and close
    lines.append("# --- Save, close, cleanup ---")
    lines.append("$wb.Save()")
    lines.append("$wb.Close($false)")
    lines.append("$xl.Quit()")
    lines.append(
        "[System.Runtime.InteropServices.Marshal]::ReleaseComObject($ws) | Out-Null"
    )
    lines.append(
        "[System.Runtime.InteropServices.Marshal]::ReleaseComObject($wb) | Out-Null"
    )
    lines.append(
        "[System.Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null"
    )
    lines.append("[GC]::Collect()")
    lines.append("[GC]::WaitForPendingFinalizers()")
    lines.append("Write-Host 'Excel closed and COM released'")
    lines.append("")

    # Copy back to OneDrive
    lines.append("# Copy back to OneDrive")
    lines.append("Start-Sleep -Seconds 2")
    lines.append("Copy-Item -Path $tempPath -Destination $srcPath -Force")
    lines.append("Write-Host 'Copied model back to OneDrive'")
    lines.append("")

    # Cleanup temp
    lines.append("# Cleanup temp file")
    lines.append("Remove-Item -Path $tempPath -Force -ErrorAction SilentlyContinue")
    lines.append("Write-Host 'Done.'")
    lines.append("")

    # Cross-check comments
    if config.crosschecks:
        lines.append("# --- Cross-check values (verify manually in Excel) ---")
        for label, expected in config.crosschecks.items():
            lines.append(f"# {label}: expected {expected:,.2f}")

    script = "\n".join(lines) + "\n"
    return script, total_writes, skipped


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_update(config: UpdateConfig) -> UpdateResult:
    """Run the full pipeline: read model + sources, generate .ps1, print summary."""

    # 1. Read model account map
    model_path = os.path.join(
        config.deal_folder, config.model_subfolder, config.model_filename
    )
    print(f"Reading model: {model_path}")
    print(f"Sheet: {config.guv_sheet_name}")
    account_map = read_model_account_map(model_path, config.guv_sheet_name)
    print(f"  → {len(account_map)} accounts mapped in model")
    print()

    # 2. Resolve all sources
    source_data: list[tuple[SourceConfig, dict[str, tuple[float, bool]]]] = []
    all_warnings: list[str] = []

    for source in config.sources:
        print(f"Reading source: {source.name}")
        susa = resolve_source(source)
        print(f"  → {len(susa)} accounts in SUSA data")
        source_data.append((source, susa))

        # Validate signs
        warnings = validate_signs(susa, source.name)
        all_warnings.extend(warnings)

    print()

    # 3. Generate PowerShell script
    script, total_writes, skipped = generate_ps1(config, account_map, source_data)

    # 4. Determine output path
    ps1_path = config.ps1_output_path
    if not ps1_path:
        ps1_path = os.path.join(config.temp_dir, "update_model.ps1")

    # 5. Write .ps1 file safely (temp → rename)
    ps1_temp = ps1_path + ".tmp"
    with open(ps1_temp, "w", encoding="utf-8") as f:
        f.write(script)
    os.replace(ps1_temp, ps1_path)
    print(f"Wrote PowerShell script: {ps1_path}")
    print(f"Total cell writes: {total_writes}")
    print()

    # 6. Print skipped accounts
    for source_name, skipped_list in skipped.items():
        if skipped_list:
            print(f"Skipped accounts ({source_name}):")
            for konto, saldo, is_soll in sorted(skipped_list, key=lambda x: int(x[0])):
                direction = "S" if is_soll else "H"
                val = model_value(saldo, is_soll)
                reason = (
                    "skip-list" if konto in config.skip_accounts else "not-in-model"
                )
                print(
                    f"  {konto}: {saldo:>12,.2f} {direction} → {val:>12,.2f}  ({reason})"
                )
            print()

    # 7. Print spot-check values
    print("Spot-check values:")
    for source, susa in source_data:
        print(f"  [{source.name}] col {source.target_column}:")
        for konto in SPOT_CHECK_ACCOUNTS:
            if konto in susa:
                saldo, is_soll = susa[konto]
                val = model_value(saldo, is_soll)
                direction = "S" if is_soll else "H"
                row = account_map.get(konto, "???")
                print(
                    f"    {konto} → row {row}: {val:>12,.2f}  (raw: {saldo:,.2f} {direction})"
                )
            else:
                print(f"    {konto} → not in SUSA")
    print()

    # 8. Print warnings
    if all_warnings:
        print("WARNINGS:")
        for w in all_warnings:
            print(f"  ⚠ {w}")
        print()

    return UpdateResult(
        ps1_path=ps1_path,
        total_writes=total_writes,
        skipped=skipped,
        warnings=all_warnings,
    )


# ---------------------------------------------------------------------------
# Config deserialization from JSON
# ---------------------------------------------------------------------------


def load_config_from_json(path: str) -> UpdateConfig:
    """Load UpdateConfig from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    sources = []
    for s in raw.get("sources", []):
        sources.append(
            SourceConfig(
                name=s["name"],
                target_column=s["target_column"],
                susa_xlsx_path=s.get("susa_xlsx_path"),
                susa_json_path=s.get("susa_json_path"),
                susa_data=s.get("susa_data"),
                xlsx_account_col=s.get("xlsx_account_col", 0),
                xlsx_saldo_col=s.get("xlsx_saldo_col", 5),
                xlsx_sh_col=s.get("xlsx_sh_col", 6),
            )
        )

    header_updates = []
    for h in raw.get("header_updates", []):
        header_updates.append((int(h[0]), int(h[1]), str(h[2])))

    skip_accounts = set(DEFAULT_SKIP_ACCOUNTS)
    extra_skips = raw.get("skip_accounts", [])
    if extra_skips:
        skip_accounts.update(str(a) for a in extra_skips)

    return UpdateConfig(
        deal_folder=raw["deal_folder"],
        model_subfolder=raw.get("model_subfolder", "2_Model"),
        model_filename=raw["model_filename"],
        guv_sheet_name=raw.get("guv_sheet_name", "GuV-Konten"),
        sources=sources,
        header_updates=header_updates,
        crosschecks=raw.get("crosschecks", {}),
        skip_accounts=skip_accounts,
        ps1_output_path=raw.get("ps1_output_path", ""),
        temp_dir=raw.get("temp_dir", r"C:\Users\X1\Documents\CLAUDE_COWORK"),
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python susa_to_model.py <config.json>")
        print()
        print("Config JSON structure:")
        print(
            textwrap.dedent("""\
            {
              "deal_folder": "C:\\\\...\\\\250724_Golmed (Lion)",
              "model_subfolder": "2_Model",
              "model_filename": "260508_Golmed_v9.xlsx",
              "guv_sheet_name": "GuV-Konten",
              "sources": [
                {
                  "name": "fy2025",
                  "target_column": 8,
                  "susa_xlsx_path": "C:\\\\...\\\\SUSA_2025.xlsx"
                },
                {
                  "name": "ytd2026",
                  "target_column": 9,
                  "susa_json_path": "C:\\\\...\\\\susa_2026_apr.json"
                }
              ],
              "header_updates": [[3, 11, "Delta 25"], [3, 13, "04-25"]],
              "crosschecks": {"Umsatz_2025": 7821903.47},
              "ps1_output_path": "C:\\\\...\\\\update_model.ps1",
              "skip_accounts": ["2870"]
            }
        """)
        )
        sys.exit(1)

    config_path = sys.argv[1]
    if not os.path.isfile(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    cfg = load_config_from_json(config_path)
    result = generate_update(cfg)

    if result.warnings:
        sys.exit(0)  # warnings are informational, not errors
