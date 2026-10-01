"use client";
/**
 * «Análisis especial»: el estudio de un mes, en sub-pestañas.
 *
 * Owner, 2026-09-30: *«un tab llamado Análisis especial… metemos Noviembre y
 * Diciembre y hacemos uno tal como Diciembre con una opción editable donde yo
 * puedo hacer un estudio particular de enero a diciembre 2027… que sea un sub
 * tab Noviembre 2026, Diciembre 2026 y uno editable o droplist y yo escojo»*.
 *
 * Las tres sub-pestañas dibujan el MISMO estudio (`AnalisisMes`, que sale de
 * `/pacing/mes`). La de «a medida» deja escoger el mes de 2027 y, si se quiere,
 * una meta propia de RN e ingreso. ⚠️ Esa meta sólo vive en la consulta: no se
 * guarda ni toca la meta del módulo (esa se edita en Presupuesto).
 */
import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import type { PacingMes } from "@/lib/api";
import { AnalisisMes, type MetaManual } from "./mes";
import {
  Tabla, boton, botonPrimario, card, colorDe, filaTotal, n0, pct, select, signo, td, tdL, th, usd0,
} from "./comun";

type Vista = "nov" | "dic" | "medida";
const VISTAS: Vista[] = ["nov", "dic", "medida"];
const ANIO_MEDIDA = 2027;

const entrada: CSSProperties = { ...select, width: 140, textAlign: "right", fontFamily: "var(--font-mono)" };

function numero(s: string): number | undefined {
  const v = Number(String(s).replace(/[$,\s]/g, ""));
  return Number.isFinite(v) && v > 0 ? v : undefined;
}

