// ALLEX v2 — minimal data, mirrors screenshot records
window.D = (function(){
  const rows = [
    { name: "Rennecke-Medic GmbH", domain: "rennecke-medic.de", region: "Niedernberg", klass: "B", ready: 66 },
    { name: "Kreidel Medizintechnik", domain: "kreidel-medizintechnik.de", region: "Niedersachsen", klass: "B", ready: 66 },
    { name: "Diopharm Handel GmbH", domain: "diopharm.de", region: "Märkisch-Oderland", klass: "B", ready: 66 },
    { name: "Strauz Novelec GmbH", domain: "strauz-novelec.de", region: "Unterfranken", klass: "B", ready: 62 },
    { name: "Wörner Medizinprodukte", domain: "woerner-medizinprodukte.de", region: "Schwäbische Alb", klass: "A", ready: 62 },
    { name: "Mectb GmbH", domain: "mectb.de", region: "Potsdam", klass: "B", ready: 46 },
    { name: "KMP Praxisversorgung", domain: "kmp-praxisversorgung.de", region: "Hildesheim", klass: "B", ready: 46 },
    { name: "Chr. Frick Medizintechnik", domain: "frick-medizintechnik.de", region: "Ruhrgebiet", klass: "B", ready: 46 },
    { name: "BRUNE Medizintechnik", domain: "brune-medizintechnik.de", region: "Schwaben", klass: "A", ready: 46 },
    { name: "Disponed GmbH", domain: "disponed.de", region: "Main-Kinzig-Kreis", klass: "B", ready: 31 },
    { name: "BIEWER medical GmbH", domain: "biewer-medical.com", region: "Mittelfranken", klass: "B", ready: 31 },
    { name: "AMP-Med GmbH", domain: "amp-med.de", region: "Saarland", klass: "B", ready: 31 },
    { name: "Schnelle Medizintechnik", domain: "medizintechnik-schnelle.de", region: "Sachsen", klass: "B", ready: 31 },
    { name: "SONO Service & Support", domain: "sono-service.de", region: "Baden-Württemberg", klass: "B", ready: 20 },
    { name: "NEUMED Medizinprodukte", domain: "neumed.de", region: "Bayern", klass: "A", ready: 20 },
    { name: "GRAUPNER medical group", domain: "graupner-medical-group.com", region: "Nordrhein-Westfalen", klass: "B", ready: 20 },
    { name: "KAMED GmbH", domain: "shop.ka-med.de", region: "Braunschweig", klass: "B", ready: 20 },
    { name: "Zuther & Holzmann GmbH", domain: "zuther-holzmann.de", region: "Mecklenburg", klass: "B", ready: 77 },
    { name: "Medizintechnik St. Egidien", domain: "medizintechnik-web.de", region: "Erzgebirge", klass: "A", ready: 77 },
    { name: "Tec Service Berlin", domain: "medizintechnik-berlin-gmbh.de", region: "Berlin", klass: "B", ready: 77 },
    { name: "Consumed GmbH", domain: "consu-med.de", region: "Oberpfalz", klass: "B", ready: 100 },
    { name: "Inmed Service GmbH", domain: "inmed-service.com", region: "Region Hann.-Münden", klass: "B", ready: 100 },
    { name: "Kamed GmbH", domain: "ka-med.de", region: "Braunschweig", klass: "B", ready: 100 },
    { name: "Mamedis GmbH", domain: "mamedis.de", region: "Magdeburg", klass: "A", ready: 100 },
  ];

  // What's missing per record (assembly-line checklist)
  // Each item: {key, label, hint, severity: 'block'|'warn'|'done'}
  // Severity logic: lower readiness = more 'block' items
  function missingFor(r){
    const all = [
      { key: 'klass',     label: 'Klassifikation bestätigt',        hint: 'AI hat A/B vorgeschlagen — manuell bestätigen' },
      { key: 'region',    label: 'Region zugeordnet',                hint: 'Wird in Briefkopf verwendet' },
      { key: 'gf_name',   label: 'Geschäftsführer (Name)',           hint: 'Aus Impressum extrahieren' },
      { key: 'anrede',    label: 'Anrede generiert',                 hint: '„Sehr geehrte Frau …" / „Herr …"' },
      { key: 'address',   label: 'Postadresse (Straße, PLZ, Stadt)', hint: 'Fehlt im Brief — kritisch' },
      { key: 'compliment',label: 'Persönliches Kompliment',          hint: 'AI-generiert · 2-3 Sätze · spezifisch' },
      { key: 'email',     label: 'GF E-Mail-Adresse',                hint: 'Optional aber empfohlen' },
      { key: 'approve',   label: 'Final freigegeben',                hint: 'Letzter Review-Schritt vor Export' },
    ];
    // Map readiness % → which items are done
    const order = ['klass','region','gf_name','anrede','address','compliment','email','approve'];
    const doneCount = Math.round((r.ready/100) * order.length);
    return all.map((item, i) => {
      let severity;
      if (i < doneCount) severity = 'done';
      else if (item.key === 'address') severity = 'block';   // address is always critical
      else if (i === doneCount) severity = 'warn';            // next-up
      else severity = 'warn';
      return { ...item, severity };
    });
  }

  return {
    rows,
    kpis: {
      ready: rows.filter(r => r.ready === 100).length,
      blocked: rows.filter(r => r.ready < 100 && r.ready >= 50).length,
      stalled: rows.filter(r => r.ready < 50).length,
    },
    funnel: [
      { stage: 'Ingested',       sub: 'ORBIS · Impressum · HR',     n: 2012, pct: 100 },
      { stage: 'Filter pass',    sub: 'Branche & Größe',            n: 1563, pct: 78 },
      { stage: 'Scraped',        sub: 'Web + Impressum',            n: 1563, pct: 78 },
      { stage: 'Classified',     sub: 'AI · A/B/C/D/E',             n: 552,  pct: 27 },
      { stage: 'A + B qualified',sub: 'Repuro-Zielgruppe',          n: 36,   pct: 1.8 },
      { stage: 'Ready to export',sub: 'Alle Felder · approved',     n: 4,    pct: 0.2 },
    ],
    cohorts: [
      { name: 'BA #7 Niederrhein',  sent: 32, reply: 6,  meeting: 2, deal: 1 },
      { name: 'BA #6 Ruhrgebiet',   sent: 48, reply: 11, meeting: 4, deal: 1 },
      { name: 'BA #5 Bayern Süd',   sent: 54, reply: 14, meeting: 5, deal: 2 },
      { name: 'BA #4 Hessen',       sent: 38, reply: 7,  meeting: 3, deal: 1 },
      { name: 'BA #3 NRW West',     sent: 62, reply: 18, meeting: 8, deal: 3 },
      { name: 'BA #2 Baden-Württ.', sent: 41, reply: 9,  meeting: 4, deal: 1 },
    ],
    classes: [
      { k: 'A', n: 5,   desc: 'Platform' },
      { k: 'B', n: 31,  desc: 'Add-on' },
      { k: 'C', n: 13,  desc: 'Unklar' },
      { k: 'D', n: 500, desc: 'No-fit' },
      { k: 'E', n: 3,   desc: 'Special' },
    ],
    bottlenecks: [
      { n: 1011, label: 'Unklassifiziert', sev: '', action: 'AI-Klassifikation starten' },
      { n: 32,   label: 'Fehlende E-Mail', sev: 'warn', action: 'Manuelle Recherche' },
      { n: 27,   label: 'Fehlende Adresse', sev: 'block', action: 'Impressum prüfen' },
    ],

    // Funnel drop-off for current BA (#7 Niederrhein) — where ingested records fell out
    // Each stage: passed → next stage; dropped → out (with reason buckets)
    dropoff: {
      total: 184,
      stages: [
        {
          stage: 'Ingest',
          sub: 'ORBIS · WLW · Manual',
          passed: 184,
          dropped: 0,
          reasons: [],
        },
        {
          stage: 'Hard Filter',
          sub: 'Branche · Größe · Land',
          passed: 142,
          dropped: 42,
          reasons: [
            { label: 'Bereits angeschrieben (Dedup)', n: 21, kind: 'dedup' },
            { label: 'Zu groß (>100 MA)',             n:  9, kind: 'size' },
            { label: 'Zu klein (<5 MA)',              n:  6, kind: 'size' },
            { label: 'Apotheke (NACE 4774)',          n:  4, kind: 'branch' },
            { label: 'Dental-Keyword im Namen',       n:  2, kind: 'branch' },
          ],
        },
        {
          stage: 'Scrape',
          sub: 'Website + Impressum',
          passed: 128,
          dropped: 14,
          reasons: [
            { label: 'Domain nicht erreichbar (DNS)', n: 8, kind: 'tech' },
            { label: 'Timeout / 5xx',                 n: 4, kind: 'tech' },
            { label: 'Robots.txt blockt',             n: 2, kind: 'tech' },
          ],
        },
        {
          stage: 'Classify',
          sub: 'AI · A/B/C/D/E',
          passed: 47,
          dropped: 81,
          reasons: [
            { label: 'D — Unpassende Branche',  n: 38, kind: 'klass' },
            { label: 'D — Handwerk',            n: 14, kind: 'klass' },
            { label: 'D — OEM/Hersteller',      n: 11, kind: 'klass' },
            { label: 'D — Krankenhaus only',    n:  9, kind: 'klass' },
            { label: 'D — Apotheke',            n:  5, kind: 'klass' },
            { label: 'E — Special',             n:  4, kind: 'klass' },
          ],
        },
        {
          stage: 'Ownership Gate',
          sub: 'OpenRegister · Blocklist',
          passed: 39,
          dropped: 8,
          reasons: [
            { label: 'S — Konzerntochter',           n: 5, kind: 'owner' },
            { label: 'S — PE-backed',                n: 2, kind: 'owner' },
            { label: 'S — Unbek. Owner ≥75%',        n: 1, kind: 'owner' },
          ],
        },
        {
          stage: 'Enrichment',
          sub: 'Adresse · GF · Email',
          passed: 32,
          dropped: 7,
          reasons: [
            { label: 'Adresse nicht extrahierbar',   n: 4, kind: 'enrich' },
            { label: 'GF-Name nicht gefunden',       n: 2, kind: 'enrich' },
            { label: 'Impressum unvollständig',      n: 1, kind: 'enrich' },
          ],
        },
        {
          stage: 'Approval',
          sub: 'Manueller Review',
          passed: 4,
          dropped: 28,
          reasons: [
            { label: 'In Bearbeitung (warn)',        n: 21, kind: 'pending' },
            { label: 'Blockiert (Felder fehlen)',    n:  7, kind: 'pending' },
          ],
        },
      ],
    },

    // Activity log — recent field changes, who did them
    activity: [
      { ts: '27.04. 14:32', actor: 'claude', company: 'Rennecke-Medic GmbH',     field: 'compliment',         old: '—',                       neu: 'Besonders beeindruckt hat uns die Sortimentstiefe von über 600 Artikeln…', kind: 'gen' },
      { ts: '27.04. 14:31', actor: 'claude', company: 'Rennecke-Medic GmbH',     field: 'leistung_text',      old: '—',                       neu: 'Sprechstundenbedarf · Notfallausrüstung',                                  kind: 'gen' },
      { ts: '27.04. 14:18', actor: 'roman',  company: 'Kreidel Medizintechnik',  field: 'klass',              old: 'C',                       neu: 'B',                                                                        kind: 'edit' },
      { ts: '27.04. 14:18', actor: 'roman',  company: 'Kreidel Medizintechnik',  field: 'reclassify_reason',  old: '—',                       neu: 'B — Add-on, Service-Komponente bestätigt',                                 kind: 'edit' },
      { ts: '27.04. 13:55', actor: 'claude', company: 'Diopharm Handel GmbH',    field: 'gesellschafter_name', old: '—',                      neu: 'Markus Diopharm',                                                          kind: 'enrich' },
      { ts: '27.04. 13:54', actor: 'claude', company: 'Diopharm Handel GmbH',    field: 'is_subsidiary',      old: 'NULL',                    neu: 'false',                                                                    kind: 'enrich' },
      { ts: '27.04. 13:54', actor: 'claude', company: 'Diopharm Handel GmbH',    field: 'pipeline_stage',     old: 'classified',              neu: 'ownership_enriched',                                                       kind: 'system' },
      { ts: '27.04. 13:42', actor: 'roman',  company: 'Strauz Novelec GmbH',     field: 'gf_email',           old: 'info@strauz-novelec.de',  neu: 'k.strauz@strauz-novelec.de',                                               kind: 'edit' },
      { ts: '27.04. 13:40', actor: 'roman',  company: 'Strauz Novelec GmbH',     field: 'anrede',             old: 'Herr',                    neu: 'Frau',                                                                     kind: 'edit' },
      { ts: '27.04. 13:21', actor: 'claude', company: 'Wörner Medizinprodukte',  field: 'compliment',         old: '—',                       neu: 'Beeindruckend ist die enge Bindung an niedergelassene Praxen in Süddeutschland…', kind: 'gen' },
      { ts: '27.04. 13:09', actor: 'roman',  company: 'BRUNE Medizintechnik',    field: 'klass',              old: 'B',                       neu: 'A',                                                                        kind: 'edit' },
      { ts: '27.04. 13:08', actor: 'roman',  company: 'BRUNE Medizintechnik',    field: 'reclassify_reason',  old: '—',                       neu: 'Größe & Service-Tiefe rechtfertigen A',                                    kind: 'edit' },
      { ts: '27.04. 12:47', actor: 'claude', company: 'Mectb GmbH',              field: 'klass',              old: '—',                       neu: 'B',                                                                        kind: 'gen' },
      { ts: '27.04. 12:46', actor: 'claude', company: 'Mectb GmbH',              field: 'services_score',     old: '—',                       neu: '54',                                                                       kind: 'gen' },
      { ts: '27.04. 12:31', actor: 'roman',  company: 'KMP Praxisversorgung',    field: 'street',             old: '—',                       neu: 'Industriestraße 12',                                                       kind: 'edit' },
      { ts: '27.04. 12:31', actor: 'roman',  company: 'KMP Praxisversorgung',    field: 'plz_ort',            old: '—',                       neu: '31135 Hildesheim',                                                         kind: 'edit' },
      { ts: '27.04. 11:58', actor: 'claude', company: 'Disponed GmbH',           field: 'compliment',         old: 'Generic v1',              neu: 'Die Spezialisierung auf Praxisbedarf für Allgemeinmediziner überzeugt…',  kind: 'regen' },
      { ts: '27.04. 11:42', actor: 'roman',  company: 'BIEWER medical GmbH',     field: 'approved_for_sendout', old: '0',                     neu: '1',                                                                        kind: 'approve' },
      { ts: '27.04. 11:18', actor: 'claude', company: 'AMP-Med GmbH',            field: 'gf_name',            old: '—',                       neu: 'Andreas Pohl',                                                             kind: 'enrich' },
      { ts: '27.04. 11:02', actor: 'roman',  company: 'NEUMED Medizinprodukte',  field: 'klass',              old: 'A',                       neu: 'S',                                                                        kind: 'edit' },
      { ts: '27.04. 11:02', actor: 'roman',  company: 'NEUMED Medizinprodukte',  field: 'reclassify_reason',  old: '—',                       neu: 'Tochter von B. Braun (manuell verifiziert)',                               kind: 'edit' },
    ],

    missingFor,
  };
})();
