/**
 * El reporte de Rooms Statistics, listo para imprimir a PDF en DOS páginas.
 *
 * **El pedido (owner, 2026-10-25):** *«mete este reporte como un reporte
 * frecuente… para que el reporte se genere según lo que diga el mes escogido…
 * que sea en PDF y en 2 páginas»*.
 *
 * Página 1: el tablero tal como se ve en la pantalla. Página 2: el detalle
 * mensual con los MESES EN COLUMNAS, seis indicadores.
 *
 * ⚠️ **No pide nada al servidor.** `getRevenueByRoomType` ya trae `months[]`;
 * la pantalla lo usa para el YTD y el Excel por mes. Es la misma regla que ya
 * está escrita en esa pantalla para el Excel mes a mes: *«agregar un endpoint
 * habría creado una segunda fuente del mismo número»*. Un reporte que calcula
 * por su cuenta es un reporte que algún día dice algo distinto de la pantalla
 * de la que cuelga, y nadie se entera hasta que alguien compara.
 *
 * ⚠️ **Los totales llegan calculados, no se recalculan acá.** La pantalla ya
 * resuelve el YTD, el «Other Rooms Revenue» que no tiene noches ni ADR pero sí
 * plata, y el orden por ingreso. Rehacer esa aritmética sería la segunda
 * fuente por la puerta de atrás.
 */

export interface FilaReporte {
  room_type_id: string;
  /** Puede no venir: no toda categoría tiene código. */
  room_type_code?: string;
  room_type_name: string;
  units: number;
  nights_available: number;
  nights_occupied: number;
  occupancy_pct: number;
  revenue: number;
  adr: number;
  pax: number;
  pct_of_total: number;
}

export interface MesReporte {
  month: number;
  rows: {
    room_type_id: string;
    nights_available: number;
    nights_occupied: number;
    revenue: number;
    pax: number;
  }[];
}

export interface DatosReporte {
  /** Las categorías del YTD, ya agregadas y ordenadas por ingreso. */
  filas: FilaReporte[];
  /** Los meses crudos, para el detalle de la página 2. */
  meses: MesReporte[];
  /** Mes de corte (1-12). El reporte va de enero a éste. */
  mes: number;
  year: number;
  /** Cómo se llama el escenario, para que el lector sepa de qué dato es. */
  escenario: string;
  /** Totales de las tarjetas, tal cual los muestra la pantalla. */
  total: { units: number; na: number; no: number; rev: number; pax: number };
  occTotal: number;
  adrTotal: number;
  /** El texto del Executive Insight que ya arma la pantalla. */
  insight: string;
  /** Ingreso sin tipo asociado (no-show, penalidades). Suma al total. */
  otherRevenue: number;
}

const MESL = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];
const AB = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Los tonos de la dona, en el orden en que la pantalla pinta la leyenda. */
const TONOS = ["#C9A227", "#1F3B63", "#5B7FA8", "#1F3B63", "#8FA9C4", "#E3D5A8"];

const usd = (v: number, d = 2) =>
  "$" + v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const num = (v: number, d = 0) =>
  v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

/**
 * ⚠️ Escapar SIEMPRE lo que viene del dato.
 *
 * Los nombres de categoría los escribe un usuario en Master Data. Un `&` o un
 * `<` en «Bar & Grill» rompe el HTML del reporte en silencio: la página sale
 * en blanco a la mitad y no hay error en ningún lado.
 */
function esc(s: string): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** La etiqueta de una categoría: «BI05 · Treehouse king bed». */
function rotulo(f: FilaReporte): string {
  return f.room_type_code ? `${f.room_type_code} · ${f.room_type_name}` : f.room_type_name;
}

