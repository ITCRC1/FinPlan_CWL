"use client";
//
// Los doce meses, desplegados, para marcar los que salen.
//
// Owner, 2026-08-20: «que los meses estén desplegados y yo escojo los que
// quiero que salgan». Antes había un desplegable de UN mes, así que pedir
// «junio y julio» era imposible.
//
// ⚠️ **Vive en un componente y no copiado en cada pantalla.** Lo usan el
// Resumen de costos y la Propuesta de descuentos, y dos copias de un selector
// terminan divergiendo sin que nada falle: cada pantalla filtra distinto y las
// dos parecen correctas.
//
const MES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

export interface MesesElegidosProps {
  meses: number[];
  onChange: (m: number[]) => void;
  /** Se llama al pedir YTD; la pantalla decide cómo resolverlo. */
  onYtd?: () => void;
}

export default function MesesElegidos({ meses, onChange, onYtd }: MesesElegidosProps) {
  const marcado = (m: number) => meses.includes(m);
  const alternar = (m: number) =>
    onChange(marcado(m) ? meses.filter(x => x !== m) : [...meses, m].sort((a, b) => a - b));

  const chip = (activo: boolean): React.CSSProperties => ({
    padding: "3px 9px", borderRadius: 13, fontSize: 12, cursor: "pointer",
    border: `1px solid ${activo ? "var(--positive)" : "var(--border)"}`,
    background: activo ? "var(--positive)" : "transparent",
    color: activo ? "#fff" : "var(--text-secondary)",
    fontWeight: activo ? 700 : 400,
  });

  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
      {/* ⚠️ «Todos» LIMPIA la selección en vez de marcar los doce: marcados,
          cualquier mes que se agregue al calendario quedaría afuera sin que
          nadie lo note. Sin marcas, manda el período. */}
      <button type="button" style={chip(meses.length === 0)}
              onClick={() => onChange([])}
              title="Sin meses marcados: manda el período">
        Todo el año
      </button>
      {onYtd && (
        <button type="button" style={chip(false)} onClick={onYtd}
                title="Marca los meses transcurridos según el corte del escenario">
          YTD
        </button>
      )}
      <span style={{ color: "var(--border)", margin: "0 2px" }}>|</span>
      {MES.slice(1).map((nombre, i) => (
        <button key={nombre} type="button" style={chip(marcado(i + 1))}
                onClick={() => alternar(i + 1)}>
          {nombre}
        </button>
      ))}
    </div>
  );
}
