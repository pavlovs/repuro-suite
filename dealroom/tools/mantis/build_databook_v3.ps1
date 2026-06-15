# MANTIS CDD Databook Builder v3 - native Excel ops only (sheet copies, formulas, sort)
# v3: dummy-deck references removed, GuV cross-check added, open questions moved to separate RFI doc
# Output: CDD_Databook_Mantis_v3.xlsx

$ErrorActionPreference = "Stop"
# en-US thread culture so COM marshals consistently (German LCID mangles formats and range strings)
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
$tempDir = "C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd"
$outputPath = "$tempDir\CDD_Databook_Mantis_v3.xlsx"
$inv = [System.Globalization.CultureInfo]::InvariantCulture

Get-Process excel -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

# ---- Repuro CI constants (BGR decimals) ----
$tealBGR    = 11702536   # 0891B2 header fill
$accent1BGR = 15651618   # 22D3EE
$bandBGR    = 16181389   # 8DE8F6 section band
$accent3BGR = 4726241    # E11D48 signal red
$accent4BGR = 570346     # EAB308
$accent5BGR = 16209320   # A855F7
$white      = 16777215
$lightGray  = 15790320
$palette    = @($tealBGR, $accent1BGR, $bandBGR, $accent4BGR, $accent5BGR, $accent3BGR, 10921638, 5197615)

# German-local format codes (set via NumberFormatLocal - German Excel mangles the NumberFormat property)
$fmtK   = "#.##0,0;\ \(#.##0,0\);\ \-"
$fmtInt = "#.##0"
$fmtPct = "0,0%"
$fmtEur = "#.##0"
$fontName = "Aptos Narrow"

function Set-CellBase($cell) {
    $cell.Font.Name = $fontName
    $cell.Font.Size = 10
    $cell.VerticalAlignment = -4108
}

# Strings -> Value2. Numbers -> .Formula "=<num>" (always a string assignment, immune to the
# PS 5.1 DLR Value2 type-poisoning bug; Excel stores the numeric result).
function New-Cell($ws, $r, $c, $v, $fmt, $center) {
    $cell = $ws.Cells.Item($r, $c)
    if ($v -is [string]) { $cell.Value2 = $v }
    else { $cell.Formula = "=" + [string]::Format($inv, "{0:R}", [double]$v) }
    Set-CellBase $cell
    if ($fmt) { $cell.NumberFormatLocal = $fmt }
    if ($center) { $cell.HorizontalAlignment = -4108 }
}

function New-Formula($ws, $r, $c, $f, $fmt) {
    $cell = $ws.Cells.Item($r, $c)
    $cell.Formula = $f
    Set-CellBase $cell
    if ($fmt) { $cell.NumberFormatLocal = $fmt }
    $cell.HorizontalAlignment = -4108
}

function New-HeaderRow($ws, $row, $startCol, $headers) {
    for ($i = 0; $i -lt $headers.Count; $i++) {
        $cell = $ws.Cells.Item($row, $startCol + $i)
        $cell.NumberFormatLocal = "@"
        $cell.Value2 = [string]$headers[$i]
        Set-CellBase $cell
        $cell.Font.Bold = $true
        $cell.Font.Color = $white
        $cell.Interior.Color = $tealBGR
        $cell.HorizontalAlignment = -4108
    }
}

function New-SectionBand($ws, $row, $startCol, $endCol, $text) {
    $rng = $ws.Range($ws.Cells.Item($row, $startCol), $ws.Cells.Item($row, $endCol))
    $rng.Interior.Color = $bandBGR
    $cell = $ws.Cells.Item($row, $startCol)
    $cell.Value2 = [string]$text
    Set-CellBase $cell
    $cell.Font.Bold = $true
    $cell.Font.Size = 11
}

function New-Title($ws, $text) {
    $cell = $ws.Cells.Item(2, 2)
    $cell.Value2 = [string]$text
    $cell.Font.Name = $fontName
    $cell.Font.Size = 13
    $cell.Font.Bold = $true
}

function New-CommentLine($ws, $r, $text) {
    $cell = $ws.Cells.Item($r, 2)
    $cell.Value2 = [string]$text
    Set-CellBase $cell
}

function Add-TableBorders($ws, $r1, $c1, $r2, $c2) {
    $rng = $ws.Range($ws.Cells.Item($r1, $c1), $ws.Cells.Item($r2, $c2))
    $rng.Borders.LineStyle = 1
    $rng.Borders.Weight = 2
}

function Set-TotalRow($ws, $row, $c1, $c2) {
    $rng = $ws.Range($ws.Cells.Item($row, $c1), $ws.Cells.Item($row, $c2))
    $rng.Font.Bold = $true
    $rng.Borders.Item(8).LineStyle = 1
    $rng.Borders.Item(8).Weight = 2
    $rng.Borders.Item(9).LineStyle = 1
    $rng.Borders.Item(9).Weight = 2
}

