"use client";
/**
 * La pantalla que sale cuando una ruta revienta al dibujarse.
 *
 * Owner, 2026-09-03: *«Application error: a client-side exception has occurred
 * (see the browser console for more information)»* — la pantalla en blanco de
 * Next, que no dice ni qué pasó ni dónde.
 *
 * ## Por qué acá y no sólo alrededor de un cuadro
 *
 * Un `ErrorBoundary` puesto a mano sólo atrapa lo que tiene adentro. Si el
 * error ocurre en el CUERPO del componente —antes del JSX, cuando se calculan
 * los datos— o en cualquier otro rincón de la página, el árbol se cae igual y
 * Next muestra su pantalla genérica.
 *
 * `error.tsx` es el mecanismo del framework: envuelve **toda la ruta**, así que
 * no hay rincón que se le escape.
 *
 * ## Lo que muestra, y por qué importa
 *
 * ⚠️ **El mensaje del error, a la vista.** «Application error, see the browser
 * console» obliga a abrir las herramientas de desarrollo — algo que un
 * Financial Controller no tiene por qué hacer para reportar un problema. Con el
 * texto en pantalla, el mensaje se copia y se pega.
 *
 * Y dice lo que el usuario más necesita saber en ese momento: **que lo que
 * guardó se guardó**. El servidor ya contestó; lo que falló es el dibujo.
 */
import { useEffect } from "react";

export default function Error({ error, reset }: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[FinPlan] la pantalla se cayó al dibujarse:", error);
  }, [error]);

  const btn: React.CSSProperties = {
    padding: "7px 14px", fontSize: 13, fontWeight: 600, borderRadius: 6,
    cursor: "pointer", border: "1px solid var(--border-medium)",
    background: "var(--bg-surface)", color: "var(--text-primary)",
  };

  return (
    <div style={{ padding: "40px 28px", maxWidth: 820 }}>
      <h1 style={{ fontSize: 20, fontWeight: 800, marginBottom: 6,
                   color: "var(--negative)" }}>
        Esta pantalla no se pudo dibujar
      </h1>
      <p style={{ fontSize: 13.5, lineHeight: 1.65, color: "var(--text-secondary)",
                  marginBottom: 16 }}>
        <b>Lo que hayas guardado está guardado.</b> El servidor ya respondió; lo
        que falló fue el dibujo de la pantalla, así que no perdiste nada de lo
        que escribiste.
      </p>

      <div style={{
        padding: "10px 13px", borderRadius: 7, marginBottom: 16,
        border: "1px solid var(--border)",
        borderLeft: "4px solid var(--negative)",
        background: "var(--bg-surface)",
      }}>
        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: .4,
                      color: "var(--text-secondary)", marginBottom: 4 }}>
          QUÉ FALLÓ — copiá este texto y pasámelo
        </div>
        <div className="mono" style={{ fontSize: 12, lineHeight: 1.5,
                                       color: "var(--text-primary)",
                                       wordBreak: "break-word" }}>
          {error.message || String(error)}
        </div>
        {error.digest && (
          <div className="mono" style={{ fontSize: 10.5, marginTop: 5,
                                         color: "var(--text-disabled)" }}>
            digest: {error.digest}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button onClick={reset} style={{ ...btn, background: "var(--brand)",
                                         color: "#fff", border: "none" }}>
          Reintentar
        </button>
        <button onClick={() => history.back()} style={btn}>Volver</button>
      </div>
    </div>
  );
}
