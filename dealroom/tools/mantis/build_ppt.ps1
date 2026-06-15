# Build Mantis CDD PPT v2 draft - full commercial section redesign (S11-S21), answer-first titles
$ErrorActionPreference = "Stop"
[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::GetCultureInfo("en-US")
Add-Type -AssemblyName System.Drawing
$tempDir = "C:\Users\X1\Documents\CLAUDE_COWORK\temp_dd"
$png = "$tempDir\png"
$outPath = "$tempDir\260610_Mantis_CDD_v2_draft.pptx"
Copy-Item "$tempDir\strawman.pptx" $outPath -Force
$eur = [char]0x20AC

Get-Process powerpnt -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$ppt = New-Object -ComObject PowerPoint.Application
try {
    $pres = $ppt.Presentations.Open($outPath, $false, $false, $false)

    function Remove-Dummies($slide, $x1, $y1, $x2, $y2) {
        $del = @()
        foreach ($shape in $slide.Shapes) {
            $name = $shape.Name
            if ($name -like "think-cell*" -or $name -like "Title*" -or $name -like "Slide Number*" -or $name -like "Content Placeholder*") { continue }
            $isYellow = $false
            try {
                if ($shape.Fill.Visible -eq -1) {
                    $rgb = $shape.Fill.ForeColor.RGB
                    $b = [Math]::Floor($rgb / 65536); $g = [Math]::Floor(($rgb % 65536) / 256); $rr = $rgb % 256
                    if ($rr -gt 200 -and $g -gt 180 -and $b -lt 160) { $isYellow = $true }
                }
            } catch {}
            $cx = $shape.Left + $shape.Width / 2
            $cy = $shape.Top + $shape.Height / 2
            $inRegion = ($x2 -gt $x1) -and ($cx -ge $x1) -and ($cx -le $x2) -and ($cy -ge $y1) -and ($cy -le $y2)
            $offSlide = ($shape.Left + $shape.Width) -lt 5
            if ($isYellow -or $inRegion -or $offSlide) { $del += $shape }
        }
        foreach ($s in $del) { try { $s.Delete() } catch {} }
        return $del.Count
    }

    # aspect-preserving picture insert, centered in target box
    function Add-Pic($slide, $file, $x, $y, $maxW, $maxH) {
        $img = [System.Drawing.Image]::FromFile("$png\$file")
        $ar = $img.Width / $img.Height
        $img.Dispose()
        $w = [single]$maxW; $h = [single]($w / $ar)
        if ($h -gt $maxH) { $h = [single]$maxH; $w = [single]($h * $ar) }
        $px = [single]($x + ($maxW - $w) / 2)
        $py = [single]($y + ($maxH - $h) / 2)
        $p = $slide.Shapes.AddPicture("$png\$file", 0, -1, $px, $py, $w, $h)
        try { $p.LockAspectRatio = 0 } catch {}
        $p.Left = $px; $p.Top = $py; $p.Width = $w; $p.Height = $h
        return $p
    }

    function Add-Note($slide, $x, $y, $w, $h, $title, $lines, $fillRgb) {
        $box = $slide.Shapes.AddShape(1, $x, $y, $w, $h)
        $box.Fill.ForeColor.RGB = $fillRgb
        $box.Line.Visible = 0
        $tf = $box.TextFrame.TextRange
        $txt = $title
        foreach ($l in $lines) { $txt += "`r" + $l }
        $tf.Text = $txt
        $tf.Font.Name = "Arial"; $tf.Font.Size = 10
        $tf.Font.Color.RGB = 3355443
        $tf.ParagraphFormat.Alignment = 1
        $tf.Paragraphs(1).Font.Bold = $true
        $box.TextFrame.WordWrap = -1
        try { $box.TextFrame.VerticalAnchor = 1 } catch {}
        return $box
    }

    function Set-Comments($slide, $lines) {
        foreach ($shape in $slide.Shapes) {
            if ($shape.Name -like "Google Shape*" -and $shape.Left -gt 600 -and $shape.HasTextFrame -eq -1) {
                $shape.TextFrame.TextRange.Text = ($lines -join "`r")
                $shape.TextFrame.TextRange.Font.Size = 10
                $shape.TextFrame.TextRange.Font.Name = "Arial"
                return $true
            }
        }
        return $false
    }

    function Set-TextByMatch($slide, $match, $newText) {
        foreach ($shape in $slide.Shapes) {
            try {
                if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1 -and $shape.TextFrame.TextRange.Text.Contains($match)) {
                    $shape.TextFrame.TextRange.Text = $newText
                    return $true
                }
            } catch {}
        }
        return $false
    }

    function Set-SlideTitle($slide, $text) {
        try { $slide.Shapes.Title.TextFrame.TextRange.Text = $text } catch {}
    }

    # ===== S11: company / sales split + business-segment table =====
    $s = $pres.Slides.Item(11)
    $n = Remove-Dummies $s 15 130 235 455
    Add-Pic $s "chart_donut.png" 26 140 200 290 | Out-Null
    Set-TextByMatch $s "Sales split 2025" "Sales split 2025 (in EUR k)" | Out-Null
    Set-TextByMatch $s "differentiates itself" "[Target] is a specialized endoscopy repair, service and trading partner - 17% of sales is contract-billed (Vertragsrechnung) and growing" | Out-Null
    Set-SlideTitle $s "[Target] is a specialized endoscopy repair and service provider with c. 3.2 M$eur revenue"
    # rewrite the business-segment table (template content from another company)
    foreach ($shape in $s.Shapes) {
        if ($shape.HasTable -eq -1) {
            $tbl = $shape.Table
            $rows = @(
                @("Vertrieb", "Sale of endoscopes, equipment and accessories (incl. refurbished units)", "Single orders, partly project-driven", "34% of 2025 sales"),
                @("Endoskop-Reparatur", "Repair of flexible and rigid endoscopes in own workshop", "Re-occurring via device damage and wear cycles", "31% of 2025 sales"),
                @("Vertragsrechnung", "Maintenance and service contracts with fixed terms", "Recurring, contract-based - only consistent grower", "17% of 2025 sales"),
                @("Other services", "Mobile field service, replacement units, peripherals, training", "Mixed; partly project-driven", "18% of 2025 sales")
            )
            for ($r = 0; $r -lt 4; $r++) {
                for ($c = 0; $c -lt 4; $c++) {
                    try {
                        $cellTf = $tbl.Cell($r + 2, $c + 1).Shape.TextFrame.TextRange
                        $cellTf.Text = $rows[$r][$c]
                    } catch {}
                }
            }
        }
    }
    Add-Note $s 259 432 674 28 "" @("Note: segment definitions reconstructed from invoice data (RepArt field) - to be confirmed with management") 16777215 | Out-Null
    Write-Host "S11 done ($n del)"

    # ===== S12: revenue quality =====
    $s = $pres.Slides.Item(12)
    $n = Remove-Dummies $s 15 130 235 455
    Set-TextByMatch $s "Sales split 2025" "Revenue by nature (2023-2025)" | Out-Null
    Add-Pic $s "chart_nature.png" 26 140 430 280 | Out-Null
    Add-Note $s 480 140 455 280 "Revenue quality" @(
        "- Contracted (Vertragsrechnung): 17% of 2025 revenue, growing +17% / +7% - the only consistent grower",
        "- Repeat, lifecycle-driven repairs (Endoskop-Reparatur, field service, replacements): c. 49%",
        "- Product sales (Vertrieb): 34% - transactional, partly project-driven",
        "- No order book: repair and service work is billed on completion; backlog metrics are not meaningful for this model",
        "- Contract terms, durations and renewal rates requested from seller (RFI Q7)") 15921906 | Out-Null
    Set-TextByMatch $s "differentiates itself" "Revenue quality: 17% contracted, c. 49% repeat lifecycle-driven repair work, 34% product sales" | Out-Null
    Set-SlideTitle $s "Two-thirds of revenue is repeat business - 17% contracted, c. 49% repair cycles"
    Write-Host "S12 done ($n del)"

    # ===== S13: growth =====
    $s = $pres.Slides.Item(13)
    $n = Remove-Dummies $s 15 130 235 455
    Set-TextByMatch $s "Sales split 2025" "Revenue by reporting line (EUR k)" | Out-Null
    Add-Pic $s "chart_segments.png" 29 136 429 280 | Out-Null
    Add-Note $s 502 136 433 280 "Growth assessment" @(
        "- Growth stalled: +11.4% (2024), +2.0% (2025); 2026 YTD (May) runs c. 10% below the 2025 average monthly pace",
        "- Vertrieb rebounded +37% in 2025 after a weak 2024; repair lines declined",
        "- Hospital-type revenue spiked in 2024 and normalized (983k -> 1,721k -> 1,377k) - inflates the 2024 base",
        "- Price vs volume split not derivable from invoice data - requested from management (RFI)") 15921906 | Out-Null
    Set-TextByMatch $s "differentiates itself" "Revenue growth has stalled in 2025 - the EBIT bridge, not the top line, is the core DD question" | Out-Null
    Set-SlideTitle $s "Growth stalled in 2025 - the 2024 jump was hospital-driven"
    Write-Host "S13 done ($n del)"

    # ===== S14: gross margin by line (replaces template product-category scatter) =====
    $s = $pres.Slides.Item(14)
    $n = Remove-Dummies $s 20 130 940 485
    Set-TextByMatch $s "sales (x-axis) and gross margin" "Gross margin by reporting line (2023-2025; Rohertrag = materials-only margin)" | Out-Null
    Add-Pic $s "chart_gm.png" 26 140 560 300 | Out-Null
    Add-Note $s 620 140 313 300 "Caveats" @(
        "- Reported Vertrieb Rohertrag fell sharply: 75% (2023) -> 47% (2024) -> 31% (2025) - proxy metric; mix shift, pricing or booking change? Management question",
        "- Repair margin improving: 62% -> 73%",
        "- Vertragsrechnung shows GM of 100-108%: no material cost booked on contract invoices - Rohertrag basis to be validated (RFI Q8)",
        "- These are contribution margins (materials-only); labor is not allocated per line") 15921906 | Out-Null
    foreach ($shape in $s.Shapes) {
        if ($shape.Name -like "Content Placeholder*" -and $shape.Top -gt 500 -and $shape.HasTextFrame -eq -1) {
            try { $shape.TextFrame.TextRange.Text = "Source: seller invoice data (file 1.1, 3,015 invoices); GM = Rohertrag / net revenue" } catch {}
        }
    }
    Set-SlideTitle $s "Materials-only repair margins are rising; reported Vertrieb margin fell sharply - basis to be validated"
    Write-Host "S14 done ($n del)"

    # ===== S15: quarterly revenue (replaces template product-category margin lines) =====
    $s = $pres.Slides.Item(15)
    $n = Remove-Dummies $s 20 130 940 510
    Set-TextByMatch $s "Gross margin by product category" "Quarterly revenue (EUR k, from invoice dates)" | Out-Null
    Add-Pic $s "chart_quarterly.png" 26 140 575 300 | Out-Null
    Add-Note $s 645 140 288 300 "Comments" @(
        "- Built from 3,015 invoice dates - live in the databook",
        "- 2026 YTD (May): 1,180k, c. 10% below the 2025 average monthly pace",
        "- Relevant for validating the seller's 120k year-end revenue shift into 2026 (EBIT bridge)") 15921906 | Out-Null
    foreach ($shape in $s.Shapes) {
        if ($shape.Name -like "Content Placeholder*" -and $shape.Top -gt 500 -and $shape.HasTextFrame -eq -1) {
            try { $shape.TextFrame.TextRange.Text = "Source: seller invoice data (file 1.1); calendar quarters" } catch {}
        }
    }
    Set-SlideTitle $s "No obvious quarterly cliffs through 2025 - but 2026 starts c. 10% softer"
    Write-Host "S15 done ($n del)"

    # ===== S16: customer types =====
    $s = $pres.Slides.Item(16)
    $n = Remove-Dummies $s 0 0 0 0
    Add-Pic $s "chart_type.png" 224 170 506 260 | Out-Null
    Set-SlideTitle $s "Customer mix is hospital-led; the dealer channel adds volatility"
    Write-Host "S16 done ($n del)"

    # ===== S17: concentration =====
    $s = $pres.Slides.Item(17)
    $n = Remove-Dummies $s 15 130 620 500
    Add-Pic $s "chart_concentration.png" 22 140 300 310 | Out-Null
    Add-Pic $s "table_buckets.png" 330 150 280 110 | Out-Null
    Add-Note $s 330 280 280 160 "Reading" @(
        "- 185 customers invoiced since 2022; 100 in 2025",
        "- Buckets on cumulative 2022-2026 revenue",
        "- Top-account contract terms requested under NDA (RFI)") 15921906 | Out-Null
    Set-Comments $s @(
        "Concentration is meaningful: Top 3 = 27%, Top 10 = 55%, Top 20 = 71% of 2025 revenue",
        "100 customers invoiced in 2025 (185 since 2022)",
        "Hospital-led base; dealer accounts are large but volatile",
        "Top-customer identity and contract exposure requested under NDA (RFI)") | Out-Null
    Set-SlideTitle $s "[Target] has a broad customer base - but Top 20 carry c. 71% of revenue"
    Write-Host "S17 done ($n del)"

    # ===== S18: cohorts =====
    $s = $pres.Slides.Item(18)
    $n = Remove-Dummies $s 15 130 620 500
    Add-Pic $s "chart_cohort.png" 19 145 580 300 | Out-Null
    Set-TextByMatch $s "Customer overview (sales by cohort" "Customer overview (sales by first-revenue cohort, in EUR k)" | Out-Null
    Set-Comments $s @(
        "c. 94% of 2025 revenue from customers already active before 2025",
        "Pre-2022 customer stock dominates - the installed base is the asset",
        "2023+ cohorts are small and decay (2023 cohort: 682k -> 780k -> 514k)",
        "Existing-base share does not imply low churn - see next slides") | Out-Null
    Set-SlideTitle $s "94% of 2025 revenue comes from existing customers - the installed base is the asset"
    Write-Host "S18 done ($n del)"

    # ===== S19: retention & churn rates =====
    $s = $pres.Slides.Item(19)
    $n = Remove-Dummies $s 15 130 620 500
    Add-Pic $s "table_retention.png" 22 160 580 95 | Out-Null
    Add-Pic $s "table_churn.png" 22 290 580 95 | Out-Null
    Set-TextByMatch $s "Customer overview" "Retention and churn (EUR k)" | Out-Null
    Set-Comments $s @(
        "NRR 90-102% and logo retention 67-79% in full-year pairs",
        "2024->25: 29 customers churned carrying 294k prior-year revenue (9.4%)",
        "Churn is invoicing-based - repair cycles can look like churn; reasons requested (RFI Q1)",
        "Early-warning: 35 customers without 2026 invoices yet carried 566k of 2025 revenue (partial-year view)") | Out-Null
    Set-SlideTitle $s "Existing-customer revenue is material - but logo churn runs at 21-33% p.a."
    Write-Host "S19 done ($n del)"

    # ===== S20: revenue bridge =====
    $s = $pres.Slides.Item(20)
    $n = Remove-Dummies $s 15 130 620 500
    Add-Pic $s "chart_bridge.png" 22 140 580 310 | Out-Null
    Set-TextByMatch $s "Customer overview" "Revenue bridge 2024 -> 2025 (EUR k)" | Out-Null
    Set-Comments $s @(
        "Start 3,118k - churned (294k) +/- net retained +115k + new/reactivated +233k = 3,176k",
        "Net growth fell from +312k (2023->24) to +58k (2024->25)",
        "New business no longer outruns churn and contraction - the growth engine question for management",
        "Churned >10k accounts highlighted in the RFI annex (Q1)") | Out-Null
    Set-SlideTitle $s "Churn and contraction absorb most new business - net growth fell to +58k in 2025"
    Write-Host "S20 done ($n del)"

    # ===== S21: customer satisfaction - not assessed =====
    $s = $pres.Slides.Item(21)
    $del = @()
    foreach ($shape in $s.Shapes) {
        if ($shape.Type -eq 13 -and $shape.Width -gt 400) { $del += $shape }
        try {
            if ($shape.Fill.Visible -eq -1) {
                $rgb = $shape.Fill.ForeColor.RGB
                $b = [Math]::Floor($rgb / 65536); $g = [Math]::Floor(($rgb % 65536) / 256); $rr = $rgb % 256
                if ($rr -gt 200 -and $g -gt 180 -and $b -lt 160) { $del += $shape }
            }
        } catch {}
    }
    foreach ($d in $del) { try { $d.Delete() } catch {} }
    Add-Note $s 26 200 905 120 "Not assessed" @(
        "- No customer satisfaction or NPS data in the data room; no survey planned at this stage",
        "- Proxy evidence: retention and cohort analyses (previous slides); churn reasons requested from seller (RFI Q1)") 15921906 | Out-Null
    Set-SlideTitle $s "Customer satisfaction - not assessed (no data available)"
    Write-Host "S21 done"

    # pre-save picture audit
    foreach ($idx in @(11, 12, 13, 14, 15, 16, 17, 18, 19, 20)) {
        $cnt = 0
        foreach ($shape in $pres.Slides.Item($idx).Shapes) { if ($shape.Type -eq 13) { $cnt++ } }
        Write-Host "  S$idx pictures: $cnt"
    }
    $pres.SaveAs($outPath) | Out-Null
    foreach ($idx in @(11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)) {
        $pres.Slides.Item($idx).Export("$png\slide_$idx.png", "PNG", 1280, 720) | Out-Null
    }
    $pres.Close()
    Write-Host "DONE: $outPath"
} catch {
    Write-Host "ERROR: $_"
    Write-Host $_.ScriptStackTrace
} finally {
    try { $ppt.Quit() } catch {}
}