try {
    # ================= CREATE TARGET WORKBOOK =================
    $wb = $excel.Workbooks.Add()
    while ($wb.Sheets.Count -gt 1) { $wb.Sheets.Item($wb.Sheets.Count).Delete() }
    $wsR = $wb.Sheets.Item(1)
    $wsR.Name = "Revenue Analysis"

    # ================= COPY SOURCE SHEETS (native, instant) =================
    Write-Host "Copying source sheets..."
    $wb1 = $excel.Workbooks.Open("$tempDir\file_1_1.xlsx")
    $pivotData = $wb1.Sheets.Item("Pivot").UsedRange.Value2
    $pivotRows = $wb1.Sheets.Item("Pivot").UsedRange.Rows.Count
    $invData = $wb1.Sheets.Item("Rechnungen").UsedRange.Value2
    $invRows = $wb1.Sheets.Item("Rechnungen").UsedRange.Rows.Count
    $wb1.Sheets.Item("Rechnungen").Copy([System.Type]::Missing, $wb.Sheets.Item($wb.Sheets.Count))
    $wsDI = $wb.Sheets.Item($wb.Sheets.Count)
    $wsDI.Name = "Data Invoices"
    $wsDI.UsedRange.Copy() | Out-Null
    $wsDI.UsedRange.PasteSpecial(-4163) | Out-Null   # values only - no external links back to seller file
    $wb1.Close($false)

    $wb2 = $excel.Workbooks.Open("$tempDir\file_1_3.xlsx")
    $wb2.Sheets.Item("Sheet1").Copy([System.Type]::Missing, $wb.Sheets.Item($wb.Sheets.Count))
    $wsDC = $wb.Sheets.Item($wb.Sheets.Count)
    $wsDC.Name = "Data Customers"
    $wsDC.UsedRange.Copy() | Out-Null
    $wsDC.UsedRange.PasteSpecial(-4163) | Out-Null
    $wb2.Close($false)
    try { foreach ($l in @($wb.LinkSources(1))) { if ($l) { $wb.BreakLink($l, 1) } } } catch {}
    Write-Host "  copied: Rechnungen ($invRows rows), Sheet1"

    # ---- Pivot totals for the check row ----
    $pivotTotals = @{ Y2023 = 0; Y2024 = 0; Y2025 = 0 }
    for ($r = 2; $r -le $pivotRows; $r++) {
        $label = $pivotData[$r, 1]
        if ($label -and $label.ToString().Trim() -eq "Gesamtergebnis") {
            try { if ($pivotData[$r, 2] -is [double]) { $pivotTotals.Y2023 = $pivotData[$r, 2] } } catch {}
            try { if ($pivotData[$r, 3] -is [double]) { $pivotTotals.Y2024 = $pivotData[$r, 3] } } catch {}
            try { if ($pivotData[$r, 4] -is [double]) { $pivotTotals.Y2025 = $pivotData[$r, 4] } } catch {}
        }
    }

    # ---- Segment list (unique RepArt, sorted by 2025 revenue desc) ----
    $segSums = @{}
    for ($r = 2; $r -le $invRows; $r++) {
        $repArt = if ($invData[$r, 6]) { $invData[$r, 6].ToString().Trim() } else { "" }
        if ($repArt -eq "") { continue }
        if (-not $segSums.ContainsKey($repArt)) { $segSums[$repArt] = 0.0 }
        $datum = $invData[$r, 8]
        if ($datum -is [double]) {
            $dt = [DateTime]::FromOADate($datum)
            if ($dt.Year -eq 2025) {
                $netto = if ($invData[$r, 3] -is [double]) { $invData[$r, 3] } else { 0 }
                $segSums[$repArt] += $netto
            }
        }
    }
    $segNames = @($segSums.Keys | Sort-Object { $segSums[$_] } -Descending)
    Write-Host "  segments: $($segNames.Count)"

    # ================= DATA INVOICES: gutter + Year/Quarter formulas =================
    Write-Host "Enhancing Data Invoices..."
    $wsDI.Columns.Item(1).Insert() | Out-Null
    $wsDI.Columns.Item(1).ColumnWidth = 3
    # Layout now: B=Rechnungsnummer C=Status D=Netto E=Modell F=SN G=RepArt H=Art I=Datum J=Rohertrag
    $diLastData = $invRows
    New-HeaderRow $wsDI 1 11 @("Year", "Quarter")
    $wsDI.Range("K2:K$diLastData").Formula = "=IFERROR(YEAR(I2),"""")"
    $wsDI.Range("L2:L$diLastData").Formula = "=IFERROR(ROUNDUP(MONTH(I2)/3,0),"""")"
    $rngKL = $wsDI.Range("K2:L$diLastData")
    $rngKL.Font.Name = $fontName; $rngKL.Font.Size = 10
    $DI = "'Data Invoices'!"
    # DI refs: D=Netto G=RepArt J=Rohertrag K=Year L=Quarter

    # ================= DATA CUSTOMERS: gutter, cleanup, cohort, sort =================
    Write-Host "Enhancing Data Customers..."
    $wsDC.Columns.Item(1).Insert() | Out-Null
    $wsDC.Columns.Item(1).ColumnWidth = 3
    # Layout now: B=Kunden(type) C=2022 D=2023 E=2024 F=2025 G=2026 H=Gesamt I=Ranking
    # Source structure: R1 = "Summen" totals row, R2 = header ("Kunden"), R3+ = data, footer = "Gesamtzahl pro Jahr"
    $hdrRowDC = 0
    for ($r = 1; $r -le 10; $r++) {
        if ($wsDC.Cells.Item($r, 2).Text -eq "Kunden") { $hdrRowDC = $r; break }
    }
    if ($hdrRowDC -eq 0) { throw "Customer header row ('Kunden') not found" }
    $dataFirst = $hdrRowDC + 1
    $dataLast = $dataFirst - 1
    for ($r = $dataFirst; $r -le 1200; $r++) {
        $v = $wsDC.Cells.Item($r, 2).Text
        if ($v -eq "" -or $v -like "Summen*" -or $v -like "Gesamtzahl*") { break }
        $dataLast = $r
    }
    $nCust = $dataLast - $dataFirst + 1
    if ($nCust -lt 100) { throw "Customer block too small ($nCust rows) - layout changed?" }
    Write-Host "  customer data rows: $dataFirst..$dataLast ($nCust customers)"
    $wsDC.Rows("$($dataLast + 1):1300").Delete() | Out-Null
    if ($hdrRowDC -gt 1) { $wsDC.Rows("1:$($hdrRowDC - 1)").Delete() | Out-Null }
    # now: header row 1, data rows 2..(1+nCust). Drop junk columns right of I (Ranking)
    $wsDC.Range("J:R").Delete() | Out-Null
    $dcLast = 1 + $nCust
    New-HeaderRow $wsDC 1 10 @("Cohort", "Cust #")
    $wsDC.Range("J2:J$dcLast").Formula = "=IF(C2>0,2022,IF(D2>0,2023,IF(E2>0,2024,IF(F2>0,2025,IF(G2>0,2026,0)))))"
    $sortRng = $wsDC.Range("B2:J$dcLast")
    $sortRng.Sort($wsDC.Range("F2"), 2, [System.Type]::Missing, [System.Type]::Missing, 1, [System.Type]::Missing, 1, 2) | Out-Null
    $wsDC.Range("K2:K$dcLast").Formula = "=ROW()-1"
    $rngJK = $wsDC.Range("J2:K$dcLast")
    $rngJK.Font.Name = $fontName; $rngJK.Font.Size = 10
    $DC = "'Data Customers'!"
    $yearCol = @{ 2022 = "C"; 2023 = "D"; 2024 = "E"; 2025 = "F"; 2026 = "G" }
    $dcFirst = 2

    $g25  = "$DC`$F`$$dcFirst`:`$F`$$dcLast"
    $jCol = "$DC`$J`$$dcFirst`:`$J`$$dcLast"
    $iCol = "$DC`$H`$$dcFirst`:`$H`$$dcLast"
    $tCol = "$DC`$B`$$dcFirst`:`$B`$$dcLast"

    # ---- Customer type list (from sheet, sorted by Gesamt desc) ----
    $typeSums = @{}
    for ($r = 2; $r -le $dcLast; $r++) {
        $t = $wsDC.Cells.Item($r, 2).Text
        if ($t -eq "") { continue }
        if (-not $typeSums.ContainsKey($t)) { $typeSums[$t] = 0.0 }
        $g = $wsDC.Cells.Item($r, 8).Value2
        if ($g -is [double]) { $typeSums[$t] += $g }
    }
    $typeNames = @($typeSums.Keys | Sort-Object { $typeSums[$_] } -Descending)
    Write-Host "  types: $($typeNames.Count)"

    # ================= TAB: Revenue Analysis =================
    Write-Host "Building Revenue Analysis..."
    $wsR.Columns.Item(1).ColumnWidth = 3
    New-Title $wsR "Revenue Analysis - full company revenue scope (GuV cross-checked: 2022-2024 within 2%; 2025 +3.9% pre-shift)"

    $r = 4
    New-SectionBand $wsR $r 2 9 "Key findings"
    $r++
    New-CommentLine $wsR $r "1. Growth stalled: GuV revenue +17% (2023), +12% (2024), -1% (2025 reported) / +3% pro-forma after the 120k revenue shift into 2026 (seller's own EBIT bridge)."; $r++
    New-CommentLine $wsR $r "2. Mobile field service (Mobiler Kundendienst) declined c. -24% in 2025 - structural question for the management session."; $r++
    New-CommentLine $wsR $r "3. Replacement sales (Reparaturersatz) swing heavily (+109% / -30%) - project-driven, not recurring."; $r++
    New-CommentLine $wsR $r "4. Calendar fiscal year confirmed by GuV (01.01.-31.12.). Invoice calc ties to the GuV within <2% for 2022-2024; 2025 is +3.9% vs the vorlaeufige GuV and reconciles only via the seller's unverified 120k shift - see cross-check below."; $r++
    New-CommentLine $wsR $r "5. EBIT fell from 716.8k (2024, 23.2%) to 320.3k (2025 reported, 10.1%); seller pro-forma 550.1k - bridge items unverified. See P&L check below."; $r++

    $r += 2
    New-SectionBand $wsR $r 2 9 "Revenue by service segment (EUR k, calendar year from invoice dates)"
    $r += 2
    $segHdrRow = $r
    New-HeaderRow $wsR $r 2 @("Segment", "2023", "2024", "2025", "2026 YTD", "YoY 23-24", "YoY 24-25")
    $r++
    $segFirstRow = $r
    foreach ($s in $segNames) {
        New-Cell $wsR $r 2 ([string]$s) $null $false
        foreach ($y in @(2023, 2024, 2025, 2026)) {
            $col = 3 + ($y - 2023)
            New-Formula $wsR $r $col "=SUMIFS($DI`$D:`$D,$DI`$G:`$G,`$B$r,$DI`$K:`$K,$y)/1000" $fmtK
        }
        New-Formula $wsR $r 7 "=IF(C$r=0,"""",(D$r-C$r)/C$r)" $fmtPct
        New-Formula $wsR $r 8 "=IF(D$r=0,"""",(E$r-D$r)/D$r)" $fmtPct
        $r++
    }
    $segLastRow = $r - 1
    $segTotalRow = $r
    New-Cell $wsR $r 2 "Total" $null $false
    foreach ($col in @(3, 4, 5, 6)) {
        $colL = [char](64 + $col)
        New-Formula $wsR $r $col "=SUM($colL$segFirstRow`:$colL$segLastRow)" $fmtK
    }
    New-Formula $wsR $r 7 "=IF(C$r=0,"""",(D$r-C$r)/C$r)" $fmtPct
    New-Formula $wsR $r 8 "=IF(D$r=0,"""",(E$r-D$r)/D$r)" $fmtPct
    Set-TotalRow $wsR $r 2 8
    Add-TableBorders $wsR $segHdrRow 2 $segTotalRow 8
    $r++
    New-Cell $wsR $r 2 "Check: seller pivot total (file 1.1)" $null $false
    $wsR.Cells.Item($r, 2).Font.Italic = $true
    New-Cell $wsR $r 3 ($pivotTotals.Y2023 / 1000) $fmtK $true
    New-Cell $wsR $r 4 ($pivotTotals.Y2024 / 1000) $fmtK $true
    New-Cell $wsR $r 5 ($pivotTotals.Y2025 / 1000) $fmtK $true
    $checkRow = $r
    $r++
    New-Cell $wsR $r 2 "Delta (calc - pivot)" $null $false
    $wsR.Cells.Item($r, 2).Font.Italic = $true
    foreach ($col in @(3, 4, 5)) {
        $colL = [char](64 + $col)
        New-Formula $wsR $r $col "=$colL$segTotalRow-$colL$checkRow" $fmtK
    }

    $r += 3
    New-SectionBand $wsR $r 2 9 "Gross margin by segment by year (EUR k; GM% = Rohertrag / net revenue - materials-only margin)"
    $r += 2
    $gmHdrRow = $r
    New-HeaderRow $wsR $r 2 @("Segment", "2023 Rev", "2023 GM%", "2024 Rev", "2024 GM%", "2025 Rev", "2025 GM%")
    $r++
    foreach ($s in $segNames) {
        New-Cell $wsR $r 2 ([string]$s) $null $false
        foreach ($y in @(2023, 2024, 2025)) {
            $colRev = 3 + ($y - 2023) * 2
            $colGM = $colRev + 1
            New-Formula $wsR $r $colRev "=SUMIFS($DI`$D:`$D,$DI`$G:`$G,`$B$r,$DI`$K:`$K,$y)/1000" $fmtK
            New-Formula $wsR $r $colGM "=IFERROR(SUMIFS($DI`$J:`$J,$DI`$G:`$G,`$B$r,$DI`$K:`$K,$y)/SUMIFS($DI`$D:`$D,$DI`$G:`$G,`$B$r,$DI`$K:`$K,$y),"""")" $fmtPct
        }
        $r++
    }
    Add-TableBorders $wsR $gmHdrRow 2 ($r - 1) 8

    $r += 2
    New-SectionBand $wsR $r 2 9 "Quarterly revenue (EUR k, from invoice dates)"
    $r += 2
    $qHdrRow = $r
    New-HeaderRow $wsR $r 2 @("Quarter", "Year", "Q", "Revenue", "Gross profit", "GM%")
    $r++
    $qFirstRow = $r
    foreach ($y in @(2023, 2024, 2025, 2026)) {
        foreach ($q in @(1, 2, 3, 4)) {
            if ($y -eq 2026 -and $q -gt 2) { continue }
            New-Cell $wsR $r 2 "$y-Q$q" $null $false
            New-Cell $wsR $r 3 $y $fmtInt $true
            New-Cell $wsR $r 4 $q $fmtInt $true
            New-Formula $wsR $r 5 "=SUMIFS($DI`$D:`$D,$DI`$K:`$K,C$r,$DI`$L:`$L,D$r)/1000" $fmtK
            New-Formula $wsR $r 6 "=SUMIFS($DI`$J:`$J,$DI`$K:`$K,C$r,$DI`$L:`$L,D$r)/1000" $fmtK
            New-Formula $wsR $r 7 "=IFERROR(F$r/E$r,"""")" $fmtPct
            $r++
        }
    }
    $qLastRow = $r - 1
    Add-TableBorders $wsR $qHdrRow 2 $qLastRow 7

    $r += 2
    New-SectionBand $wsR $r 2 9 "Revenue reconciliation bridge - 2025 (EUR k)"
    $r += 2
    $bridgeHdr = $r
    New-HeaderRow $wsR $r 2 @("Source", "Revenue 2025", "Scope", "Notes")
    $r++
    New-Cell $wsR $r 2 "File 1.1 (invoice data, calc)" $null $false
    New-Formula $wsR $r 3 "=E$segTotalRow" $fmtK
    New-Cell $wsR $r 4 "Repair/service invoices" $null $false
    New-Cell $wsR $r 5 "Live calc from Data Invoices tab, calendar year 2025" $null $false
    $r++
    New-Cell $wsR $r 2 "File 1.3 (customer revenue)" $null $false
    New-Formula $wsR $r 3 "=SUM($g25)/1000" $fmtK
    New-Cell $wsR $r 4 "Same scope as 1.1" $null $false
    New-Cell $wsR $r 5 "Reconciles with 1.1 within c. 12-23k p.a. (<2%) - normal for commercial data" $null $false
    $bridge13 = $r
    $r++
    New-Cell $wsR $r 2 "GuV 2025 Umsatzerloese (vorlaeufig)" $null $false
    New-Cell $wsR $r 3 3057.969 $fmtK $true
    New-Cell $wsR $r 4 "Reported P&L" $null $false
    New-Cell $wsR $r 5 "Source: 4.1 / 2025 GuV.xlsx (bis Periode 16, erstellt 21.05.2026)" $null $false
    $bridgeGuv = $r
    $r++
    New-Cell $wsR $r 2 "+ Revenue shifted into 2026 (seller bridge)" $null $false
    New-Cell $wsR $r 3 120.0 $fmtK $true
    New-Cell $wsR $r 4 "Seller adjustment" $null $false
    New-Cell $wsR $r 5 "Per seller EBIT-Nebenrechnung - UNVERIFIED, see RFI doc Q2" $null $false
    $bridgeShift = $r
    $r++
    New-Cell $wsR $r 2 "GuV 2025 pro-forma (reported + shift)" $null $false
    New-Formula $wsR $r 3 "=C$bridgeGuv+C$bridgeShift" $fmtK
    New-Cell $wsR $r 4 "" $null $false
    New-Cell $wsR $r 5 "Seller shows 3,178.0 - matches" $null $false
    $bridgePf = $r
    $r++
    New-Cell $wsR $r 2 "Residual (pro-forma GuV - file 1.3)" $null $false
    $wsR.Cells.Item($r, 2).Font.Bold = $true
    New-Formula $wsR $r 3 "=C$bridgePf-C$bridge13" $fmtK
    New-Cell $wsR $r 4 "Immaterial" $null $false
    New-Cell $wsR $r 5 "Commercial data = company revenue; 2025 tie-out depends on the unverified shift" $null $false
    Add-TableBorders $wsR $bridgeHdr 2 $r 5

    # GuV cross-check + P&L
    $r += 3
    New-SectionBand $wsR $r 2 9 "GuV cross-check and P&L (EUR k; source: 4.1 Jahresabschluesse + seller EBIT-Nebenrechnung)"
    $r += 2
    $guvHdr = $r
    New-HeaderRow $wsR $r 2 @("Item", "2022", "2023", "2024", "2025", "Note")
    $r++
    New-Cell $wsR $r 2 "GuV Umsatzerloese (reported)" $null $false
    New-Cell $wsR $r 3 2349.657 $fmtK $true
    New-Cell $wsR $r 4 2760.011 $fmtK $true
    New-Cell $wsR $r 5 3093.248 $fmtK $true
    New-Cell $wsR $r 6 3057.969 $fmtK $true
    New-Cell $wsR $r 7 "2025 vorlaeufig (bis Periode 16)" $null $false
    $guvRevRow = $r
    $r++
    New-Cell $wsR $r 2 "File 1.3 customer revenue" $null $false
    foreach ($pair in @(@(3, "C"), @(4, "D"), @(5, "E"), @(6, "F"))) {
        $col = $pair[0]; $yc = $pair[1]
        New-Formula $wsR $r $col "=SUM($DC`$$yc`$$dcFirst`:`$$yc`$$dcLast)/1000" $fmtK
    }
    New-Cell $wsR $r 7 "Live formula off Data Customers" $null $false
    $cmRevRow = $r
    $r++
    New-Cell $wsR $r 2 "Delta (commercial - GuV)" $null $false
    $wsR.Cells.Item($r, 2).Font.Italic = $true
    foreach ($col in @(3, 4, 5, 6)) {
        $colL = [char](64 + $col)
        New-Formula $wsR $r $col "=$colL$cmRevRow-$colL$guvRevRow" $fmtK
    }
    New-Cell $wsR $r 7 "2025 delta = the 120k shift (timing)" $null $false
    $r++
    New-Cell $wsR $r 2 "Delta %" $null $false
    $wsR.Cells.Item($r, 2).Font.Italic = $true
    foreach ($col in @(3, 4, 5, 6)) {
        $colL = [char](64 + $col)
        New-Formula $wsR $r $col "=($colL$cmRevRow-$colL$guvRevRow)/$colL$guvRevRow" $fmtPct
    }
    $r++
    New-Cell $wsR $r 2 "EBIT (reported)" $null $false
    New-Cell $wsR $r 5 716.8 $fmtK $true
    New-Cell $wsR $r 6 320.3 $fmtK $true
    New-Cell $wsR $r 7 "Margin 23.2% -> 10.1%" $null $false
    $r++
    New-Cell $wsR $r 2 "EBIT pro-forma (seller)" $null $false
    New-Cell $wsR $r 5 794.6 $fmtK $true
    New-Cell $wsR $r 6 550.1 $fmtK $true
    New-Cell $wsR $r 7 "Incl. GF salary adj. (384k -> 140k + 18% NK); 2026P/2027P = 778.1 - all UNVERIFIED" $null $false
    $r++
    New-Cell $wsR $r 2 "GuV Rohertrag 2025" $null $false
    New-Cell $wsR $r 6 1764.269 $fmtK $true
    New-Cell $wsR $r 7 "57.7% of reported revenue - materials-only margin, consistent with invoice Rohertrag field" $null $false
    Add-TableBorders $wsR $guvHdr 2 $r 7

    $wsR.Columns.Item(2).ColumnWidth = 34
    for ($c = 3; $c -le 8; $c++) { $wsR.Columns.Item($c).ColumnWidth = 11 }
    $wsR.Columns.Item(7).ColumnWidth = 40

    # ================= TAB: Customer Analysis =================
    Write-Host "Building Customer Analysis..."
    $wsC = $wb.Sheets.Add([System.Type]::Missing, $wsR)
    $wsC.Name = "Customer Analysis"
    $wsC.Columns.Item(1).ColumnWidth = 3
    New-Title $wsC "Customer Analysis - full company revenue scope (GuV cross-checked)"

    $r = 4
    New-SectionBand $wsC $r 2 10 "Key findings"
    $r++
    New-CommentLine $wsC $r "1. Concentrated base: Top 20 customers carry c. 71% of cumulative revenue; Top 3 c. 27%. Typical for regional service business, but single-account risk is real."; $r++
    New-CommentLine $wsC $r "2. c. 94% of 2025 revenue comes from customers already seen before 2025 - sticky base, few new accounts (11 first-revenue customers in 2025)."; $r++
    New-CommentLine $wsC $r "3. Dealer channel (Haendler) is volatile (573k -> 364k -> 929k in 2023-2025, after 959k in 2022) - lumpy project business, not recurring."; $r++
    New-CommentLine $wsC $r "4. Hospital segment (Krankenhaus) spiked in 2024 (983k -> 1,721k) and fell back in 2025 (1,377k) - one-off effect to be explained by management."; $r++

    $r += 2
    New-SectionBand $wsC $r 2 10 "Customer concentration - 2025 (EUR k)"
    $r += 2
    $concHdrRow = $r
    New-HeaderRow $wsC $r 2 @("Metric", "# Customers", "Revenue 2025", "% of total")
    $r++
    $concFirstRow = $r
    foreach ($n in @(3, 5, 10, 20)) {
        New-Cell $wsC $r 2 "Top $n" $null $false
        New-Cell $wsC $r 3 $n $fmtInt $true
        New-Formula $wsC $r 4 "=SUMPRODUCT(LARGE($g25,ROW(INDIRECT(""1:$n""))))/1000" $fmtK
        New-Formula $wsC $r 5 "=D$r/D`$$($concFirstRow + 4)" $fmtPct
        $r++
    }
    New-Cell $wsC $r 2 "All active 2025" $null $false
    New-Formula $wsC $r 3 "=COUNTIF($g25,"">0"")" $fmtInt
    New-Formula $wsC $r 4 "=SUM($g25)/1000" $fmtK
    New-Formula $wsC $r 5 "=D$r/D$r" $fmtPct
    Set-TotalRow $wsC $r 2 5
    $concLastRow = $r
    Add-TableBorders $wsC $concHdrRow 2 $concLastRow 5

    $r += 3
    New-SectionBand $wsC $r 2 10 "Revenue by customer type (EUR k)"
    $r += 2
    $typeHdrRow = $r
    New-HeaderRow $wsC $r 2 @("Customer type", "# Cust", "2022", "2023", "2024", "2025", "2026 YTD", "Total", "Share")
    $r++
    $typeFirstRow = $r
    foreach ($t in $typeNames) {
        New-Cell $wsC $r 2 ([string]$t) $null $false
        New-Formula $wsC $r 3 "=COUNTIF($tCol,`$B$r)" $fmtInt
        foreach ($y in @(2022, 2023, 2024, 2025, 2026)) {
            $col = 4 + ($y - 2022)
            $yc = $yearCol[$y]
            New-Formula $wsC $r $col "=SUMIFS($DC`$$yc`$$dcFirst`:`$$yc`$$dcLast,$tCol,`$B$r)/1000" $fmtK
        }
        New-Formula $wsC $r 9 "=SUM(D$r`:H$r)" $fmtK
        $r++
    }
    $typeLastRow = $r - 1
    $typeTotalRow = $r
    New-Cell $wsC $r 2 "Total" $null $false
    New-Formula $wsC $r 3 "=SUM(C$typeFirstRow`:C$typeLastRow)" $fmtInt
    foreach ($col in @(4, 5, 6, 7, 8, 9)) {
        $colL = [char](64 + $col)
        New-Formula $wsC $r $col "=SUM($colL$typeFirstRow`:$colL$typeLastRow)" $fmtK
    }
    Set-TotalRow $wsC $r 2 10
    for ($rr = $typeFirstRow; $rr -le $typeLastRow; $rr++) {
        New-Formula $wsC $rr 10 "=I$rr/I`$$typeTotalRow" $fmtPct
    }
    New-Formula $wsC $typeTotalRow 10 "=SUM(J$typeFirstRow`:J$typeLastRow)" $fmtPct
    Add-TableBorders $wsC $typeHdrRow 2 $typeTotalRow 10

    $r += 3
    New-SectionBand $wsC $r 2 10 "Customers by revenue bucket (cumulative 2022-2026, EUR)"
    $r += 2
    $bktHdrRow = $r
    New-HeaderRow $wsC $r 2 @("Bucket", "From (EUR)", "To (EUR)", "# Customers", "Revenue (EUR k)", "% of total")
    $r++
    $buckets = @(
        @{ L = "> 100k"; Min = 100000; Max = 9999999999 },
        @{ L = "50-100k"; Min = 50000; Max = 100000 },
        @{ L = "20-50k"; Min = 20000; Max = 50000 },
        @{ L = "10-20k"; Min = 10000; Max = 20000 },
        @{ L = "1-10k"; Min = 1000; Max = 10000 },
        @{ L = "< 1k"; Min = 0; Max = 1000 }
    )
    foreach ($b in $buckets) {
        New-Cell $wsC $r 2 ([string]$b.L) $null $false
        New-Cell $wsC $r 3 $b.Min $fmtEur $true
        New-Cell $wsC $r 4 $b.Max $fmtEur $true
        New-Formula $wsC $r 5 "=COUNTIFS($iCol,"">=""&C$r,$iCol,""<""&D$r)" $fmtInt
        New-Formula $wsC $r 6 "=SUMIFS($iCol,$iCol,"">=""&C$r,$iCol,""<""&D$r)/1000" $fmtK
        New-Formula $wsC $r 7 "=F$r/(SUM($iCol)/1000)" $fmtPct
        $r++
    }
    Add-TableBorders $wsC $bktHdrRow 2 ($r - 1) 7

    $r += 2
    New-SectionBand $wsC $r 2 10 "New vs existing customers - 2025 (EUR k)"
    $r += 2
    $nveHdrRow = $r
    New-HeaderRow $wsC $r 2 @("Category", "# Customers", "Revenue 2025", "% of total")
    $r++
    New-Cell $wsC $r 2 "Existing (cohort before 2025)" $null $false
    New-Formula $wsC $r 3 "=COUNTIFS($jCol,""<2025"",$g25,"">0"")" $fmtInt
    New-Formula $wsC $r 4 "=SUMIFS($g25,$jCol,""<2025"")/1000" $fmtK
    New-Formula $wsC $r 5 "=D$r/(SUM($g25)/1000)" $fmtPct
    $r++
    New-Cell $wsC $r 2 "New (2025 cohort)" $null $false
    New-Formula $wsC $r 3 "=COUNTIFS($jCol,2025,$g25,"">0"")" $fmtInt
    New-Formula $wsC $r 4 "=SUMIFS($g25,$jCol,2025)/1000" $fmtK
    New-Formula $wsC $r 5 "=D$r/(SUM($g25)/1000)" $fmtPct
    Add-TableBorders $wsC $nveHdrRow 2 $r 5

    $r += 3
    New-SectionBand $wsC $r 2 10 "Top 20 customers by 2025 revenue (EUR k) - live references to Data Customers"
    $r += 2
    $t20HdrRow = $r
    New-HeaderRow $wsC $r 2 @("#", "Type", "2022", "2023", "2024", "2025", "2026 YTD", "Total", "Cohort")
    $r++
    for ($i = 0; $i -lt 20; $i++) {
        $srcRow = $dcFirst + $i
        New-Formula $wsC $r 2 "=${DC}K${srcRow}" $fmtInt
        $cellT = $wsC.Cells.Item($r, 3)
        $cellT.Formula = "=${DC}B${srcRow}"
        Set-CellBase $cellT
        foreach ($col in @(4, 5, 6, 7, 8)) {
            $srcL = $yearCol[2022 + ($col - 4)]
            New-Formula $wsC $r $col "=${DC}${srcL}${srcRow}/1000" $fmtK
        }
        New-Formula $wsC $r 9 "=${DC}H${srcRow}/1000" $fmtK
        New-Formula $wsC $r 10 "=${DC}J${srcRow}" $fmtInt
        $r++
    }
    Add-TableBorders $wsC $t20HdrRow 2 ($r - 1) 10

    $wsC.Columns.Item(2).ColumnWidth = 28
    for ($c = 3; $c -le 10; $c++) { $wsC.Columns.Item($c).ColumnWidth = 11 }

    # ================= TAB: Cohort Analysis =================
    Write-Host "Building Cohort Analysis..."
    $wsK = $wb.Sheets.Add([System.Type]::Missing, $wsC)
    $wsK.Name = "Cohort Analysis"
    $wsK.Columns.Item(1).ColumnWidth = 3
    New-Title $wsK "Cohort Analysis - first-revenue cohorts 2022-2026"

    $r = 4
    New-SectionBand $wsK $r 2 9 "Key findings"
    $r++
    New-CommentLine $wsK $r "1. Revenue base is dominated by the pre-2022 customer stock (2022 cohort) - the business lives off its installed base."; $r++
    New-CommentLine $wsK $r "2. The 2023 cohort is degrading: 682k -> 780k -> 514k. First-revenue cohorts since 2023 are smaller and decay faster."; $r++
    New-CommentLine $wsK $r "3. Retention is solid on the core base: NRR 90-102% in the full-year pairs, logo retention 67-79%."; $r++

    $r += 2
    New-SectionBand $wsK $r 2 9 "Methodology"
    $r++
    New-CommentLine $wsK $r "Cohort = first calendar year with revenue > 0 within the 2022-2026 data window. No true acquisition dates available - customers active before 2022 all land in the 2022 cohort (overstates that cohort)."; $r++
    New-CommentLine $wsK $r "Logo retention = customers active in year N still active in N+1. NRR = revenue in N+1 from customers active in N, divided by their full year-N revenue. 2026 is YTD (data through May) - pairs vs 2026 are partial."; $r++

    $r += 2
    New-SectionBand $wsK $r 2 9 "Revenue by first-revenue cohort, observed 2022-2026 (EUR k)"
    $r += 2
    $cohHdrRow = $r
    New-HeaderRow $wsK $r 2 @("Cohort", "# Customers", "2022", "2023", "2024", "2025", "2026 YTD")
    $r++
    $cohFirstRow = $r
    foreach ($cy in @(2022, 2023, 2024, 2025, 2026)) {
        New-Cell $wsK $r 2 "$cy cohort" $null $false
        New-Formula $wsK $r 3 "=COUNTIF($jCol,VALUE(LEFT(B$r,4)))" $fmtInt
        foreach ($y in @(2022, 2023, 2024, 2025, 2026)) {
            $col = 4 + ($y - 2022)
            $yc = $yearCol[$y]
            New-Formula $wsK $r $col "=SUMIFS($DC`$$yc`$$dcFirst`:`$$yc`$$dcLast,$jCol,VALUE(LEFT(`$B$r,4)))/1000" $fmtK
            if ($y -lt $cy) { $wsK.Cells.Item($r, $col).Interior.Color = $lightGray }
        }
        $r++
    }
    $cohLastRow = $r - 1
    $cohTotalRow = $r
    New-Cell $wsK $r 2 "Total" $null $false
    foreach ($col in @(3, 4, 5, 6, 7, 8)) {
        $colL = [char](64 + $col)
        $fmt = if ($col -eq 3) { $fmtInt } else { $fmtK }
        New-Formula $wsK $r $col "=SUM($colL$cohFirstRow`:$colL$cohLastRow)" $fmt
    }
    Set-TotalRow $wsK $r 2 8
    Add-TableBorders $wsK $cohHdrRow 2 $cohTotalRow 8

    $r += 3
    New-SectionBand $wsK $r 2 9 "Year-over-year retention (EUR k)"
    $r += 2
    $retHdrRow = $r
    New-HeaderRow $wsK $r 2 @("Period", "Active (start)", "Retained (next yr)", "Logo retention", "Rev (start)", "Rev retained (next yr)", "NRR")
    $r++
    foreach ($y in @(2022, 2023, 2024, 2025)) {
        $cy = $yearCol[$y]; $cn = $yearCol[$y + 1]
        $rngY = "$DC`$$cy`$$dcFirst`:`$$cy`$$dcLast"
        $rngN = "$DC`$$cn`$$dcFirst`:`$$cn`$$dcLast"
        $lbl = if ($y -eq 2025) { "2025 -> 2026 YTD (partial)" } else { "$y -> $($y + 1)" }
        New-Cell $wsK $r 2 $lbl $null $false
        if ($y -eq 2025) { $wsK.Cells.Item($r, 2).Font.Italic = $true }
        New-Formula $wsK $r 3 "=COUNTIF($rngY,"">0"")" $fmtInt
        New-Formula $wsK $r 4 "=COUNTIFS($rngY,"">0"",$rngN,"">0"")" $fmtInt
        New-Formula $wsK $r 5 "=D$r/C$r" $fmtPct
        New-Formula $wsK $r 6 "=SUM($rngY)/1000" $fmtK
        New-Formula $wsK $r 7 "=SUMIFS($rngN,$rngY,"">0"")/1000" $fmtK
        New-Formula $wsK $r 8 "=G$r/F$r" $fmtPct
        $r++
    }
    Add-TableBorders $wsK $retHdrRow 2 ($r - 1) 8

    $wsK.Columns.Item(2).ColumnWidth = 24
    for ($c = 3; $c -le 8; $c++) { $wsK.Columns.Item($c).ColumnWidth = 13 }

    # ================= TAB: Charts =================
    Write-Host "Building Charts..."
    $wsG = $wb.Sheets.Add([System.Type]::Missing, $wsK)
    $wsG.Name = "Charts"
    $wsG.Columns.Item(1).ColumnWidth = 3
    New-Title $wsG "Charts - copy directly into PowerPoint (sources are live ranges on the analysis tabs)"

    function Set-ChartStyle($ch, $title) {
        $ch.HasTitle = $true
        $ch.ChartTitle.Text = [string]$title
        $ch.ChartTitle.Font.Size = 12
        $ch.ChartTitle.Font.Bold = $true
        $ch.ChartArea.Font.Name = $fontName
        $ch.ChartArea.Font.Size = 10
        try { $ch.ChartArea.Format.Line.Visible = 0 } catch {}
    }
    function Set-SeriesColors($ch) {
        $cnt = $ch.SeriesCollection().Count
        for ($i = 1; $i -le $cnt; $i++) {
            try { $ch.SeriesCollection($i).Format.Fill.ForeColor.RGB = $palette[($i - 1) % $palette.Count] } catch {}
        }
    }
    function Clear-Series($ch) {
        while ($ch.SeriesCollection().Count -gt 0) { $ch.SeriesCollection(1).Delete() | Out-Null }
    }

    # Chart 1: revenue by segment (contiguous range)
    $co = $wsG.ChartObjects().Add(30, 40, 460, 270)
    $ch = $co.Chart
    $ch.SetSourceData($wsR.Range($wsR.Cells.Item($segHdrRow, 2), $wsR.Cells.Item($segLastRow, 6)), 2)
    $ch.ChartType = 51
    Set-ChartStyle $ch "Revenue by segment (EUR k; 2026 = YTD May)"
    Set-SeriesColors $ch
    try { $ch.Legend.Position = -4107 } catch {}

    # Chart 2: quarterly revenue (manual single series)
    $co = $wsG.ChartObjects().Add(520, 40, 460, 270)
    $ch = $co.Chart
    $ch.ChartType = 51
    Clear-Series $ch
    $s = $ch.SeriesCollection().NewSeries()
    $s.Values = $wsR.Range("E$qFirstRow`:E$qLastRow")
    $s.XValues = $wsR.Range("B$qFirstRow`:B$qLastRow")
    $s.Name = "Revenue"
    Set-ChartStyle $ch "Quarterly revenue (EUR k; 2026 = YTD May)"
    try { $ch.SeriesCollection(1).Format.Fill.ForeColor.RGB = $tealBGR } catch {}
    try { $ch.HasLegend = $false } catch {}

    # Chart 3: revenue by cohort (manual series per cohort row, stacked)
    $co = $wsG.ChartObjects().Add(30, 330, 460, 270)
    $ch = $co.Chart
    $ch.ChartType = 52
    Clear-Series $ch
    for ($rr = $cohFirstRow; $rr -le $cohLastRow; $rr++) {
        $s = $ch.SeriesCollection().NewSeries()
        $s.Values = $wsK.Range("D$rr`:H$rr")
        $s.XValues = $wsK.Range("D$cohHdrRow`:H$cohHdrRow")
        $s.Name = $wsK.Cells.Item($rr, 2).Text
    }
    Set-ChartStyle $ch "Revenue by first-revenue cohort (EUR k; 2026 = YTD May)"
    Set-SeriesColors $ch
    try { $ch.Legend.Position = -4107 } catch {}

    # Chart 4: concentration (manual single series)
    $co = $wsG.ChartObjects().Add(520, 330, 460, 270)
    $ch = $co.Chart
    $ch.ChartType = 57
    Clear-Series $ch
    $s = $ch.SeriesCollection().NewSeries()
    $s.Values = $wsC.Range("E$concFirstRow`:E$($concFirstRow + 3)")
    $s.XValues = $wsC.Range("B$concFirstRow`:B$($concFirstRow + 3)")
    $s.Name = "Share of 2025 revenue"
    Set-ChartStyle $ch "Customer concentration 2025 (% of revenue)"
    try { $ch.SeriesCollection(1).Format.Fill.ForeColor.RGB = $tealBGR } catch {}
    try { $ch.HasLegend = $false } catch {}
    try { $ch.Axes(2).TickLabels.NumberFormat = "0%" } catch {}

    # Chart 5: revenue by customer type (manual series per type row, stacked)
    $co = $wsG.ChartObjects().Add(30, 620, 460, 270)
    $ch = $co.Chart
    $ch.ChartType = 52
    Clear-Series $ch
    for ($rr = $typeFirstRow; $rr -le $typeLastRow; $rr++) {
        $s = $ch.SeriesCollection().NewSeries()
        $s.Values = $wsC.Range("D$rr`:H$rr")
        $s.XValues = $wsC.Range("D$typeHdrRow`:H$typeHdrRow")
        $s.Name = $wsC.Cells.Item($rr, 2).Text
    }
    Set-ChartStyle $ch "Revenue by customer type (EUR k)"
    Set-SeriesColors $ch
    try { $ch.Legend.Position = -4107 } catch {}

    # ================= TAB: Gaps and Confidence =================
    Write-Host "Building Gaps and Confidence..."
    $wsQ = $wb.Sheets.Add([System.Type]::Missing, $wsG)
    $wsQ.Name = "Gaps and Confidence"
    $wsQ.Columns.Item(1).ColumnWidth = 3
    $wsQ.Columns.Item(2).ColumnWidth = 32
    $wsQ.Columns.Item(3).ColumnWidth = 75
    $wsQ.Columns.Item(4).ColumnWidth = 14
    New-Title $wsQ "Data gaps and confidence"

    $r = 4
    New-SectionBand $wsQ $r 2 4 "Data gaps"
    $r += 2
    $gapHdr = $r
    New-HeaderRow $wsQ $r 2 @("Item", "Description", "Severity")
    $r++
    $gaps = @(
        @{ I = "2025 GuV vorlaeufig + unverified pro-forma"; D = "2025 GuV is preliminary (bis Periode 16). Seller EBIT bridge items all unverified: 120k revenue shift to 2026, 28k Bestandskorrektur, 80k Olympus prep costs, GF salary normalization (384k -> 140k + 18% NK). Final JA 2025, SuSa and BWA 2026 outstanding."; S = "HIGH" },
        @{ I = "EBIT margin drop 2025"; D = "Reported EBIT 716.8k -> 320.3k (23.2% -> 10.1% margin). Even seller pro-forma (550.1k) is -31% vs 2024 pro-forma (794.6k). Drivers must be verified before any valuation discussion."; S = "HIGH" },
        @{ I = "Rohertrag = materials-only margin"; D = "GuV Rohertrag 2025 = 57.7% of revenue; invoice Rohertrag field is consistent with a materials-only margin (explains GM c. 100% on service contracts and 36 negative-GM invoices). Segment GM% are contribution margins, not fully-loaded margins. Definition to be confirmed (RFI Q8)."; S = "MEDIUM" },
        @{ I = "No churn reasons"; D = "Churned customers (>10k revenue in 2023 or 2024, zero in 2025/2026) - reasons unknown. See RFI doc Q1 and the highlighted Kundendaten tab there."; S = "MEDIUM" },
        @{ I = "Cohort window effect"; D = "Cohort = first revenue year in 2022-2026 window. Pre-2022 customers all land in the 2022 cohort - true acquisition dates unknown."; S = "LOW" },
        @{ I = "1.1 vs 1.3 residual deltas"; D = "Files reconcile within <2% p.a. - normal for commercial data (credit notes/timing). Short seller confirmation suffices (RFI Q10)."; S = "LOW" }
    )
    foreach ($g in $gaps) {
        New-Cell $wsQ $r 2 ([string]$g.I) $null $false
        New-Cell $wsQ $r 3 ([string]$g.D) $null $false
        New-Cell $wsQ $r 4 ([string]$g.S) $null $true
        $wsQ.Cells.Item($r, 3).WrapText = $true
        if ($g.S -eq "HIGH") { $wsQ.Cells.Item($r, 4).Font.Color = $accent3BGR; $wsQ.Cells.Item($r, 4).Font.Bold = $true }
        elseif ($g.S -eq "MEDIUM") { $wsQ.Cells.Item($r, 4).Font.Color = 32768 }
        $r++
    }
    Add-TableBorders $wsQ $gapHdr 2 ($r - 1) 4

    $r += 2
    New-SectionBand $wsQ $r 2 4 "Confidence by analysis"
    $r += 2
    $confHdr = $r
    New-HeaderRow $wsQ $r 2 @("Analysis", "Confidence", "Notes")
    $r++
    $conf = @(
        @{ A = "Revenue by service segment"; C = "HIGH"; N = "Live SUMIFS off 3,015 seller invoices; ties to seller pivot (delta 0) and GuV (<2%)" },
        @{ A = "Revenue coverage"; C = "HIGH 22-24 / MEDIUM 25"; N = "GuV cross-check complete; 2025 tie-out depends on the seller's unverified 120k shift" },
        @{ A = "Gross margin by segment"; C = "MEDIUM"; N = "Materials-only margin (DB I); labor not allocated per segment" },
        @{ A = "Customer concentration"; C = "HIGH"; N = "Full company revenue scope confirmed via GuV" },
        @{ A = "Customer type split"; C = "HIGH"; N = "Type field consistently populated" },
        @{ A = "Cohort analysis"; C = "MEDIUM"; N = "Window effect: pre-2022 customers lumped into 2022 cohort" },
        @{ A = "Retention / NRR"; C = "MEDIUM"; N = "Live formulas; 2026 pairs partial (data through May)" },
        @{ A = "EBIT quality"; C = "LOW"; N = "Vorlaeufige GuV + unverified seller pro-forma bridge - the central open DD item" }
    )
    foreach ($c in $conf) {
        New-Cell $wsQ $r 2 ([string]$c.A) $null $false
        New-Cell $wsQ $r 3 ([string]$c.C) $null $false
        New-Cell $wsQ $r 4 ([string]$c.N) $null $false
        $wsQ.Cells.Item($r, 4).WrapText = $true
        $r++
    }
    Add-TableBorders $wsQ $confHdr 2 ($r - 1) 4

    $r += 2
    New-CommentLine $wsQ $r "Open questions to the seller: see separate RFI document 260610_Mantis_RFI_Fragenliste_v1.xlsx (numbered, source references, severity, answer column)."
    $wsQ.Cells.Item($r, 2).Font.Bold = $true

    # ================= TAB: Summary (first) =================
    Write-Host "Building Summary..."
    $wsS = $wb.Sheets.Add($wb.Sheets.Item(1))
    $wsS.Name = "Summary"
    $wsS.Columns.Item(1).ColumnWidth = 3
    $wsS.Columns.Item(2).ColumnWidth = 6
    $wsS.Columns.Item(3).ColumnWidth = 55
    $wsS.Columns.Item(4).ColumnWidth = 65
    $wsS.Columns.Item(5).ColumnWidth = 12
    New-Title $wsS "Project Mantis - CDD Databook (Draft v3)"
    New-CommentLine $wsS 3 "Revenue, customer and cohort analysis | Sources: seller files 1.1 + 1.3 and GuV 2022-2025 (4.1) | Built 2026-06-10 | Analysis tables are live formulas; GuV figures hardcoded with source labels"

    $r = 5
    New-SectionBand $wsS $r 2 5 "Answer first - what the data says"
    $r++
    $answers = @(
        "1. REVENUE LARGELY VERIFIED: commercial data ties to the GuV within <2% for 2022-2024; 2025 is +3.9% vs the vorlaeufige GuV and reconciles only via the seller's unverified 120k shift into 2026. Scope = full company revenue (GuV 2025: 3,058k reported / 3,178k pro-forma). Growth stalled: +17% (2023), +12% (2024), -1% reported / +3% pro-forma (2025).",
        "2. The customer base is the asset: sticky installed base, c. 94% of 2025 revenue from existing customers, NRR 90-102% - but concentrated (Top 20 = c. 71%) and new first-revenue cohorts since 2023 are small and decay quickly.",
        "3. THE ISSUE IS EBIT, NOT REVENUE: reported EBIT fell 716.8k -> 320.3k (23.2% -> 10.1%). Seller pro-forma of 550.1k rests on unverified items (120k revenue shift, 28k inventory, 80k Olympus, GF salary normalization). Verifying this bridge is the core of the financial DD.",
        "4. Verdict: stable c. 3.1m revenue service business with real margin questions. Price on verified EBIT, not seller pro-forma, until the bridge is evidenced."
    )
    foreach ($a in $answers) {
        $cell = $wsS.Cells.Item($r, 2)
        $wsS.Range($wsS.Cells.Item($r, 2), $wsS.Cells.Item($r, 5)).Merge()
        $cell.Value2 = [string]$a
        Set-CellBase $cell
        $cell.WrapText = $true
        $wsS.Rows.Item($r).RowHeight = 38
        $r++
    }

    $r += 1
    New-SectionBand $wsS $r 2 5 "Red flags / watch items"
    $r += 2
    $rfHdr = $r
    New-HeaderRow $wsS $r 2 @("#", "Finding", "So what", "Severity")
    $r++
    $flags = @(
        @{ F = "Reported EBIT -55% in 2025 (716.8k -> 320.3k)"; SW = "Seller pro-forma rests on unverified one-offs - core valuation risk"; S = "HIGH" },
        @{ F = "2025 GuV vorlaeufig (bis Periode 16); SuSa/BWA missing"; SW = "Final JA may shift numbers - request final accounts + SuSa + BWA 2026"; S = "HIGH" },
        @{ F = "Krankenhaus 2024 spike (983k -> 1,721k -> 1,377k, 2023-2025)"; SW = "If one-off, underlying 2024 growth is optics, not trend"; S = "HIGH" },
        @{ F = "Mobiler Kundendienst -24% in 2025 (378k -> 286k)"; SW = "Field service shrinking - structural shift or lost territories?"; S = "MEDIUM" },
        @{ F = "2023 cohort degrading (682k -> 780k -> 514k)"; SW = "New customer vintages decay - new business not replacing churn value"; S = "MEDIUM" },
        @{ F = "Dealer channel volatile (573k -> 364k -> 929k, 2023-2025; 959k in 2022)"; SW = "Lumpy project revenue, possible dealer concentration"; S = "MEDIUM" },
        @{ F = "Rohertrag = materials-only margin (GM c. 100% on service contracts)"; SW = "Segment GM% are contribution margins - do not read as full margins"; S = "MEDIUM" }
    )
    $idx = 1
    foreach ($f in $flags) {
        New-Cell $wsS $r 2 $idx $fmtInt $true
        New-Cell $wsS $r 3 ([string]$f.F) $null $false
        New-Cell $wsS $r 4 ([string]$f.SW) $null $false
        New-Cell $wsS $r 5 ([string]$f.S) $null $true
        $wsS.Cells.Item($r, 3).WrapText = $true
        $wsS.Cells.Item($r, 4).WrapText = $true
        if ($f.S -eq "HIGH") { $wsS.Cells.Item($r, 5).Font.Color = $accent3BGR; $wsS.Cells.Item($r, 5).Font.Bold = $true }
        elseif ($f.S -eq "MEDIUM") { $wsS.Cells.Item($r, 5).Font.Color = 32768 }
        $idx++; $r++
    }
    Add-TableBorders $wsS $rfHdr 2 ($r - 1) 5

    $r += 2
    New-SectionBand $wsS $r 2 5 "How to read this file"
    $r++
    $howTo = @(
        "- All analysis tables are LIVE FORMULAS off the two raw data tabs (Data Invoices, Data Customers). GuV figures are hardcoded values with source labels.",
        "- Figures in EUR thousands unless stated. Number format: one decimal, negatives in parentheses, zero as dash.",
        "- Data Customers is sorted by 2025 revenue descending. Cohort = first year with revenue in the 2022-2026 window (pre-2022 customers appear as 2022 cohort).",
        "- Charts tab: charts are PowerPoint-ready, sourced from live ranges on the analysis tabs.",
        "- Open questions to the seller live in the separate RFI document (260610_Mantis_RFI_Fragenliste_v1.xlsx), not in this file."
    )
    foreach ($h in $howTo) {
        $cell = $wsS.Cells.Item($r, 2)
        $wsS.Range($wsS.Cells.Item($r, 2), $wsS.Cells.Item($r, 5)).Merge()
        $cell.Value2 = [string]$h
        Set-CellBase $cell
        $r++
    }

    # ================= FINAL: tab order, gridlines, save =================
    Write-Host "Finalizing..."
    foreach ($wsX in @($wsDI, $wsDC)) {
        $ur = $wsX.UsedRange
        $ur.Font.Name = $fontName
        $ur.Font.Size = 10
    }
    $wsDI.Move([System.Type]::Missing, $wb.Sheets.Item($wb.Sheets.Count))
    $wsDC.Move([System.Type]::Missing, $wb.Sheets.Item($wb.Sheets.Count))

    foreach ($ws in $wb.Sheets) {
        $ws.Activate()
        $excel.ActiveWindow.DisplayGridlines = $false
    }
    $wb.Sheets.Item("Summary").Activate()

    if (Test-Path $outputPath) { Remove-Item $outputPath -Force }
    $wb.SaveAs($outputPath, 51)
    $wb.Close($false)
    Write-Host "DONE: $outputPath"

} catch {
    Write-Host "ERROR: $_"
    Write-Host $_.ScriptStackTrace
} finally {
    try { $excel.Quit() } catch {}
    try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch {}
}
