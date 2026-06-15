# v4 = Roman's v3_RD + Churn Analysis tab + bridge chart + commentary fills. Surgical, in-place on a COPY.
$ErrorActionPreference = "Stop"
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$tempDir = "C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd"
$outputPath = "$tempDir\CDD_Databook_Mantis_v4.xlsx"
Copy-Item "$tempDir\v3_RD.xlsx" $outputPath -Force

Get-Process excel -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$tealBGR = 11702536
$bandBGR = 16181389
$white = 16777215
$fmtK = "#.##0,0;\ \(#.##0,0\);\ \-"
$fmtInt = "#.##0"
$fmtPct = "0,0%"
$fontName = "Aptos Narrow"

function Set-CellBase($cell) { $cell.Font.Name = $fontName; $cell.Font.Size = 10; $cell.VerticalAlignment = -4108 }
function New-Cell($ws, $r, $c, $v, $fmt, $center) {
    $cell = $ws.Cells.Item($r, $c)
    if ($v -is [string]) { $cell.Value2 = $v } else { $cell.Formula = "=" + [string]::Format($inv, "{0:R}", [double]$v) }
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
        $cell.Font.Bold = $true; $cell.Font.Color = $white; $cell.Interior.Color = $tealBGR
        $cell.HorizontalAlignment = -4108
    }
}
function New-SectionBand($ws, $row, $startCol, $endCol, $text) {
    $rng = $ws.Range($ws.Cells.Item($row, $startCol), $ws.Cells.Item($row, $endCol))
    $rng.Interior.Color = $bandBGR
    $cell = $ws.Cells.Item($row, $startCol)
    $cell.Value2 = [string]$text
    Set-CellBase $cell; $cell.Font.Bold = $true; $cell.Font.Size = 11
}
function New-CommentLine($ws, $r, $text) { $cell = $ws.Cells.Item($r, 2); $cell.Value2 = [string]$text; Set-CellBase $cell }
function Add-TableBorders($ws, $r1, $c1, $r2, $c2) {
    $rng = $ws.Range($ws.Cells.Item($r1, $c1), $ws.Cells.Item($r2, $c2))
    $rng.Borders.LineStyle = 1; $rng.Borders.Weight = 2
}

