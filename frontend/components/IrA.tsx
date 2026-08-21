"use client";
/**
 * La barra de saltos: «Ir a…» y «‹ Volver a».
 *
 * **El pedido (owner, 2026-08-19):** «que dentro de un tab me pueda mover a
 * otro tab internamente sin tener que salir… en forma lógica».
 *
 * Dos sentidos, y hacen falta los dos. El «Ir a» te lleva a la pregunta
 * siguiente; el «Volver a» te trae de vuelta a lo que estabas haciendo. Sin el
 * segundo, saltar sale caro: hay que reconstruir a mano dónde estabas, y
 * entonces la gente deja de saltar.
 *
 * ⚠️ **El contexto se pasa por props, no se adivina.** La pantalla sabe qué
 * escenario y qué mes está mostrando; la URL puede no decirlo todavía. Si esta
 * barra dedujera el contexto por su cuenta, el salto llevaría el escenario
 * equivocado — y no fallaría: mostraría otro presupuesto real. Ver
 * `lib/contexto.ts`.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { conContexto, useContexto } from "@/lib/contexto";
import { saltosDe } from "@/lib/rutas";

export default function IrA({ esc, mes, dep, cta }: {
  /** El escenario que la pantalla está mostrando AHORA. */
  esc?: string;
  /** El mes, si la pantalla tiene uno. */
  mes?: number;
  /** El departamento, si la pantalla está parada en uno. */
  dep?: string;
  /** La cuenta del mayor, si la pantalla está parada en una. */
  cta?: string;
}) {
  const pathname = usePathname();
  const ctxUrl = useContexto();
  const t = useTranslations("ira");
  const ti = useTranslations("nav.items");
  const destinos = saltosDe(pathname);

  // Lo que la pantalla dice le gana a lo que diga la URL: la URL es de cuando
  // llegaste, la pantalla es de ahora.
  const ctx = { esc: esc ?? ctxUrl.esc, mes: mes ?? ctxUrl.mes,
                dep: dep ?? ctxUrl.dep, cta: cta ?? ctxUrl.cta };

  if (!destinos.length && !ctxUrl.de) return null;

  return (
    <nav aria-label={t("titulo")} style={{
      display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8,
      margin: "0 0 16px", padding: "9px 14px", borderRadius: 6,
      background: "var(--bg-surface)",
      border: "1px solid var(--border-medium)",
      // La franja de marca a la izquierda es lo que la hace encontrable. La
      // primera versión usaba `--border-subtle` sobre `--bg-surface` y el owner
      // no la vio: sobre una pantalla que ya tiene tablas, tarjetas y avisos,
      // un recuadro de bajo contraste arriba de todo se lee como separador.
      borderLeft: "3px solid var(--brand)",
      fontSize: 13,
    }}>
      {ctxUrl.de && (
        <>
          <Link href={ctxUrl.de} style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            color: "var(--text-primary)", textDecoration: "none", fontWeight: 700,
          }}>
            <span aria-hidden>‹</span>{t("volver")}
          </Link>
          {destinos.length > 0 && (
            <span aria-hidden style={{
              width: 1, height: 16, background: "var(--border-medium)", margin: "0 4px",
            }} />
          )}
        </>
      )}

      {destinos.length > 0 && (
        <span style={{
          // ⚠️ NO `--brand` como color de TEXTO. Se ve bien en los dos temas
          // claros y no llega al mínimo legible en los dos oscuros: 4.11:1 en
          // Grafito y 3.26:1 en Hoy, contra el 4.5:1 de WCAG. La marca se usa
          // acá para el borde y la franja izquierda, que son elementos de UI
          // (umbral 3:1) y sí lo pasan. Lo vigila `test_temas`.
          color: "var(--text-secondary)", fontWeight: 700,
          letterSpacing: 0.3, textTransform: "uppercase", fontSize: 11.5,
        }}>{t("titulo")}</span>
      )}

      {destinos.map(d => (
        <Link
          key={d.href}
          href={conContexto(d.href, ctx, d.lleva ?? ["esc", "mes", "dep"], pathname)}
          // El «por qué» va en el tooltip y no en el rótulo: son cinco destinos
          // en una línea, y cinco frases no se leen — se saltean.
          title={t(`porque.${d.porque}`)}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "5px 11px", borderRadius: 4, textDecoration: "none",
            fontWeight: 600,
            // Texto en el token probado; el color de marca vive en el borde.
            color: "var(--text-primary)",
            background: "var(--bg-base)",
            border: "1px solid var(--brand)",
          }}
        >
          {ti(d.item)}
          <span aria-hidden>›</span>
        </Link>
      ))}
    </nav>
  );
}
