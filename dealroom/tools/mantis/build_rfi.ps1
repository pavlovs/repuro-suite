# MANTIS RFI Fragenliste v1 - German seller-facing question list + highlighted Kundendaten tab
# Output: 260610_Mantis_RFI_Fragenliste_v1.xlsx

$ErrorActionPreference = "Stop"
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
$tempDir = "C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd"
$outputPath = "$tempDir\260610_Mantis_RFI_Fragenliste_v1.xlsx"

Get-Process excel -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$tealBGR = 11702536
$bandBGR = 16181389
$accent3BGR = 4726241
$white = 16777215
$yellow = 10092543   # 99FFFF? -> BGR for FFFF99 light yellow: B=0x99,G=0xFF,R=0xFF = 0x99FFFF = 10092543
$fontName = "Aptos Narrow"

function Set-CellBase($cell) {
    $cell.Font.Name = $fontName
    $cell.Font.Size = 10
    $cell.VerticalAlignment = -4108
}
function New-Cell($ws, $r, $c, $v, $center) {
    $cell = $ws.Cells.Item($r, $c)
    $cell.Value2 = [string]$v
    Set-CellBase $cell
    if ($center) { $cell.HorizontalAlignment = -4108 }
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
function Add-TableBorders($ws, $r1, $c1, $r2, $c2) {
    $rng = $ws.Range($ws.Cells.Item($r1, $c1), $ws.Cells.Item($r2, $c2))
    $rng.Borders.LineStyle = 1
    $rng.Borders.Weight = 2
}

try {
    $wb = $excel.Workbooks.Add()
    while ($wb.Sheets.Count -gt 1) { $wb.Sheets.Item($wb.Sheets.Count).Delete() }
    $wsF = $wb.Sheets.Item(1)
    $wsF.Name = "Fragenliste"

    # ---- Kundendaten tab: native copy of seller file ----
    $wb2 = $excel.Workbooks.Open("$tempDir\file_1_3.xlsx")
    $wb2.Sheets.Item("Sheet1").Copy([System.Type]::Missing, $wb.Sheets.Item($wb.Sheets.Count))
    $wsK = $wb.Sheets.Item($wb.Sheets.Count)
    $wsK.Name = "Kundendaten"
    $wsK.UsedRange.Copy() | Out-Null
    $wsK.UsedRange.PasteSpecial(-4163) | Out-Null
    $wb2.Close($false)
    try { foreach ($l in @($wb.LinkSources(1))) { if ($l) { $wb.BreakLink($l, 1) } } } catch {}

    $wsK.Columns.Item(1).Insert() | Out-Null
    $wsK.Columns.Item(1).ColumnWidth = 3
    # B=Kunden C=2022 D=2023 E=2024 F=2025 G=2026 H=Gesamt I=Ranking
    $hdrRow = 0
    for ($r = 1; $r -le 10; $r++) { if ($wsK.Cells.Item($r, 2).Text -eq "Kunden") { $hdrRow = $r; break } }
    if ($hdrRow -eq 0) { throw "Kunden header not found" }
    $dataFirst = $hdrRow + 1
    $dataLast = $dataFirst - 1
    for ($r = $dataFirst; $r -le 1200; $r++) {
        $v = $wsK.Cells.Item($r, 2).Text
        if ($v -eq "" -or $v -like "Summen*" -or $v -like "Gesamtzahl*") { break }
        $dataLast = $r
    }
    $nCust = $dataLast - $dataFirst + 1
    Write-Host "  Kundendaten rows: $dataFirst..$dataLast ($nCust)"
    $wsK.Rows("$($dataLast + 1):1300").Delete() | Out-Null
    if ($hdrRow -gt 1) { $wsK.Rows("1:$($hdrRow - 1)").Delete() | Out-Null }
    $wsK.Range("J:R").Delete() | Out-Null
    $dcLast = 1 + $nCust

    # header restyle + Kommentar column
    New-HeaderRow $wsK 1 2 @("Kundentyp", "2022", "2023", "2024", "2025", "2026 YTD", "Gesamt", "Ranking", "Anmerkung")
    $ur = $wsK.Range("B2:J$dcLast")
    $ur.Font.Name = $fontName; $ur.Font.Size = 10

    # churn detection + yellow highlight: >10k in 2023 OR 2024, zero in 2025 AND 2026
    $churned = 0
    for ($r = 2; $r -le $dcLast; $r++) {
        $v23 = $wsK.Cells.Item($r, 4).Value2; if ($v23 -isnot [double]) { $v23 = 0 }
        $v24 = $wsK.Cells.Item($r, 5).Value2; if ($v24 -isnot [double]) { $v24 = 0 }
        $v25 = $wsK.Cells.Item($r, 6).Value2; if ($v25 -isnot [double]) { $v25 = 0 }
        $v26 = $wsK.Cells.Item($r, 7).Value2; if ($v26 -isnot [double]) { $v26 = 0 }
        if (($v23 -gt 10000 -or $v24 -gt 10000) -and $v25 -le 0 -and $v26 -le 0) {
            $wsK.Range($wsK.Cells.Item($r, 2), $wsK.Cells.Item($r, 10)).Interior.Color = $yellow
            $cell = $wsK.Cells.Item($r, 10)
            $cell.Value2 = [string]"Bitte Abgang erl" + [char]0x00E4 + "utern (Frage 1)"
            Set-CellBase $cell
            $churned++
        }
    }
    Write-Host "  churned customers highlighted: $churned"
    $wsK.Columns.Item(2).ColumnWidth = 22
    for ($c = 3; $c -le 9; $c++) { $wsK.Columns.Item($c).ColumnWidth = 13 }
    $wsK.Columns.Item(10).ColumnWidth = 34
    Add-TableBorders $wsK 1 2 $dcLast 10

    # ---- Fragenliste tab ----
    # NOTE: PS variables are case-insensitive - never define $AE next to $ae
    $ae = [char]0x00E4; $oe = [char]0x00F6; $ue = [char]0x00FC; $sz = [char]0x00DF
    $bigUE = [char]0x00DC
    $eur = [char]0x20AC

    $wsF.Columns.Item(1).ColumnWidth = 3
    $title = $wsF.Cells.Item(2, 2)
    $title.Value2 = [string]("Endoberatung GmbH " + [char]0x2013 + " Fragenliste zur Datenanalyse " + [char]0x2013 + " Stand 10.06.2026")
    $title.Font.Name = $fontName; $title.Font.Size = 13; $title.Font.Bold = $true
    New-Cell $wsF 3 2 ("Bezug: bereitgestellte Unterlagen im Datenraum (Ordner 01 Umsatz und Kunden, 04 Finanzen). Gelb markierte Kunden im Tab 'Kundendaten' beziehen sich auf Frage 1.") $false

    $hdr = 5
    $hPrio = "Priorit" + $ae + "t"
    $hAntw = "Antwort Verk" + $ae + "ufer"
    New-HeaderRow $wsF $hdr 2 @("Nr.", "Quelldokument", "Frage", $hPrio, $hAntw)
    $r = $hdr + 1
    $qs = @(
        @{ S = "1.3 Kundenliste (Ums" + $ae + "tze gesamt seit 2022)"; Q = "Im Tab 'Kundendaten' sind Kunden gelb markiert, die 2023 oder 2024 mehr als 10 T$eur Umsatz hatten und in 2025 sowie bis Mai 2026 keinen Umsatz mehr aufweisen. Bitte erl" + $ae + "utern Sie je Kunde den Grund des Abgangs (z. B. Preis, Wettbewerb, Insolvenz, Eigenaufbereitung, Standortschlie" + $sz + "ung)."; P = "Hoch" },
        @{ S = "4.1 GuV 2025 (EBIT-Nebenrechnung)"; Q = "Bitte Nachweise zu den Pro-Forma-Anpassungen 2025: 120 T$eur Umsatzverschiebung nach 2026, 28 T$eur Bestandskorrektur (Konto 3400), 80 T$eur Aufbereitungskosten Olympus."; P = "Hoch" },
        @{ S = "4.1 GuV 2024/2025 (EBIT-Nebenrechnung)"; Q = "Das EBIT sank 2025 deutlich gegen" + $ue + "ber 2024. Bitte (a) die Herleitung der Gehaltsanpassung Gesch" + $ae + "ftsf" + $ue + "hrung (384 T$eur auf 140 T$eur zzgl. 18% Nebenkosten) erl" + $ae + "utern und (b) eine EBIT-" + $bigUE + "berleitung 2024 auf 2025 nach wesentlichen Kostenarten bereitstellen."; P = "Hoch" },
        @{ S = "4.1 Jahresabschl" + $ue + "sse"; Q = "Die GuV 2025 ist vorl" + $ae + "ufig (bis Periode 16). Wann liegt der finale Jahresabschluss 2025 vor? Bitte zus" + $ae + "tzlich SuSa 2023-2025 und aktuelle BWA 2026 bereitstellen."; P = "Hoch" },
        @{ S = "1.3 Kundenliste"; Q = "Der Umsatz im Krankenhaus-Segment stieg 2024 von 983 T$eur auf 1.721 T$eur und fiel 2025 auf 1.377 T$eur zur" + $ue + "ck. Was war der Treiber (Preis, Volumen, Einmalprojekt)?"; P = "Hoch" },
        @{ S = "1.1 Umsatzaufstellung"; Q = "Der Umsatz im Mobilen Kundendienst ging 2025 um ca. -24% zur" + $ue + "ck (378 T$eur auf 286 T$eur). Ist der R" + $ue + "ckgang strukturell oder tempor" + $ae + "r?"; P = "Hoch" },
        @{ S = "1.1 Umsatzaufstellung / 1.4 Servicevertr" + $ae + "ge"; Q = "Die Vertragsrechnung w" + $ae + "chst stetig (+17% in 2024, +7% in 2025). Bitte " + $bigUE + "bersicht der Servicevertr" + $ae + "ge (falls verf" + $ue + "gbar): Laufzeiten, K" + $ue + "ndigungsfristen, Verl" + $ae + "ngerungsquoten."; P = "Hoch" },
        @{ S = "1.1 Umsatzaufstellung"; Q = "Bei der Vertragsrechnung liegt der ausgewiesene Rohertrag bei 100-108% des Umsatzes; 36 Rechnungen zeigen negativen Rohertrag. Bitte die Berechnungsbasis des Felds 'Rohertrag' erl" + $ae + "utern (nur Materialeinsatz?)."; P = "Mittel" },
        @{ S = "1.3 Kundenliste"; Q = "Der H" + $ae + "ndler-Umsatz schwankt stark (573 T$eur / 364 T$eur / 929 T$eur in 2023-2025). Handelt es sich um Projektgesch" + $ae + "ft? Wer sind die gr" + $oe + $sz + "ten H" + $ae + "ndler, bestehen Rahmenvertr" + $ae + "ge?"; P = "Mittel" },
        @{ S = "1.1 / 1.3"; Q = "Die Summen aus Rechnungsdaten (1.1) und Kundenliste (1.3) weichen um 12-23 T$eur p.a. (<2%) voneinander ab. Bitte kurz best" + $ae + "tigen: Gutschriften / Periodenabgrenzung?"; P = "Niedrig" }
    )
    $i = 1
    foreach ($q in $qs) {
        New-Cell $wsF $r 2 "$i" $true
        New-Cell $wsF $r 3 ([string]$q.S) $false
        New-Cell $wsF $r 4 ([string]$q.Q) $false
        New-Cell $wsF $r 5 ([string]$q.P) $true
        New-Cell $wsF $r 6 "" $false
        $wsF.Cells.Item($r, 3).WrapText = $true
        $wsF.Cells.Item($r, 4).WrapText = $true
        if ($q.P -eq "Hoch") { $wsF.Cells.Item($r, 5).Font.Color = $accent3BGR; $wsF.Cells.Item($r, 5).Font.Bold = $true }
        $i++; $r++
    }
    Add-TableBorders $wsF $hdr 2 ($r - 1) 6
    $wsF.Columns.Item(2).ColumnWidth = 5
    $wsF.Columns.Item(3).ColumnWidth = 30
    $wsF.Columns.Item(4).ColumnWidth = 80
    $wsF.Columns.Item(5).ColumnWidth = 10
    $wsF.Columns.Item(6).ColumnWidth = 55
    $wsF.Rows.Item($hdr).RowHeight = 18

    foreach ($ws in $wb.Sheets) {
        $ws.Activate()
        $excel.ActiveWindow.DisplayGridlines = $false
    }
    $wb.Sheets.Item("Fragenliste").Activate()

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
