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
import { boton, botonPrimario, card, select } from "./comun";

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

  const ir = useCallback((v: Vista, m?: number) => {
    const q = new URLSearchParams({ v });
    if (v === "medida") q.set("m", String(m ?? mesMedida));
    router.replace(`${ruta}?${q.toString()}`);
  }, [router, ruta, mesMedida]);

  // Al cambiar de mes se arranca de la meta cargada de ese mes.
  useEffect(() => { setAplicada(undefined); setCargada(null); setRnTxt(""); setTotTxt(""); setFaltaAlgo(false); }, [vista, mesMedida]);

  const alCargar = useCallback((a: PacingMes) => {
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

      <AnalisisMes key={`${anio}-${mes}`} year={anio} month={mes} metaManual={aplicada} onCargado={alCargar} />
    </div>
  );
}
