"use client";
/**
 * La banda que dice QUÉ set estás mirando.
 *
 * Una pantalla filtrada y una sin filtrar se ven iguales salvo por cuántas
 * filas tienen — y «cuántas filas tiene Rack Rates» no es algo que nadie se
 * sepa de memoria. Sin esta banda, abrir Villas desde el menú y abrir Rack
 * Rates desde Planning son dos pantallas idénticas con totales distintos, que
 * es exactamente la clase de confusión que termina en una tarifa cargada en el
 * lugar equivocado.
 *
 * Por eso dice las tres cosas que distinguen la vista: qué set, cuántas
 * unidades, y cómo salir. El «ver todas» es un link y no un botón porque
 * cambiar de set ES navegar: tiene que quedar en el historial.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { useContexto } from "@/lib/contexto";
import { SET_VILLAS, SET_RESIDENCIAS } from "@/lib/roomSet";

const NOMBRE: Record<string, string> = {
  [SET_VILLAS]: "Villas",
  [SET_RESIDENCIAS]: "Residencias",
};

export default function AvisoSet(
  { set, unidades, vacio }: { set: string; unidades: number; vacio: boolean },
) {
  const t = useTranslations("roomSetView");
  const pathname = usePathname();
  const { esc } = useContexto();

  if (!set) return null;

  const nombre = NOMBRE[set] ?? set;
  const todas = esc ? `${pathname}?esc=${encodeURIComponent(esc)}` : pathname;

  return (
    <div style={{
      margin: "10px 0 16px", padding: "10px 14px", borderRadius: 6,
      background: vacio ? "rgba(192,57,43,0.10)" : "rgba(200,162,74,0.10)",
      border: `1px solid ${vacio ? "var(--accent-red, #C0392B)" : "#c8a24a"}`,
      display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
    }}>
      <span style={{
        fontSize: 11, fontWeight: 700, letterSpacing: "0.06em",
        textTransform: "uppercase", color: vacio ? "var(--accent-red, #C0392B)" : "#c8a24a",
      }}>
        {t("badge", { set: nombre })}
      </span>
      <div style={{ flex: 1, minWidth: 260, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
        {vacio
          ? t("empty", { set: nombre })
          : t("help", { set: nombre, n: unidades })}
      </div>
      <Link href={todas} style={{
        fontSize: 12, fontWeight: 600, color: "var(--text-secondary)",
        textDecoration: "underline", whiteSpace: "nowrap",
      }}>
        {t("showAll")}
      </Link>
    </div>
  );
}
