# Export v4 charts + key tables as PNGs for PPT insertion
$ErrorActionPreference = "Stop"
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
$png = "C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd\png"
New-Item -ItemType Directory -Force -Path $png | Out-Null
Get-Process excel -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
    $wb = $excel.Workbooks.Open("C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd\CDD_Databook_Mantis_v4.xlsx")
    $wsG = $wb.Sheets.Item("Charts")

    $map = @{
        "Revenue by reporting line" = "chart_segments.png"
        "Revenue by first-revenue cohort" = "chart_cohort.png"
        "Customer concentration 2025" = "chart_concentration.png"
        "Revenue by customer type" = "chart_type.png"
        "Revenue bridge 2024" = "chart_bridge.png"
        "Sales split 2025" = "chart_donut.png"
        "Revenue by nature" = "chart_nature.png"
    }
    for ($i = 1; $i -le $wsG.ChartObjects().Count; $i++) {
        $co = $wsG.ChartObjects($i)
        $t = try { $co.Chart.ChartTitle.Text } catch { "" }
        foreach ($k in $map.Keys) {
            if ($t -like "$k*") {
                $co.Activate() | Out-Null
                Start-Sleep -Milliseconds 300
                $co.Chart.Export("$png\$($map[$k])", "PNG") | Out-Null
                $size = (Get-Item "$png\$($map[$k])").Length
                Write-Host "exported $($map[$k]) ($size bytes)"
            }
        }
    }

    function Export-RangePic($ws, $rangeAddr, $file) {
        $rng = $ws.Range($rangeAddr)
        $w = $rng.Width; $h = $rng.Height
        $rng.CopyPicture(1, -4147) | Out-Null
        Start-Sleep -Milliseconds 700
        $tmp = $ws.ChartObjects().Add(5, 5, $w + 4, $h + 4)
        $tmp.Activate() | Out-Null
        $tmp.Chart.Paste() | Out-Null
        Start-Sleep -Milliseconds 400
        $tmp.Chart.Export("$png\$file", "PNG") | Out-Null
        $tmp.Delete() | Out-Null
        Write-Host "exported $file ($([int]$w)x$([int]$h))"
    }

    # buckets table on Customer Analysis: find 'Bucket' header in col B
    $wsC = $wb.Sheets.Item("Customer Analysis")
    $bktHdr = 0
    for ($r = 1; $r -le 100; $r++) { if ($wsC.Cells.Item($r, 2).Text -eq "Bucket") { $bktHdr = $r; break } }
    if ($bktHdr -gt 0) {
        # unbounded cap displays as dash instead of ###########
        $wsC.Cells.Item($bktHdr + 1, 4).NumberFormatLocal = "[>=9999999998]\-;#.##0"
        Export-RangePic $wsC "B$bktHdr`:G$($bktHdr + 6)" "table_buckets.png"
    }

    # retention table on Cohort Analysis: find 'Period' header in col B
    $wsK = $wb.Sheets.Item("Cohort Analysis")
    $retHdr = 0
    for ($r = 1; $r -le 100; $r++) { if ($wsK.Cells.Item($r, 2).Text -eq "Period") { $retHdr = $r; break } }
    if ($retHdr -gt 0) { Export-RangePic $wsK "B$retHdr`:H$($retHdr + 4)" "table_retention.png" }

    # churn-by-year table on Churn Analysis (header R11)
    $wsCh = $wb.Sheets.Item("Churn Analysis")
    Export-RangePic $wsCh "B11:G15" "table_churn.png"

    $wb.Close($false)
} catch {
    Write-Host "ERROR: $_"
    Write-Host $_.ScriptStackTrace
} finally { try { $excel.Quit() } catch {} }
