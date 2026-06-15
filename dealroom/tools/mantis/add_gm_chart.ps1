$ErrorActionPreference = "Stop"
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
$png = "C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd\png"
Get-Process excel -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false; $excel.DisplayAlerts = $false
$fontName = "Aptos Narrow"
$palette = @(11702536, 15651618, 16181389)
try {
    $wb = $excel.Workbooks.Open("C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd\CDD_Databook_Mantis_v4.xlsx")
    $wsG = $wb.Sheets.Item("Charts")
    $DI = "'Data Invoices'!"
    $RA = "'Revenue Analysis'!"
    # helper GM table at B46 (criteria reference the segment label cells on Revenue Analysis B15:B17)
    $wsG.Cells.Item(46, 2).Value2 = "GM by line"
    foreach ($p in @(@(3, "2023"), @(4, "2024"), @(5, "2025"))) {
        $c = $p[0]; $wsG.Cells.Item(46, $c).NumberFormatLocal = "@"; $wsG.Cells.Item(46, $c).Value2 = $p[1]
    }
    $rows = @(@(47, 15), @(48, 16), @(49, 17))
    foreach ($rp in $rows) {
        $r = $rp[0]; $src = $rp[1]
        $wsG.Cells.Item($r, 2).Formula = "=$RA`B$src"
        foreach ($yp in @(@(3, 2023), @(4, 2024), @(5, 2025))) {
            $c = $yp[0]; $y = $yp[1]
            $wsG.Cells.Item($r, $c).Formula = "=SUMIFS($DI`$J:`$J,$DI`$G:`$G,$RA`$B$src,$DI`$K:`$K,$y)/SUMIFS($DI`$D:`$D,$DI`$G:`$G,$RA`$B$src,$DI`$K:`$K,$y)"
            $wsG.Cells.Item($r, $c).NumberFormatLocal = "0,0%"
        }
    }
    $wsG.Cells.Item(50, 2).Value2 = "Other services"
    foreach ($yp in @(@(3, 2023), @(4, 2024), @(5, 2025))) {
        $c = $yp[0]; $y = $yp[1]
        $num = "SUMIFS($DI`$J:`$J,$DI`$K:`$K,$y)-SUMIFS($DI`$J:`$J,$DI`$G:`$G,$RA`$B`$15,$DI`$K:`$K,$y)-SUMIFS($DI`$J:`$J,$DI`$G:`$G,$RA`$B`$16,$DI`$K:`$K,$y)-SUMIFS($DI`$J:`$J,$DI`$G:`$G,$RA`$B`$17,$DI`$K:`$K,$y)"
        $den = "SUMIFS($DI`$D:`$D,$DI`$K:`$K,$y)-SUMIFS($DI`$D:`$D,$DI`$G:`$G,$RA`$B`$15,$DI`$K:`$K,$y)-SUMIFS($DI`$D:`$D,$DI`$G:`$G,$RA`$B`$16,$DI`$K:`$K,$y)-SUMIFS($DI`$D:`$D,$DI`$G:`$G,$RA`$B`$17,$DI`$K:`$K,$y)"
        $wsG.Cells.Item(50, $c).Formula = "=($num)/($den)"
        $wsG.Cells.Item(50, $c).NumberFormatLocal = "0,0%"
    }
    # chart 9
    $exists = $false
    for ($i = 1; $i -le $wsG.ChartObjects().Count; $i++) {
        $t = try { $wsG.ChartObjects($i).Chart.ChartTitle.Text } catch { "" }
        if ($t -like "Gross margin by reporting*") { $exists = $true }
    }
    if (-not $exists) {
        $co = $wsG.ChartObjects().Add(1340, 40, 460, 270)
        $ch = $co.Chart
        $ch.ChartType = 51
        while ($ch.SeriesCollection().Count -gt 0) { $ch.SeriesCollection(1).Delete() | Out-Null }
        foreach ($cp in @(@(3, "2023"), @(4, "2024"), @(5, "2025"))) {
            $c = $cp[0]
            $colL = [char](64 + $c)
            $s = $ch.SeriesCollection().NewSeries()
            $s.Values = $wsG.Range("$colL`47:$colL`50")
            $s.XValues = $wsG.Range("B47:B50")
            $s.Name = $cp[1]
        }
        $ch.HasTitle = $true
        $ch.ChartTitle.Text = "Gross margin by reporting line (materials-only, %)"
        $ch.ChartTitle.Font.Size = 12; $ch.ChartTitle.Font.Bold = $true
        $ch.ChartArea.Font.Name = $fontName; $ch.ChartArea.Font.Size = 10
        for ($i = 1; $i -le 3; $i++) { try { $ch.SeriesCollection($i).Format.Fill.ForeColor.RGB = $palette[$i - 1] } catch {} }
        try { $ch.Legend.Position = -4107 } catch {}
        try { $ch.Axes(2).TickLabels.NumberFormat = "0%" } catch {}
    }
    # export gm + quarterly
    for ($i = 1; $i -le $wsG.ChartObjects().Count; $i++) {
        $co = $wsG.ChartObjects($i)
        $t = try { $co.Chart.ChartTitle.Text } catch { "" }
        if ($t -like "Gross margin by reporting*") { $co.Activate() | Out-Null; Start-Sleep -m 300; $co.Chart.Export("$png\chart_gm.png", "PNG") | Out-Null; Write-Host "chart_gm exported" }
        if ($t -like "Quarterly revenue*") { $co.Activate() | Out-Null; Start-Sleep -m 300; $co.Chart.Export("$png\chart_quarterly.png", "PNG") | Out-Null; Write-Host "chart_quarterly exported" }
    }
    # print GM values for commentary grounding
    for ($r = 47; $r -le 50; $r++) {
        Write-Host "GM $($wsG.Cells.Item($r,2).Text): 2023=$($wsG.Cells.Item($r,3).Text) 2024=$($wsG.Cells.Item($r,4).Text) 2025=$($wsG.Cells.Item($r,5).Text)"
    }
    Start-Sleep -Seconds 1
    $wb.Save()
    $wb.Close($false)
} catch { Write-Host "ERROR: $_"; Write-Host $_.ScriptStackTrace }
finally { try { $excel.Quit() } catch {} }