export function AnalisisEspecial() {
  const t = useTranslations("pacing.especial");
  const tm = useTranslations("months");
  const largos = tm.raw("long") as string[];
  const router = useRouter();
  const ruta = usePathname();
  const qs = useSearchParams();

  const vista: Vista = (VISTAS as string[]).includes(qs.get("v") ?? "") ? (qs.get("v") as Vista) : "nov";
  const mesQ = Number(qs.get("m"));
  const mesMedida = mesQ >= 1 && mesQ <= 12 ? mesQ : 1;

  // Meta a medida: lo escrito (texto) y lo aplicado (lo que se manda al cálculo).
  const [rnTxt, setRnTxt] = useState("");
  const [totTxt, setTotTxt] = useState("");
  const [aplicada, setAplicada] = useState<MetaManual | undefined>(undefined);
  const [cargada, setCargada] = useState<PacingMes["meta"]>(null);
  const [datos, setDatos] = useState<PacingMes | null>(null);
  // Constructor de meta: % de alza en tarifa y ocupación objetivo sobre el mismo mes del año anterior.
  const [alzaTxt, setAlzaTxt] = useState("0");
  const [occTxt, setOccTxt] = useState("");

  const ir = useCallback((v: Vista, m?: number) => {
    const q = new URLSearchParams({ v });
    if (v === "medida") q.set("m", String(m ?? mesMedida));
    router.replace(`${ruta}?${q.toString()}`);
  }, [router, ruta, mesMedida]);

  // Al cambiar de mes se arranca de la meta cargada de ese mes.
  useEffect(() => {
    setAplicada(undefined); setCargada(null); setRnTxt(""); setTotTxt(""); setFaltaAlgo(false);
    setDatos(null); setAlzaTxt("0"); setOccTxt("");
  }, [vista, mesMedida]);

  const alCargar = useCallback((a: PacingMes) => {
    setDatos(a);
    setOccTxt(prev => {
      if (prev) return prev;
      const h = a.anterior.hf;
      const occ = h.rn && h.cap ? h.rn / h.cap : a.anterior.occ;
      return occ ? (occ * 100).toFixed(1) : "";
    });
    if (aplicada) return;                       // ya hay meta propia: no pisarla
    setCargada(a.meta);
    setRnTxt(a.meta?.rn ? String(Math.round(a.meta.rn)) : "");
    setTotTxt(a.meta?.total ? String(Math.round(a.meta.total)) : "");
  }, [aplicada]);

  const [faltaAlgo, setFaltaAlgo] = useState(false);
  const aplicar = () => {
    const rn = numero(rnTxt), total = numero(totTxt);
    // ⚠️ Sin meta cargada hacen falta las dos: con una sola, el estudio dividiría
    // contra una meta en cero.
    const falta = !cargada?.rn && !cargada?.total && (!rn || !total);
    setFaltaAlgo(falta);
    if (falta) return;
    setAplicada(rn || total ? { rn, total } : undefined);
  };
  const limpiar = () => { setAplicada(undefined); setCargada(null); setRnTxt(""); setTotTxt(""); setFaltaAlgo(false); };

  const anio = vista === "medida" ? ANIO_MEDIDA : 2026;
  const mes = vista === "nov" ? 11 : vista === "dic" ? 12 : mesMedida;

  return (
    <div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {VISTAS.map(k => (
          <button key={k} onClick={() => ir(k)} style={k === vista ? botonPrimario : boton}>{t(`vistas.${k}`)}</button>
        ))}
      </div>

      {vista === "medida" && (
        <div style={{ ...card, display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16, maxWidth: 1210 }}>
          <label style={{ fontSize: 12, display: "grid", gap: 4 }}>
            {t("mes")}
            <select style={{ ...select, minWidth: 170 }} value={mesMedida} onChange={e => ir("medida", Number(e.target.value))}>
              {largos.map((n, i) => <option key={i} value={i + 1}>{n} {ANIO_MEDIDA}</option>)}
            </select>
          </label>
          <label style={{ fontSize: 12, display: "grid", gap: 4 }}>
            {t("metaRn")}
            <input style={entrada} inputMode="numeric" value={rnTxt} placeholder="0"
                   onChange={e => setRnTxt(e.target.value)} onKeyDown={e => e.key === "Enter" && aplicar()} />
          </label>
          <label style={{ fontSize: 12, display: "grid", gap: 4 }}>
            {t("metaTotal")}
            <input style={entrada} inputMode="numeric" value={totTxt} placeholder="0"
                   onChange={e => setTotTxt(e.target.value)} onKeyDown={e => e.key === "Enter" && aplicar()} />
          </label>
          <button style={botonPrimario} onClick={aplicar}>{t("aplicar")}</button>
          {aplicada && <button style={boton} onClick={limpiar}>{t("limpiar")}</button>}
          <div style={{ fontSize: 11, color: "var(--text-secondary)", flexBasis: "100%", lineHeight: 1.5 }}>
            {aplicada ? t("notaManual") : cargada ? t("notaCargada", { fuente: cargada.source ?? "—" }) : t("notaSinMeta")}
            {faltaAlgo && <span style={{ color: "var(--warning)" }}> {t("faltaAlgo")}</span>}
          </div>
        </div>
      )}

      {vista === "medida" && datos && !datos.vacio && (
        <MismoMesAnterior a={datos} largo={largos[mesMedida - 1]} alzaTxt={alzaTxt} setAlzaTxt={setAlzaTxt}
                          occTxt={occTxt} setOccTxt={setOccTxt}
                          usar={(rn, total) => {
                            setRnTxt(String(rn)); setTotTxt(String(total)); setFaltaAlgo(false);
                            setAplicada({ rn, total });
                          }} />
      )}

      <AnalisisMes key={`${anio}-${mes}`} year={anio} month={mes} metaManual={aplicada} onCargado={alCargar} />
    </div>
  );
}

/**
 * El mismo mes del año anterior, al lado de lo que hay hoy, y un constructor de
 * meta: ocupación objetivo × noches disponibles del mes = RN; ingreso por noche
 * del año anterior × (1 + alza de tarifa) × RN = ingreso.
 *
 * ⚠️ El cierre del año anterior sale del History & Forecast (ingreso TOTAL, con
 * consumo en sitio). Si las fotos no cubren ese mes, se usa el valor de las
 * reservas, que es sólo habitación: se avisa en la nota.
 */
