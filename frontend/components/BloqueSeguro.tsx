"use client";
/**
 * Un cuadro que no se lleva la pantalla puesta si revienta.
 *
 * Owner, 2026-09-03: *«cuando doy guardar y recalcular me saca de la pantalla y
 * me da error»* — la pantalla en blanco de Next, «application error: a
 * client-side exception has occurred».
 *
 * ## Por qué existe
 *
 * En React, una excepción al dibujar **desmonta el árbol entero**. Una pantalla
 * como la de repartos tiene cinco o seis cuadros de validación, cada uno
 * leyendo un pedazo distinto de la respuesta; que uno solo se rompa por un
 * departamento que no está en el catálogo, o por una llave que llegó vacía,
 * deja al usuario sin la pantalla y **sin la configuración que acababa de
 * escribir**.
 *
 * Envolviendo cada cuadro, el que falla se convierte en un aviso y los demás
 * siguen dibujándose. La configuración se salvó igual —el backend contestó
 * 200— y ahora se puede seguir trabajando.
 *
 * ⚠️ **Esto NO tapa el error: lo muestra.** El mensaje sale en pantalla con el
 * nombre del bloque, que es más de lo que decía la pantalla en blanco. Un
 * bloque en gris con su motivo es una pista; un `Application error` sin más es
 * un callejón.
 *
 * Tiene que ser una CLASE: `componentDidCatch` no existe en los hooks, y es la
 * única forma que da React de atrapar un error de render.
 */
import React from "react";

type Props = { nombre: string; children: React.ReactNode };
type State = { error: Error | null };

export default class BloqueSeguro extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error) {
    // Queda en la consola con el nombre del bloque: sin esto habría que
    // adivinar cuál de los seis cuadros fue.
    console.error(`[BloqueSeguro] «${this.props.nombre}» falló al dibujar:`, error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{
        marginTop: 20, padding: "12px 14px", borderRadius: 8,
        border: "1px solid var(--border)",
        borderLeft: "4px solid var(--negative)",
        fontSize: 12.5, lineHeight: 1.6, color: "var(--text-secondary)",
      }}>
        <b style={{ color: "var(--negative)" }}>
          No se pudo dibujar «{this.props.nombre}».
        </b>{" "}
        El resto de la pantalla sigue funcionando y{" "}
        <b>lo que guardaste se guardó</b> — esto es sólo el cuadro de
        validación.
        <div className="mono" style={{ marginTop: 6, fontSize: 11,
                                       color: "var(--text-disabled)" }}>
          {this.state.error.message || String(this.state.error)}
        </div>
      </div>
    );
  }
}