export function htmlReporteRoomStats(d: DatosReporte): string {
  const { filas, meses, mes, year, escenario, total, occTotal, adrTotal } = d;
  const hoy = new Date();
  const generado = `${MESL[hoy.getMonth()]} ${hoy.getDate()}, ${hoy.getFullYear()}`;

  // ── barras ────────────────────────────────────────────────────────────────
  const maxRev = Math.max(...filas.map(f => f.revenue), 1);
  const paso = 150000;
  const tope = Math.ceil(maxRev / paso) * paso || paso;
  const barras = filas.map(f =>
    `<div class=br><div class=brl>${esc(f.room_type_name)}</div>`
    + `<div class=brt><div class=brb style="width:${(f.revenue / tope * 100).toFixed(2)}%"></div>`
    + `<span class=brv>${usd(f.revenue, 0)}</span></div></div>`).join("");
  const ejes = [0, 1, 2, 3, 4].map(i => {
    const v = tope * i / 4;
    return `<span>${v === 0 ? "$0" : "$" + (v / 1000).toLocaleString("en-US") + "K"}</span>`;
  }).join("");

  // ── dona ──────────────────────────────────────────────────────────────────
  let acum = 0;
  const tramos: string[] = [];
  const leyenda: string[] = [];
  filas.forEach((f, i) => {
    const pct = total.rev ? f.revenue / total.rev * 100 : 0;
    const color = TONOS[i % TONOS.length];
    tramos.push(`${color} ${acum.toFixed(3)}% ${(acum + pct).toFixed(3)}%`);
    acum += pct;
    leyenda.push(`<div class=lg><span class=pt style="background:${color}"></span>`
      + `<span class=lgn>${esc(rotulo(f))}</span>`
      + `<span class=lgp>${pct.toFixed(1)}%</span></div>`);
  });

  const tabla = filas.map(f =>
    `<tr><td class=l>${esc(rotulo(f))}</td><td>${num(f.units)}</td>`
    + `<td>${num(f.nights_occupied)}</td><td>${(f.occupancy_pct * 100).toFixed(1)}%</td>`
    + `<td>${usd(f.adr)}</td><td>${usd(f.revenue)}</td><td>${num(f.pax)}</td></tr>`).join("")
    // El ingreso sin tipo no tiene noches ni ADR, pero su plata es real: sale
    // como fila propia para que el TOTAL cierre a la vista.
    + (d.otherRevenue
      ? `<tr><td class=l>Other Rooms Revenue</td><td>—</td><td>—</td><td>—</td>`
        + `<td>—</td><td>${usd(d.otherRevenue)}</td><td>—</td></tr>`
      : "");

  // ── página 2: un bloque por indicador, meses en columnas ──────────────────
  const porMes = new Map<string, Map<number, MesReporte["rows"][number]>>();
  for (const mo of meses) {
    if (mo.month > mes) continue;
    for (const r of mo.rows) {
      if (!porMes.has(r.room_type_id)) porMes.set(r.room_type_id, new Map());
      porMes.get(r.room_type_id)!.set(mo.month, r);
    }
  }
  type Campo = "nights_available" | "nights_occupied" | "revenue" | "pax";
  const bloque = (
    titulo: string,
    valor: (r: Partial<MesReporte["rows"][number]>) => number,
    fmt: (v: number) => string,
  ) => {
    const th = Array.from({ length: mes }, (_, i) => `<th>${AB[i]}</th>`).join("");
    const cuerpo = filas.map(f => {
      const tds = Array.from({ length: mes }, (_, i) =>
        `<td>${fmt(valor(porMes.get(f.room_type_id)?.get(i + 1) ?? {}))}</td>`).join("");
      return `<tr><td class=l>${esc(f.room_type_code || f.room_type_name.slice(0, 5))}</td>`
        + `${tds}<td class=yt>${fmt(valor(f))}</td></tr>`;
    }).join("");
    const tds = Array.from({ length: mes }, (_, i) => {
      const m = i + 1;
      const agg: Record<Campo, number> = {
        nights_available: 0, nights_occupied: 0, revenue: 0, pax: 0 };
      for (const f of filas) {
        const r = porMes.get(f.room_type_id)?.get(m);
        if (!r) continue;
        agg.nights_available += r.nights_available;
        agg.nights_occupied += r.nights_occupied;
        agg.revenue += r.revenue;
        agg.pax += r.pax;
      }
      return `<td>${fmt(valor(agg))}</td>`;
    }).join("");
    const tot = valor({
      nights_available: total.na, nights_occupied: total.no,
      revenue: total.rev, pax: total.pax,
    });
    return `<div class=blk><div class=bt>${titulo}</div>`
      + `<table class=mm><thead><tr><th class=l>VILLA</th>${th}`
      + `<th class=yt>YTD ${AB[mes - 1]}</th></tr></thead><tbody>${cuerpo}`
      + `<tr class=tot><td class=l>TOT</td>${tds}<td class=yt>${fmt(tot)}</td>`
      + `</tr></tbody></table></div>`;
  };

  const n = (r: Partial<MesReporte["rows"][number]>, k: Campo) => r[k] ?? 0;
  const bloques = [
    bloque("NIGHTS AVAILABLE", r => n(r, "nights_available"), v => num(v)),
    bloque("NIGHTS OCCUPIED", r => n(r, "nights_occupied"), v => num(v)),
    bloque("OCCUPANCY %",
      r => (n(r, "nights_available") ? n(r, "nights_occupied") / n(r, "nights_available") : 0),
      v => (v * 100).toFixed(1) + "%"),
    bloque("REVENUE (USD)", r => n(r, "revenue"), v => usd(v, 0)),
    bloque("ADR (USD)",
      r => (n(r, "nights_occupied") ? n(r, "revenue") / n(r, "nights_occupied") : 0),
      v => usd(v)),
    bloque("PAX", r => n(r, "pax"), v => num(v)),
  ].join("");

  const leyCodigos = filas.map(f =>
    `<b>${esc(f.room_type_code ?? "")}</b> ${esc(f.room_type_name)}`).join(" &nbsp;·&nbsp; ");

  const KPIS: [string, string][] = [
    ["UNITS", num(total.units)],
    ["TOTAL NIGHTS", num(total.na)],
    ["TOTAL NIGHTS OCCUPIED", num(total.no)],
    ["OCCUPANCY", (occTotal * 100).toFixed(1) + "%"],
    ["ADR", usd(adrTotal)],
    ["TOTAL PAX", num(total.pax)],
    ["TOTAL REVENUE", usd(total.rev)],
  ];
  const tarjetas = KPIS.map(([a, b]) =>
    `<div class=k><div class=kl>${a}</div><div class=kv>${b}</div></div>`).join("");

  // ⚠️ Las medidas están calibradas al ancho REAL de la hoja (Letter
  // horizontal con 10 mm de margen ≈ 980 px), no al del navegador. A 1320 px
  // se veía bien y al imprimir las filas envolvían y la página 1 se desbordaba
  // a la 2.
  return `<!doctype html><html lang=en><head><meta charset=utf-8>
<title>CWL · Rooms Statistics · YTD ${MESL[mes - 1]} ${year}</title>
<style>
@page { size: Letter landscape; margin: 10mm; }
*{box-sizing:border-box;margin:0;padding:0}
body{font:11px/1.35 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 color:#20242B;background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.hd{background:linear-gradient(90deg,#141A22 0%,#1F3B63 55%,#5B7FA8 100%);
 border-left:5px solid #C9A227;border-radius:8px;padding:10px 18px;margin-bottom:10px;
 text-align:center}
.hd h1{font-size:19px;font-weight:700;color:#fff;line-height:1.2}
.hd h1 em{font-style:normal;color:#C9A227;margin-left:8px}
.hd .ov{font-size:9.5px;font-weight:700;letter-spacing:1.2px;color:#C9A227;
 text-transform:uppercase;margin-bottom:4px}
.hd .un{font-size:11px;color:#C7D2E0;margin-top:5px}
.hd .sc{font-size:10px;color:#C7D2E0;margin-top:7px;padding-top:7px;
 border-top:1px solid rgba(255,255,255,.18);display:inline-block}
.kr{display:grid;grid-template-columns:repeat(7,1fr);gap:7px;margin-bottom:10px}
.k{background:#EFEFEB;border:1px solid #E2E2DC;border-radius:9px;padding:9px 4px;text-align:center}
.kl{font-size:8.5px;font-weight:700;letter-spacing:.4px;color:#6B7280;margin-bottom:6px}
.kv{font-size:17px;font-weight:700;color:#141A22}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.pn{background:#EFEFEB;border:1px solid #E2E2DC;border-radius:9px;padding:10px 13px}
.ph{font-size:9px;font-weight:700;letter-spacing:.5px;color:#4A5568;text-align:center;margin-bottom:8px}
.br{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.brl{width:118px;font-size:8px;color:#374151;text-align:right;line-height:1.1}
.brt{flex:1;display:flex;align-items:center;gap:7px}
.brb{height:14px;background:#1F3B63;border-radius:1px}
.brv{font-size:8px;color:#374151;white-space:nowrap}
.ax{display:flex;justify-content:space-between;font-size:8.5px;color:#9CA3AF;
 margin:4px 0 0 124px;padding-right:50px}
.dn{display:flex;align-items:center;gap:12px}
.donut{width:124px;height:124px;border-radius:50%;flex:none;
 background:conic-gradient(${tramos.join(", ")});
 -webkit-mask:radial-gradient(circle,transparent 41px,#000 42px);
 mask:radial-gradient(circle,transparent 41px,#000 42px)}
.lgs{flex:1}
.lg{display:flex;align-items:center;gap:6px;font-size:8px;color:#374151;padding:1.5px 0}
.pt{width:9px;height:9px;border-radius:2px;flex:none}
.lgn{flex:1} .lgp{font-weight:700}
.tbl{width:100%;border-collapse:collapse;font-size:8.5px}
.tbl th{font-size:7px;font-weight:700;letter-spacing:.2px;color:#6B7280;
 text-align:right;padding:4px 5px;border-bottom:1.5px solid #D8DBE0}
.tbl th.l,.tbl td.l{text-align:left}
.tbl td{text-align:right;padding:4.5px 5px;border-bottom:1px solid #EDEFF2;white-space:nowrap}
.tbl tr.tot td{font-weight:700;border-top:1.5px solid #CBD2DA;border-bottom:none}
.ins{background:#FFFBEF;border:1px solid #E6D9A8;border-radius:9px;padding:11px 14px}
.ins .t{font-size:10px;font-weight:700;color:#B88A1B;letter-spacing:.5px;margin-bottom:9px}
.ins p{font-size:9.5px;line-height:1.5;color:#374151}
.p2{page-break-before:always}
.p2 .hd{padding:7px 18px;margin-bottom:6px}
.p2 .hd h1{font-size:16px}
.p2 .hd .ov{font-size:8.5px;margin-bottom:2px}
.p2 .hd .un{font-size:9.5px;margin-top:3px}
.p2 .hd .sc{font-size:8.5px;margin-top:5px;padding-top:5px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:5px 14px}
.leg{font-size:7.5px;color:#6B7280;text-align:center;margin-top:7px;
 padding-top:6px;border-top:1px solid #E5E7EB}
.blk{page-break-inside:avoid;break-inside:avoid}
table.mm{width:100%;border-collapse:collapse;font-size:7.3px;margin-bottom:2px}
table.mm th{background:#1F3B63;color:#fff;font-size:7px;font-weight:700;
 padding:2.5px 5px;text-align:right}
table.mm th.l,table.mm td.l{text-align:left;width:38px;font-weight:600}
table.mm td{text-align:right;padding:1.6px 5px;border-bottom:1px solid #EDEFF2;white-space:nowrap}
table.mm tbody tr:nth-child(even) td{background:#FAFBFC}
table.mm .yt{font-weight:700;color:#1F3B63;background:#F2F5F9!important;
 border-left:1.5px solid #CBD2DA}
table.mm tr.tot td{background:#2E5C8A!important;color:#fff;font-weight:700}
table.mm tr.tot td.yt{background:#1F3B63!important;color:#fff}
.bt{background:#2E5C8A;color:#fff;font-size:8px;font-weight:700;letter-spacing:.6px;
 padding:2.5px 10px;margin:6px 0 0;border-radius:3px 3px 0 0;text-align:center}
.sub{font-size:8.5px;color:#6B7280;margin:2px 0 4px;text-align:center}
</style></head><body>

<div class=hd>
  <div class=ov>Corcovado Wilderness Lodge &nbsp;·&nbsp; The Costa Rica Collection</div>
  <h1>Rooms Statistics <em>Year to Date · ${MESL[mes - 1]} ${year}</em></h1>
  <div class=un>Occupancy, ADR and revenue by room category &nbsp;·&nbsp;
    January – ${MESL[mes - 1]} ${year}</div>
  <div class=sc>DATA &nbsp;<b>${esc(escenario)}</b> &nbsp;·&nbsp; generated ${generado}</div>
</div>

<div class=kr>${tarjetas}</div>

<div class=row>
  <div class=pn><div class=ph>REVENUE BY ROOM CATEGORY</div>${barras}<div class=ax>${ejes}</div></div>
  <div class=pn><div class=ph>REVENUE MIX</div>
    <div class=dn><div class=donut></div><div class=lgs>${leyenda.join("")}</div></div></div>
</div>

<div class=row>
  <div class=pn><div class=ph>ROOM CATEGORY PERFORMANCE</div>
    <table class=tbl><thead><tr><th class=l>ROOM CATEGORY</th><th>UNITS</th>
    <th>ROOMS OCCUPIED</th><th>OCCUPANCY</th><th>ADR</th><th>TOTAL REVENUE</th>
    <th>TOTAL PAX</th></tr></thead><tbody>${tabla}
    <tr class=tot><td class=l>TOTAL</td><td>${num(total.units)}</td>
    <td>${num(total.no)}</td><td>${(occTotal * 100).toFixed(1)}%</td>
    <td>${usd(adrTotal)}</td><td>${usd(total.rev)}</td><td>${num(total.pax)}</td>
    </tr></tbody></table></div>
  <div class=ins><div class=t>💡 EXECUTIVE INSIGHT</div><p>${esc(d.insight)}</p></div>
</div>

<div class=p2>
  <div class=hd>
    <div class=ov>Corcovado Wilderness Lodge &nbsp;·&nbsp; Rooms Statistics</div>
    <h1>Monthly Detail <em>January – ${MESL[mes - 1]} ${year}</em></h1>
    <div class=un>Months in columns &nbsp;·&nbsp; six indicators by room category</div>
    <div class=sc>DATA &nbsp;<b>${esc(escenario)}</b> &nbsp;·&nbsp; generated ${generado}</div>
  </div>
  <div class=sub>One block per indicator. Rows are room categories and columns are
    months; the last column is the year-to-date figure through ${MESL[mes - 1]} —
    the same number shown on the previous page.</div>
  <div class=g2>${bloques}</div>
  <div class=leg>${leyCodigos}</div>
</div>
</body></html>`;
}
