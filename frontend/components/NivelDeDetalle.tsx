"use client";
/**
 * El mismo P&L, en tres niveles de detalle, a un clic.
 *
 * **El pedido (owner, 2026-08-27):** *«quiero ese reporte con varios niveles de
 * detalle con solo un click: 1-Resumido · 2-P&L a nivel Departamental ·
 * 3-Detallado, máximo detalle»*.
 *
 * Los tres ya existían como pantallas sueltas del menú. El problema no era que
 * faltara el reporte: era que para pasar de uno a otro había que salir al menú,
 * buscarlo, y **volver a elegir el escenario y el mes** — y ahí es donde se
 * pierde la comparación, porque el de al lado abre en otro escenario y las
 * cifras no son las mismas.
 *
 * ⚠️ **El contexto viaja por la URL, y viene por props.** Es la misma regla que
 * `IrA`: la pantalla sabe qué escenario y qué mes está mostrando; la URL puede
 * no decirlo todavía. Si este control lo dedujera por su cuenta, el salto
 * llevaría el escenario equivocado — y **no fallaría**: mostraría otro
 * presupuesto real, con sus totales bien sumados. Ver `lib/contexto.ts`.
 *
 * **Por qué no es un desplegable.** Son tres, se usan en secuencia («no cuadra
 * el GOP → abrí el departamental → abrí la cuenta»), y el valor está en ver los
 * tres rótulos a la vez para saber que existen. Un desplegable los esconde
 * detrás de un clic extra justo cuando se está buscando algo.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

import { conContexto, useContexto } from "@/lib/contexto";

/** Los tres niveles, del más resumido al más abierto. El orden es el pedido. */
export const NIVELES = [
  { n: 1, href: "/pl/simplified",           rotulo: "Resumido",
    ayuda: "Vista ejecutiva: estadísticas, ingreso, gasto y GOP" },
  { n: 2, href: "/reports/pl-by-dept",      rotulo: "Departamental",
    ayuda: "El P&L abierto por departamento" },
  { n: 3, href: "/reports/pl-full-detail",  rotulo: "Detallado",
    ayuda: "Máximo detalle: cuenta por cuenta" },
] as const;

export default function NivelDeDetalle({ esc, mes }: {
  /** El escenario que la pantalla está mostrando AHORA. */
  esc?: string;
  /** El mes, si la pantalla está parada en uno (1..12). */
  mes?: number;
}) {
  const pathname = usePathname();
  const ctxUrl = useContexto();

  // Lo que la pantalla dice le gana a lo que diga la URL: la URL es de cuando
  // llegaste, la pantalla es de ahora.
  const ctx = { esc: esc ?? ctxUrl.esc, mes: mes ?? ctxUrl.mes };

  return (
    <nav aria-label="Nivel de detalle" style={{
      display: "inline-flex", alignItems: "center", gap: 0,
      borderRadius: 6, overflow: "hidden",
      border: "1px solid var(--border-medium)",
    }}>
      <span style={{
        padding: "6px 10px", fontSize: 11, fontWeight: 700, letterSpacing: 0.3,
        color: "var(--text-secondary)", background: "var(--bg-subtle)",
        borderRight: "1px solid var(--border-medium)", whiteSpace: "nowrap",
      }}>DETALLE</span>

      {NIVELES.map((nv, i) => {
        const activo = pathname === nv.href;
        const contenido = (
          <>
            <span style={{ opacity: 0.65, marginRight: 5 }}>{nv.n}</span>
            {nv.rotulo}
          </>
        );
        const estilo: React.CSSProperties = {
          padding: "6px 13px", fontSize: 12, fontWeight: 600,
          textDecoration: "none", whiteSpace: "nowrap",
          borderLeft: i === 0 ? "none" : "1px solid var(--border-medium)",
          background: activo ? "var(--brand)" : "var(--bg-surface)",
          color: activo ? "#fff" : "var(--text-primary)",
          cursor: activo ? "default" : "pointer",
        };
        // El nivel en el que ya estás no es un link: un link a la pantalla
        // actual recarga y pierde lo que tengas desplegado.
        return activo ? (
          <span key={nv.n} aria-current="page" title={nv.ayuda} style={estilo}>
            {contenido}
          </span>
        ) : (
          <Link key={nv.n} href={conContexto(nv.href, ctx, ["esc", "mes"])}
                title={nv.ayuda} style={estilo}>
            {contenido}
          </Link>
        );
      })}
    </nav>
  );
}
