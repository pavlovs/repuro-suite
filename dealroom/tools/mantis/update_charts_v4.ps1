# Update v4 charts for PPT: chart1 -> 4 reporting lines; add donut (sales split 2025) + revenue-nature mix
$ErrorActionPreference = "Stop"
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
Get-Process excel -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$fontName = "Aptos Narrow"
$tealBGR = 11702536
$palette = @(11702536, 15651618, 16181389, 570346, 16209320, 4726241)
try {
    $wb = $excel.Workbooks.Open("C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd\CDD_Databook_Mantis_v4.xlsx")
    $wsR = $wb.Sheets.Item("Revenue Analysis")
    $wsG = $wb.Sheets.Item("Charts")

    function Set-Style($ch, $title) {
        $ch.HasTitle = $true
        $ch.ChartTitle.Text = [string]$title
        $ch.ChartTitle.Font.Size = 12; $ch.ChartTitle.Font.Bold = $true
        $ch.ChartArea.Font.Name = $fontName; $ch.ChartArea.Font.Size = 10
        try { $ch.ChartArea.Format.Line.Visible = 0 } catch {}
    }

    # ---- Chart 1: repoint to 4 reporting lines (rows 15,16,17,19; years C..F) ----
    $c1 = $wsG.ChartObjects(1).Chart
    while ($c1.SeriesCollection().Count -gt 0) { $c1.SeriesCollection(1).Delete() | Out-Null }
    foreach ($row in @(15, 16, 17, 19)) {
        $s = $c1.SeriesCollection().NewSeries()
        $s.Values = $wsR.Range("C$row`:F$row")
        $s.XValues = $wsR.Range("C14:F14")
        $s.Name = $wsR.Cells.Item($row, 2).Text
    }
    $c1.ChartType = 51
    Set-Style $c1 "Revenue by reporting line (EUR k; 2026 = YTD May)"
    for ($i = 1; $i -le 4; $i++) { try { $c1.SeriesCollection($i).Format.Fill.ForeColor.RGB = $palette[$i - 1] } catch {} }
    try { $c1.Legend.Position = -4107 } catch {}
    Write-Host "chart1 repointed: $($c1.SeriesCollection().Count) series"

    # ---- Chart 7: Sales split 2025 donut/pie (static values read live at build) ----
    $names = @(); $vals = @()
    foreach ($row in @(15, 16, 17, 19)) {
        $names += $wsR.Cells.Item($row, 2).Text
        $vals += [double]$wsR.Cells.Item($row, 5).Value2   # col E = 2025
    }
    $co = $wsG.ChartObjects().Add(980, 40, 320, 290)
    $ch = $co.Chart
    $ch.ChartType = 5
    while ($ch.SeriesCollection().Count -gt 0) { $ch.SeriesCollection(1).Delete() | Out-Null }
    $s = $ch.SeriesCollection().NewSeries()
    $s.Values = $vals
    $s.XValues = $names
    $s.Name = "2025"
    Set-Style $ch "Sales split 2025 (EUR k)"
    for ($i = 1; $i -le 4; $i++) { try { $s.Points($i).Format.Fill.ForeColor.RGB = $palette[$i - 1] } catch {} }
    try {
        $s.HasDataLabels = $true
        $s.DataLabels.ShowPercentage = $true
        $s.DataLabels.ShowValue = $false
        $s.DataLabels.Font.Size = 10
    } catch {}
    try { $ch.Legend.Position = -4107 } catch {}
    Write-Host "chart7 donut added"

    # ---- Chart 8: revenue by nature, 100% stacked (helper table on Charts!B40) ----
    $wsG.Cells.Item(40, 2).Value2 = "Nature"
    $wsG.Cells.Item(40, 3).NumberFormatLocal = "@"; $wsG.Cells.Item(40, 3).Value2 = "2023"
    $wsG.Cells.Item(40, 4).NumberFormatLocal = "@"; $wsG.Cells.Item(40, 4).Value2 = "2024"
    $wsG.Cells.Item(40, 5).NumberFormatLocal = "@"; $wsG.Cells.Item(40, 5).Value2 = "2025"
    $wsG.Cells.Item(41, 2).Value2 = "Contractual service (recurring)"
    $wsG.Cells.Item(42, 2).Value2 = "Repairs & other (re-occurring)"
    $wsG.Cells.Item(43, 2).Value2 = "Product sales (Vertrieb)"
    foreach ($p in @(@(3, "C"), @(4, "D"), @(5, "E"))) {
        $c = $p[0]; $L = $p[1]
        $wsG.Cells.Item(41, $c).Formula = "='Revenue Analysis'!$L`17"
        $wsG.Cells.Item(42, $c).Formula = "='Revenue Analysis'!$L`16+'Revenue Analysis'!$L`19"
        $wsG.Cells.Item(43, $c).Formula = "='Revenue Analysis'!$L`15"
    }
    $co = $wsG.ChartObjects().Add(980, 350, 320, 290)
    $ch = $co.Chart
    $ch.ChartType = 53
    while ($ch.SeriesCollection().Count -gt 0) { $ch.SeriesCollection(1).Delete() | Out-Null }
    foreach ($row in @(41, 42, 43)) {
        $s = $ch.SeriesCollection().NewSeries()
        $s.Values = $wsG.Range("C$row`:E$row")
        $s.XValues = $wsG.Range("C40:E40")
        $s.Name = $wsG.Cells.Item($row, 2).Text
    }
    Set-Style $ch "Revenue by nature (% of total)"
    for ($i = 1; $i -le 3; $i++) { try { $ch.SeriesCollection($i).Format.Fill.ForeColor.RGB = $palette[$i - 1] } catch {} }
    try { $ch.Legend.Position = -4107 } catch {}
    Write-Host "chart8 nature mix added"

    Start-Sleep -Seconds 2
    $excel.CalculateUntilAsyncQueriesDone() | Out-Null
    try { $wb.Save() } catch {
        Write-Host "  Save() failed, retrying via SaveAs: $($_.Exception.Message)"
        Start-Sleep -Seconds 2
        $wb.SaveAs("C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd\CDD_Databook_Mantis_v4.xlsx", 51)
    }
    Write-Host "DONE charts: $($wsG.ChartObjects().Count) total"
    $wb.Close($false)
} catch {
    Write-Host "ERROR: $_"
    Write-Host $_.ScriptStackTrace
} finally {
    try { $excel.Quit() } catch {}
}