try {
    $wb = $excel.Workbooks.Open($outputPath)

    # ---- Data Customers layout in v3_RD: header R2, data R3.., C=Kunden D=2022 E=2023 F=2024 G=2025 H=2026 K=Cohort
    $wsDC = $wb.Sheets.Item("Data Customers")
    $dcFirst = 3
    $dcLast = 2
    for ($r = 3; $r -le 1200; $r++) {
        if ($wsDC.Cells.Item($r, 3).Text -eq "") { break }
        $dcLast = $r
    }
    Write-Host "  Data Customers rows: $dcFirst..$dcLast"
    $DC = "'Data Customers'!"
    $yearCol = @{ 2022 = "D"; 2023 = "E"; 2024 = "F"; 2025 = "G"; 2026 = "H" }
    $tCol = "$DC`$C`$$dcFirst`:`$C`$$dcLast"

    # type list by total desc
    $typeSums = @{}
    for ($r = $dcFirst; $r -le $dcLast; $r++) {
        $t = $wsDC.Cells.Item($r, 3).Text
        if ($t -eq "") { continue }
        if (-not $typeSums.ContainsKey($t)) { $typeSums[$t] = 0.0 }
        $g = $wsDC.Cells.Item($r, 9).Value2
        if ($g -is [double]) { $typeSums[$t] += $g }
    }
    $typeNames = @($typeSums.Keys | Sort-Object { $typeSums[$_] } -Descending)

    # ---- New tab after Cohort Analysis ----
    $wsCh = $wb.Sheets.Add([System.Type]::Missing, $wb.Sheets.Item("Cohort Analysis"))
    $wsCh.Name = "Churn Analysis"
    $wsCh.Columns.Item(1).ColumnWidth = 3
    $cell = $wsCh.Cells.Item(2, 2)
    $cell.Value2 = "Churn Analysis - customer attrition and revenue bridge (full revenue scope)"
    $cell.Font.Name = $fontName; $cell.Font.Size = 13; $cell.Font.Bold = $true

    $r = 4
    $churnKfRow = $r
    New-SectionBand $wsCh $r 2 9 "Key findings"
    $r += 4

    $r += 1
    New-SectionBand $wsCh $r 2 9 "Churn by year (EUR k; churned = revenue in year N, none in N+1; churned revenue valued at year-N revenue)"
    $r += 2
    $chHdrRow = $r
    New-HeaderRow $wsCh $r 2 @("Period", "Active (start)", "Churned logos", "Logo churn %", "Churned revenue", "Revenue churn %")
    $r++
    $chFirstRow = $r
    foreach ($y in @(2022, 2023, 2024, 2025)) {
        $a = $yearCol[$y]; $b = $yearCol[$y + 1]
        $rngA = "$DC`$$a`$$dcFirst`:`$$a`$$dcLast"
        $rngB = "$DC`$$b`$$dcFirst`:`$$b`$$dcLast"
        $lbl = if ($y -eq 2025) { "2025 -> 2026 YTD (partial)" } else { "$y -> $($y + 1)" }
        New-Cell $wsCh $r 2 $lbl $null $false
        if ($y -eq 2025) { $wsCh.Cells.Item($r, 2).Font.Italic = $true }
        New-Formula $wsCh $r 3 "=COUNTIF($rngA,"">0"")" $fmtInt
        New-Formula $wsCh $r 4 "=COUNTIFS($rngA,"">0"",$rngB,""<=0"")" $fmtInt
        New-Formula $wsCh $r 5 "=D$r/C$r" $fmtPct
        New-Formula $wsCh $r 6 "=SUMIFS($rngA,$rngA,"">0"",$rngB,""<=0"")/1000" $fmtK
        New-Formula $wsCh $r 7 "=F$r/(SUM($rngA)/1000)" $fmtPct
        $r++
    }
    Add-TableBorders $wsCh $chHdrRow 2 ($r - 1) 7

    $r += 2
    New-SectionBand $wsCh $r 2 9 "Revenue bridge by year (EUR k; Start - churned +/- net retained + new/reactivated = End)"
    $r += 2
    $brHdrRow = $r
    New-HeaderRow $wsCh $r 2 @("Period", "Start", "- Churned", "+/- Net retained", "+ New/reactivated", "= End", "Check")
    $r++
    $brFirstRow = $r
    foreach ($y in @(2022, 2023, 2024)) {
        $a = $yearCol[$y]; $b = $yearCol[$y + 1]
        $rngA = "$DC`$$a`$$dcFirst`:`$$a`$$dcLast"
        $rngB = "$DC`$$b`$$dcFirst`:`$$b`$$dcLast"
        New-Cell $wsCh $r 2 "$y -> $($y + 1)" $null $false
        New-Formula $wsCh $r 3 "=SUM($rngA)/1000" $fmtK
        New-Formula $wsCh $r 4 "=-SUMIFS($rngA,$rngA,"">0"",$rngB,""<=0"")/1000" $fmtK
        New-Formula $wsCh $r 5 "=(SUMIFS($rngB,$rngA,"">0"",$rngB,"">0"")-SUMIFS($rngA,$rngA,"">0"",$rngB,"">0""))/1000" $fmtK
        New-Formula $wsCh $r 6 "=SUMIFS($rngB,$rngA,""<=0"")/1000" $fmtK
        New-Formula $wsCh $r 7 "=SUM($rngB)/1000" $fmtK
        New-Formula $wsCh $r 8 "=C$r+D$r+E$r+F$r-G$r" $fmtK
        $r++
    }
    $brLastRow = $r - 1
    Add-TableBorders $wsCh $brHdrRow 2 $brLastRow 8

    $r += 2
    New-SectionBand $wsCh $r 2 9 "Churn by customer type, 2024 -> 2025 (EUR k)"
    $r += 2
    $ctHdrRow = $r
    New-HeaderRow $wsCh $r 2 @("Customer type", "Active 2024", "Churned", "Logo churn %", "Churned revenue (2024)")
    $r++
    $rngE24 = "$DC`$F`$$dcFirst`:`$F`$$dcLast"
    $rngF25 = "$DC`$G`$$dcFirst`:`$G`$$dcLast"
    foreach ($t in $typeNames) {
        New-Cell $wsCh $r 2 ([string]$t) $null $false
        New-Formula $wsCh $r 3 "=COUNTIFS($tCol,`$B$r,$rngE24,"">0"")" $fmtInt
        New-Formula $wsCh $r 4 "=COUNTIFS($tCol,`$B$r,$rngE24,"">0"",$rngF25,""<=0"")" $fmtInt
        New-Formula $wsCh $r 5 "=IFERROR(D$r/C$r,"""")" $fmtPct
        New-Formula $wsCh $r 6 "=SUMIFS($rngE24,$tCol,`$B$r,$rngE24,"">0"",$rngF25,""<=0"")/1000" $fmtK
        $r++
    }
    Add-TableBorders $wsCh $ctHdrRow 2 ($r - 1) 6

    # dynamic key findings from computed values
    $logo2223 = $wsCh.Cells.Item($chFirstRow, 5).Value2
    $logo2324 = $wsCh.Cells.Item($chFirstRow + 1, 5).Value2
    $logo2425 = $wsCh.Cells.Item($chFirstRow + 2, 5).Value2
    $churnLogos2425 = $wsCh.Cells.Item($chFirstRow + 2, 4).Value2
    $churnRev2425 = $wsCh.Cells.Item($chFirstRow + 2, 6).Value2
    $newRev2425 = $wsCh.Cells.Item($brFirstRow + 2, 6).Value2
    $net2324 = $wsCh.Cells.Item($brFirstRow + 1, 7).Value2 - $wsCh.Cells.Item($brFirstRow + 1, 3).Value2
    $net2425 = $wsCh.Cells.Item($brFirstRow + 2, 7).Value2 - $wsCh.Cells.Item($brFirstRow + 2, 3).Value2
    $loMin = [Math]::Min([Math]::Min($logo2223, $logo2324), $logo2425)
    $loMax = [Math]::Max([Math]::Max($logo2223, $logo2324), $logo2425)
    $kf1 = "1. Logo churn runs at " + [string]::Format($inv, "{0:P0}", $loMin) + "-" + [string]::Format($inv, "{0:P0}", $loMax) + " p.a. In 2024 -> 2025 the company lost " + [int]$churnLogos2425 + " customers carrying " + [string]::Format($inv, "{0:N0}", $churnRev2425) + "k of prior-year revenue."
    $kf2 = "2. The bridge turned: 2023 -> 2024 added " + [string]::Format($inv, "{0:+#,##0;-#,##0}", $net2324) + "k net revenue, 2024 -> 2025 only " + [string]::Format($inv, "{0:+#,##0;-#,##0}", $net2425) + "k - churn and contraction now nearly offset expansion plus " + [string]::Format($inv, "{0:N0}", $newRev2425) + "k of new/reactivated business."
    $kf3 = "3. Churn reasons are unknown - the churned >10k accounts are highlighted in the RFI Kundendaten tab (Q1). High churned revenue concentrates in the types shown below."
    New-CommentLine $wsCh ($churnKfRow + 1) $kf1
    New-CommentLine $wsCh ($churnKfRow + 2) $kf2
    New-CommentLine $wsCh ($churnKfRow + 3) $kf3

    $wsCh.Columns.Item(2).ColumnWidth = 26
    for ($c = 3; $c -le 8; $c++) { $wsCh.Columns.Item($c).ColumnWidth = 15 }

    # ---- Chart 6 on Charts tab: revenue bridge 2024 -> 2025 ----
    $wsG = $wb.Sheets.Item("Charts")
    $co = $wsG.ChartObjects().Add(520, 620, 460, 270)
    $ch = $co.Chart
    $ch.ChartType = 51
    while ($ch.SeriesCollection().Count -gt 0) { $ch.SeriesCollection(1).Delete() | Out-Null }
    $brRow = $brFirstRow + 2
    $s = $ch.SeriesCollection().NewSeries()
    $s.Values = $wsCh.Range("C$brRow`:G$brRow")
    $s.XValues = $wsCh.Range("C$brHdrRow`:G$brHdrRow")
    $s.Name = "EUR k"
    $ch.HasTitle = $true
    $ch.ChartTitle.Text = "Revenue bridge 2024 -> 2025 (EUR k)"
    $ch.ChartTitle.Font.Size = 12; $ch.ChartTitle.Font.Bold = $true
    $ch.ChartArea.Font.Name = $fontName; $ch.ChartArea.Font.Size = 10
    try { $ch.SeriesCollection(1).Format.Fill.ForeColor.RGB = $tealBGR } catch {}
    try { $ch.HasLegend = $false } catch {}

    # ---- health check chart 1 (Roman's segment-table restructure may have shifted its source) ----
    try {
        $c1 = $wsG.ChartObjects(1).Chart
        Write-Host "  chart1 series: $($c1.SeriesCollection().Count) ; s1 formula: $($c1.SeriesCollection(1).Formula)"
    } catch { Write-Host "  chart1 check failed: $($_.Exception.Message)" }

    # ---- fill Roman's Commentary column on Customer Analysis (G45 header exists) ----
    $wsC = $wb.Sheets.Item("Customer Analysis")
    $cmt = $wsC.Cells.Item(46, 7)
    $cmt.Value2 = "Existing base carries 94-95% of revenue in both years - the business runs on its installed base; new accounts add <200k p.a."
    Set-CellBase $cmt
    $cmt.WrapText = $true
    $wsC.Range($wsC.Cells.Item(46, 7), $wsC.Cells.Item(51, 9)).Merge()

    # gridlines off for new tab
    $wsCh.Activate()
    $excel.ActiveWindow.DisplayGridlines = $false
    $wb.Sheets.Item("Summary").Activate()

    $wb.Save()
    $wb.Close($false)
    Write-Host "DONE: $outputPath"
} catch {
    Write-Host "ERROR: $_"
    Write-Host $_.ScriptStackTrace
} finally {
    try { $excel.Quit() } catch {}
    try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null } catch {}
}
