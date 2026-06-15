/**
 * DR-M13 — Cross-Deal Benchmarking
 * Wireframe render function for the DEALROOM portfolio dashboard.
 * [Wireframe — mock data]
 *
 * Usage: renderBenchmark() → returns self-contained HTML string.
 * Drop into the portfolio view alongside other dashboard sections.
 */

function renderBenchmark() {
  // ─── Mock data ───────────────────────────────────────────────────────────────
  const deals = ['Cat', 'Lion', 'Fox', 'Wolf', 'Mouse'];

  const financial = {
    headers: ['Metric', ...deals, 'Avg'],
    rows: [
      {
        label: 'Revenue M€',
        values: [6.2, 8.5, 4.1, 3.8, 2.9],
        avg: 5.1,
        fmt: 'M€',
        higherIsBetter: true,
      },
      {
        label: 'Rev CAGR 22–25',
        values: [8.2, 12.1, 5.3, 3.1, 15.2],
        avg: 8.8,
        fmt: '%',
        higherIsBetter: true,
      },
      {
        label: 'Gross margin',
        values: [42, 38, 45, 35, 48],
        avg: 41.6,
        fmt: '%',
        higherIsBetter: true,
      },
      {
        label: 'EBITDA adj. K€',
        values: [820, 1050, 480, 350, 410],
        avg: 622,
        fmt: 'K€',
        higherIsBetter: true,
      },
      {
        label: 'EBITDA margin',
        values: [13.2, 12.4, 11.7, 9.2, 14.1],
        avg: 12.1,
        fmt: '%',
        higherIsBetter: true,
      },
      {
        label: 'PEX % of rev',
        values: [22, 25, 18, 28, 20],
        avg: 22.6,
        fmt: '%',
        higherIsBetter: false,
      },
    ],
  };

  const commercial = {
    headers: ['Metric', ...deals, 'Avg'],
    rows: [
      {
        label: 'Recurring %',
        values: [45, 35, 55, 25, 40],
        avg: 40,
        fmt: '%',
        higherIsBetter: true,
      },
      {
        label: 'Top-3 conc.',
        values: [38, 42, 28, 55, 35],
        avg: 39.6,
        fmt: '%',
        higherIsBetter: false,
      },
      {
        label: '# Customers',
        values: [180, 120, 250, 85, 95],
        avg: 146,
        fmt: 'n',
        higherIsBetter: true,
      },
    ],
  };

  const valuation = [
    { deal: 'Cat',       ev: 6.6, multiple: '5.5x', stage: 'offer_negotiation',  days: 45 },
    { deal: 'Lion',      ev: 9.2, multiple: '5.8x', stage: 'offer_negotiation',  days: 32 },
    { deal: 'Fox',       ev: 4.8, multiple: '5.2x', stage: 'offer_preparation',  days: 28 },
    { deal: 'Wolf',      ev: 3.5, multiple: '5.0x', stage: 'offer_negotiation',  days: 51 },
    { deal: 'Mouse',     ev: 3.1, multiple: '4.8x', stage: 'financials_recv',    days: 18 },
  ];
  const valuationAvg = {
    ev: (valuation.reduce((s, d) => s + d.ev, 0) / valuation.length).toFixed(1),
    multiple: '5.3x',
    days: (valuation.reduce((s, d) => s + d.days, 0) / valuation.length).toFixed(1),
  };

  // ─── Helpers ─────────────────────────────────────────────────────────────────

  /** German number formatting */
  function fmtDE(val, fmt) {
    if (fmt === '%') return val.toFixed(1).replace('.', ',') + '%';
    if (fmt === 'M€') return val.toFixed(1).replace('.', ',');
    if (fmt === 'K€') return val.toLocaleString('de-DE');
    return val.toString();
  }

  /** Quartile color coding — best 25% → green, worst 25% → red */
  function quartileColor(val, values, higherIsBetter) {
    const sorted = [...values].sort((a, b) => a - b);
    const q1 = sorted[Math.floor(sorted.length * 0.25)];
    const q3 = sorted[Math.floor(sorted.length * 0.75)];
    if (higherIsBetter) {
      if (val >= q3) return 'background:#dcfce7;';
      if (val <= q1) return 'background:#fee2e2;';
    } else {
      if (val <= q1) return 'background:#dcfce7;';
      if (val >= q3) return 'background:#fee2e2;';
    }
    return '';
  }

  /** Stage badge */
  function stageBadge(stage) {
    const map = {
      offer_negotiation:  { label: 'Offer negotiation',  color: '#fef9c3', border: '#ca8a04' },
      offer_preparation:  { label: 'Offer preparation',  color: '#dbeafe', border: '#2563eb' },
      financials_recv:    { label: 'Financials received', color: '#f3e8ff', border: '#9333ea' },
    };
    const s = map[stage] || { label: stage, color: '#f1f5f9', border: '#64748b' };
    return `<span style="background:${s.color};border:1px solid ${s.border};border-radius:4px;
      padding:1px 6px;font-size:11px;color:#1e293b;">${s.label}</span>`;
  }

  /** Days-in-stage color: >45 red, 20-45 yellow, <20 green */
  function daysColor(days) {
    if (days > 45) return 'color:#dc2626;font-weight:600;';
    if (days > 20) return 'color:#d97706;';
    return 'color:#16a34a;';
  }

  // ─── Sub-section renderers ────────────────────────────────────────────────────

  function renderMetricTable(section) {
    const colW = `width:${Math.floor(72 / deals.length)}%`;
    const headerCells = section.headers.map((h, i) =>
      `<th style="padding:8px 10px;text-align:${i === 0 ? 'left' : 'right'};
        background:#f8fafc;font-weight:600;font-size:12px;color:#374151;
        border-bottom:2px solid #e2e8f0;${i > 0 ? colW : 'width:22%'};">${h}</th>`
    ).join('');

    const dataRows = section.rows.map(row => {
      const dataCells = row.values.map((val, i) => {
        const style = quartileColor(val, row.values, row.higherIsBetter);
        return `<td style="padding:7px 10px;text-align:right;font-size:13px;
          border-bottom:1px solid #f1f5f9;${style}font-variant-numeric:tabular-nums;">
          ${fmtDE(val, row.fmt)}</td>`;
      }).join('');

      const avgCell = `<td style="padding:7px 10px;text-align:right;font-size:13px;
        font-weight:600;color:#374151;border-bottom:1px solid #f1f5f9;
        background:#f8fafc;font-variant-numeric:tabular-nums;">
        ${fmtDE(row.avg, row.fmt)}</td>`;

      return `<tr>
        <td style="padding:7px 10px;font-size:13px;color:#374151;
          border-bottom:1px solid #f1f5f9;font-weight:500;">${row.label}</td>
        ${dataCells}${avgCell}
      </tr>`;
    }).join('');

    return `<table style="width:100%;border-collapse:collapse;font-family:inherit;">
      <thead><tr>${headerCells}</tr></thead>
      <tbody>${dataRows}</tbody>
    </table>`;
  }

  function renderValuationTable() {
    const rows = valuation.map(d => {
      const evStyle = d.ev >= 8 ? 'color:#16a34a;font-weight:600;' :
                      d.ev <= 3.5 ? 'color:#6b7280;' : '';
      return `<tr>
        <td style="padding:8px 10px;font-size:13px;font-weight:600;color:#0891B2;
          border-bottom:1px solid #f1f5f9;">${d.deal}</td>
        <td style="padding:8px 10px;font-size:13px;text-align:right;${evStyle}
          border-bottom:1px solid #f1f5f9;">${d.ev.toFixed(1).replace('.', ',')}</td>
        <td style="padding:8px 10px;font-size:13px;text-align:right;
          border-bottom:1px solid #f1f5f9;">${d.multiple}</td>
        <td style="padding:8px 10px;font-size:13px;border-bottom:1px solid #f1f5f9;">
          ${stageBadge(d.stage)}</td>
        <td style="padding:8px 10px;font-size:13px;text-align:right;
          border-bottom:1px solid #f1f5f9;${daysColor(d.days)}">${d.days}</td>
      </tr>`;
    }).join('');

    const avgRow = `<tr style="background:#f8fafc;">
      <td style="padding:8px 10px;font-size:13px;font-weight:600;color:#374151;">Avg</td>
      <td style="padding:8px 10px;font-size:13px;text-align:right;font-weight:600;">
        ${valuationAvg.ev.replace('.', ',')}</td>
      <td style="padding:8px 10px;font-size:13px;text-align:right;font-weight:600;">
        ${valuationAvg.multiple}</td>
      <td style="padding:8px 10px;font-size:13px;color:#6c757d;">—</td>
      <td style="padding:8px 10px;font-size:13px;text-align:right;font-weight:600;">
        ${valuationAvg.days.replace('.', ',')}</td>
    </tr>`;

    const headers = ['Deal', 'EV M€', 'Multiple', 'Stage', 'Days in stage'].map((h, i) =>
      `<th style="padding:8px 10px;text-align:${i > 0 && i < 3 ? 'right' : 'left'};
        background:#f8fafc;font-weight:600;font-size:12px;color:#374151;
        border-bottom:2px solid #e2e8f0;">${h}</th>`
    ).join('');

    return `<table style="width:100%;border-collapse:collapse;font-family:inherit;">
      <thead><tr>${headers}</tr></thead>
      <tbody>${rows}${avgRow}</tbody>
    </table>`;
  }

  function renderSpiderPlaceholder() {
    return `<div style="display:flex;align-items:center;justify-content:center;
      height:180px;background:#f8fafc;border:2px dashed #cbd5e1;border-radius:8px;">
      <div style="text-align:center;color:#6c757d;">
        <div style="font-size:28px;margin-bottom:8px;">◎</div>
        <div style="font-size:13px;font-weight:600;color:#374151;margin-bottom:4px;">
          Spider Chart — Deal vs. Portfolio Average</div>
        <div style="font-size:12px;max-width:340px;line-height:1.5;">
          5-axis radar: Revenue growth · EBITDA margin · Recurring % · Size · Customer quality<br>
          Select a deal from the filter to overlay it against the portfolio average.
        </div>
        <div style="margin-top:10px;font-size:11px;color:#94a3b8;font-style:italic;">
          [Placeholder — chart.js radar implementation in final version]
        </div>
      </div>
    </div>`;
  }

  // ─── Legend ───────────────────────────────────────────────────────────────────

  const legend = `<div style="display:flex;align-items:center;gap:16px;
    font-size:11px;color:#6c757d;margin-bottom:4px;">
    <span>Color coding:</span>
    <span><span style="display:inline-block;width:12px;height:12px;background:#dcfce7;
      border:1px solid #86efac;border-radius:2px;vertical-align:middle;margin-right:4px;"></span>
      Best quartile</span>
    <span><span style="display:inline-block;width:12px;height:12px;background:#fee2e2;
      border:1px solid #fca5a5;border-radius:2px;vertical-align:middle;margin-right:4px;"></span>
      Worst quartile</span>
    <span style="margin-left:auto;background:#fef3c7;border:1px solid #f59e0b;
      border-radius:4px;padding:1px 8px;color:#92400e;font-weight:600;">
      Wireframe — mock data</span>
  </div>`;

  // ─── Section wrapper ──────────────────────────────────────────────────────────

  function section(title, content) {
    return `<div style="margin-bottom:20px;">
      <div style="font-size:11px;font-weight:700;letter-spacing:0.08em;
        color:#0891B2;text-transform:uppercase;margin-bottom:10px;
        padding-bottom:6px;border-bottom:1px solid #e2e8f0;">${title}</div>
      ${content}
    </div>`;
  }

  // ─── Filter bar ───────────────────────────────────────────────────────────────

  const filterBar = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:20px;">
    ${['All Active', 'Octopus', 'Cat', 'Lion', 'Fox', 'Wolf', 'Mouse', 'Mantis', 'Swordfish'].map((d, i) =>
      `<button style="padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer;
        border:1px solid ${i === 0 ? '#0891B2' : '#e2e8f0'};
        background:${i === 0 ? '#0891B2' : '#fff'};
        color:${i === 0 ? '#fff' : '#374151'};
        font-family:inherit;">${d}${i === 0 ? ' ▾' : ''}</button>`
    ).join('')}
  </div>`;

  // ─── Main assembly ────────────────────────────────────────────────────────────

  return `
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 24px;
  max-width:1100px;">

  <!-- Header -->
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
    <div>
      <span style="font-size:15px;font-weight:700;color:#0891B2;
        letter-spacing:0.04em;text-transform:uppercase;">Cross-Deal Benchmarking</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;">
      <select style="padding:5px 10px;border:1px solid #e2e8f0;border-radius:4px;
        font-size:12px;color:#374151;background:#f8fafc;font-family:inherit;">
        <option>All Active ▾</option>
        <option>Offer stage only</option>
        <option>Financials received</option>
      </select>
    </div>
  </div>

  ${filterBar}
  ${legend}

  <div style="height:1px;background:#e2e8f0;margin:14px 0;"></div>

  ${section('Financial Comparison', renderMetricTable(financial))}
  ${section('Commercial Quality', renderMetricTable(commercial))}
  ${section('Valuation Comparison', renderValuationTable())}
  ${section('Portfolio Radar', renderSpiderPlaceholder())}

</div>`;
}

// ─── Dev harness — paste into browser console or Node to preview ──────────────
if (typeof module !== 'undefined') {
  module.exports = { renderBenchmark };
}