function MismoMesAnterior({ a, largo, alzaTxt, setAlzaTxt, occTxt, setOccTxt, usar }: {
  a: PacingMes; largo: string;
  alzaTxt: string; setAlzaTxt: (v: string) => void;
  occTxt: string; setOccTxt: (v: string) => void;
  usar: (rn: number, total: number) => void;
}) {
  const tl = useTranslations("pacing.especial.ly");
  const P = a.anterior, L = a.libros, h = P.hf;
  const conFotos = h.rn > 0;
  const capLy = conFotos && h.cap ? h.cap : a.cap;
  const ly = conFotos
    ? { rn: h.rn, total: h.total, adr: h.rn ? h.rooms / h.rn : 0 }
    : { rn: P.rn, total: P.valor_total, adr: P.valor_noche };
  const noche = ly.rn ? ly.total / ly.rn : 0;

  const alza = Number(String(alzaTxt).replace(",", ".")) || 0;
  const occ = Number(String(occTxt).replace(",", ".")) || 0;
  const rnObj = Math.round(Math.min(occ, 100) / 100 * a.cap);
  const nocheObj = noche * (1 + alza / 100);
  const ingObj = Math.round(rnObj * nocheObj);
  const listo = rnObj > 0 && ingObj > 0;

  const etiqueta = `${largo.toLowerCase()} ${a.anio - 1}`;
  const filas: { k: string; rn: number; occ: number; adr: number | null; total: number | null; noche: number | null; b?: boolean }[] = [
    { k: tl("stly", { fecha: a.stly_fecha }), rn: P.stly, occ: capLy ? P.stly / capLy : 0, adr: null,
      total: null, noche: P.stly ? P.stly_valor / P.stly : null },
    { k: tl("cierre", { mes: etiqueta }), rn: ly.rn, occ: capLy ? ly.rn / capLy : 0, adr: ly.adr, total: ly.total, noche },
    { k: tl("hoy", { fecha: a.corte }), rn: L.rn, occ: L.occ, adr: L.adr_rooms, total: L.total, noche: L.rn ? L.total / L.rn : null, b: true },
  ];
  const vsStly = L.rn - P.stly;

  return (
    <div style={{ ...card, marginBottom: 16, maxWidth: 1210 }}>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{tl("titulo", { mes: etiqueta })}</div>
      <Tabla minWidth={760}>
        <thead><tr>
          {["concepto", "rn", "occ", "adr", "total", "noche"].map((c, i) =>
            <th key={c} style={{ ...th, textAlign: i ? "right" : "left" }}>{tl(`c.${c}`)}</th>)}
        </tr></thead>
        <tbody>
          {filas.map(f => (
            <tr key={f.k} style={f.b ? filaTotal : undefined}>
              <td style={tdL}>{f.k}</td><td style={td}>{n0(f.rn)}</td><td style={td}>{pct(f.occ, 1)}</td>
              <td style={td}>{f.adr == null ? "—" : usd0(f.adr)}</td><td style={td}>{f.total == null ? "—" : usd0(f.total)}</td>
              <td style={td}>{f.noche == null ? "—" : usd0(f.noche)}</td>
            </tr>
          ))}
          <tr><td style={tdL}>{tl("vsStly")}</td>
            <td style={{ ...td, color: colorDe(vsStly) }}>{signo(vsStly, n0)}</td>
            <td style={{ ...td, color: colorDe(vsStly) }}>{P.stly ? signo(vsStly / P.stly, x => pct(x, 0)) : "—"}</td>
            <td style={td} colSpan={3}></td></tr>
        </tbody>
      </Tabla>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", margin: "6px 0 14px", lineHeight: 1.5 }}>
        {tl(conFotos ? "notaFotos" : "notaReservas")}
      </div>

      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{tl("constructor")}</div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ fontSize: 12, display: "grid", gap: 4 }}>
          {tl("alza")}
          <input style={{ ...select, width: 110, textAlign: "right" }} inputMode="decimal" value={alzaTxt}
                 onChange={e => setAlzaTxt(e.target.value)} />
        </label>
        <label style={{ fontSize: 12, display: "grid", gap: 4 }}>
          {tl("occ")}
          <input style={{ ...select, width: 110, textAlign: "right" }} inputMode="decimal" value={occTxt}
                 onChange={e => setOccTxt(e.target.value)} />
        </label>
        <div style={{ fontSize: 12, lineHeight: 1.6 }}>
          <div>{tl("resRn", { occ: occ.toFixed(1), cap: n0(a.cap), rn: n0(rnObj) })}</div>
          <div>{tl("resNoche", { base: usd0(noche), alza: alza.toFixed(1), noche: usd0(nocheObj) })}</div>
          <div><b>{tl("resTotal", { total: usd0(ingObj) })}</b>
            {" "}<span style={{ color: colorDe(ingObj - ly.total) }}>({tl("vsLy", { d: signo(ingObj - ly.total, usd0) })})</span></div>
        </div>
        <button style={listo ? botonPrimario : { ...boton, opacity: 0.5 }} disabled={!listo}
                onClick={() => usar(rnObj, ingObj)}>{tl("usar")}</button>
      </div>
    </div>
  );
}
