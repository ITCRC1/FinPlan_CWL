"use client";
//
// Guillermo — el gato (`docs/GUILLERMO.md` §10.2).
//
// ⚠️ **Su permanencia ES la alerta.** No necesita texto: si hay pendientes se
// sienta y se queda hasta que resuelvas; si está trabado, además mueve la cola
// rápido y baja las orejas. Ese contraste tiene que distinguirse **de reojo**,
// sin leer el header.
//
// ⚠️ **El estado SIEMPRE viene del backend** (§10.2.7). El componente no
// infiere ni recuerda nada: si la UI y la base discrepan, gana la base.
//
// ⚠️ **No es el único canal.** La misma información vive en el header y en el
// correo. El gato es el recordatorio, no el sistema de alertas — si alguien lo
// apaga, no se pierde ninguna advertencia.
//
import { useCallback, useEffect, useRef, useState } from "react";

// Dónde quedó la última vez que alguien lo corrió de lugar. Es preferencia de
// quien mira, no dato del sistema: va en el navegador, no en la base.
const DONDE = "guillermo_pos";

// El alto y ancho reales del dibujo, para no dejarlo salir de la pantalla.
const ANCHO = 170;
const ALTO = 125;

// Cuánto hay que mover el ratón antes de que deje de ser un clic y pase a ser
// un arrastre. Sin este umbral, un clic con la mano temblorosa movería al gato
// en vez de abrir la pantalla — y el clic es lo que hacen todos los días.
const UMBRAL = 4;

// ⚠️ `off` es un estado NUEVO, y hace falta. «Nunca arrancó» no es «trabado»
// —marcarlo rojo haría gritar a un Guillermo recién instalado desde el día
// cero, y una alarma que suena siempre se aprende a ignorar— pero tampoco es
// «al día». En `off` el gato NO aparece; el aviso vive en la pantalla.
export type GuillermoState = "off" | "idle" | "running" | "pending" | "stuck";

export interface GuillermoProps {
  state: GuillermoState;
  pendingCount?: number;
  onClick?: () => void;
  playIntro?: boolean;
  /**
   * ⚠️ La caja de muestra de `Admin → Guillermo` lo monta en `false`.
   * El componente es `position: fixed`: si el de la muestra leyera la posición
   * guardada, se saldría de su caja y aparecería flotando sobre la pantalla —
   * dos gatos a la vez, y uno de ellos mintiendo sobre dónde está el de verdad.
   */
  arrastrable?: boolean;
}

/** Que no se pueda dejar fuera de la pantalla, ni al soltarlo ni al achicar la
 *  ventana. Un gato arrastrado al borde y perdido no se recupera con nada. */
function dentro(x: number, y: number): { x: number; y: number } {
  if (typeof window === "undefined") return { x, y };
  return {
    x: Math.max(0, Math.min(x, window.innerWidth - ANCHO)),
    y: Math.max(0, Math.min(y, window.innerHeight - ALTO)),
  };
}

// §10.2.2 — en variables CSS para poder alinearlas al tema sin tocar el SVG.
// Sin contornos negros duros: el gato no debe competir con los datos.
const PALETA = `
  .gm { --fur:#A9B2B9; --fur-dark:#5E6A73; --fur-light:#E3E8EB;
        --ear:#F4B8C1; --eye:#5FC2D1; --ink:#2E3941; }
`;

// La secuencia de entrada del §10.2.3: se asoma, se esconde, se asoma más y
// sale caminando. Los tiempos son los de la tabla del spec.
const ENTRADA: [number, number, number][] = [
  //  t(ms)  x(px)   duración(ms)
  [400, -118, 550],
  [1300, -180, 450],
  [2000, -88, 600],
  [3100, -180, 400],
  [3800, 120, 2600],
];

export default function Guillermo({
  state, pendingCount = 0, onClick, playIntro = false, arrastrable = true,
}: GuillermoProps) {
  const [x, setX] = useState(-180);
  const [ms, setMs] = useState(0);
  const [visible, setVisible] = useState(false);

  // ── Moverlo de lugar (pedido del owner, 2026-08-20) ──────────────────────
  //
  // «A veces está detrás de cálculos y datos y hay que moverlo.» Con
  // `position: fixed` y un solo lugar posible, la única salida era apagarlo —
  // y apagarlo pierde el aviso.
  //
  // ⚠️ **La posición se RECUERDA.** Si volviera al rincón de siempre en cada
  // recarga, moverlo no resolvería nada: habría que moverlo otra vez, y otra.
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const [agarrado, setAgarrado] = useState(false);
  const caja = useRef<HTMLDivElement | null>(null);
  const arrastre = useRef<{
    px: number; py: number; ox: number; oy: number; movido: boolean;
  } | null>(null);

  useEffect(() => {
    if (!arrastrable || typeof window === "undefined") return;
    try {
      const guardado = localStorage.getItem(DONDE);
      if (guardado) {
        const { x: gx, y: gy } = JSON.parse(guardado);
        if (typeof gx === "number" && typeof gy === "number") setPos(dentro(gx, gy));
      }
    } catch {
      // Un valor corrupto en localStorage no puede dejar sin gato a nadie.
    }
  }, [arrastrable]);

  // ⚠️ Al achicar la ventana, una posición vieja puede quedar fuera de la
  // pantalla. Se vuelve a meter adentro; si no, el gato desaparece y no hay
  // forma de traerlo de vuelta.
  useEffect(() => {
    if (!pos) return;
    const alCambiar = () => setPos(p => (p ? dentro(p.x, p.y) : p));
    window.addEventListener("resize", alCambiar);
    return () => window.removeEventListener("resize", alCambiar);
  }, [pos]);

  const agarrar = useCallback((ev: React.PointerEvent) => {
    if (!arrastrable) return;
    const r = caja.current?.getBoundingClientRect();
    if (!r) return;
    ev.preventDefault();
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
    arrastre.current = { px: ev.clientX, py: ev.clientY,
                         ox: r.left, oy: r.top, movido: false };
    setAgarrado(true);
  }, [arrastrable]);

  const mover = useCallback((ev: React.PointerEvent) => {
    const a = arrastre.current;
    if (!a) return;
    const dx = ev.clientX - a.px;
    const dy = ev.clientY - a.py;
    if (!a.movido && Math.abs(dx) < UMBRAL && Math.abs(dy) < UMBRAL) return;
    a.movido = true;
    setPos(dentro(a.ox + dx, a.oy + dy));
  }, []);

  const soltar = useCallback((ev: React.PointerEvent, alClic?: () => void) => {
    const a = arrastre.current;
    arrastre.current = null;
    setAgarrado(false);
    (ev.target as Element).releasePointerCapture?.(ev.pointerId);
    if (!a) return;
    if (a.movido) {
      // ⚠️ Se guarda al SOLTAR, no en cada píxel: escribir en localStorage en
      // cada `pointermove` son cientos de escrituras por arrastre.
      try {
        const r = caja.current?.getBoundingClientRect();
        if (r) localStorage.setItem(DONDE, JSON.stringify({ x: r.left, y: r.top }));
      } catch { /* sin persistencia, pero movido igual */ }
      return;
    }
    alClic?.();            // No se movió: era un clic.
  }, []);

  // Doble clic lo devuelve a su lugar de siempre. Es la salida para quien lo
  // arrastró sin querer y no sabe dónde lo dejó.
  const devolver = useCallback(() => {
    if (!arrastrable) return;
    try { localStorage.removeItem(DONDE); } catch { /* nada */ }
    setPos(null);
  }, [arrastrable]);

  // ⚠️ `prefers-reduced-motion`: sin caminata ni entrada. Aparece y desaparece
  // con fade. No es un detalle estético — una animación que cruza la pantalla
  // puede marear a quien la tiene activada.
  const [reducido, setReducido] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducido(mq.matches);
    const on = () => setReducido(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  useEffect(() => {
    // «Nada que reportar» → no aparece. Duerme.
    // `off` tampoco: todavía no lo encendieron, no hay nada que alertar.
    if (state === "idle" || state === "off") { setVisible(false); return; }
    setVisible(true);

    // ⚠️ Si alguien lo movió, la caminata NO corre. Un gato que camina hacia
    // su rincón de siempre después de que lo pusiste en otro lado es un gato
    // que ignora lo que le pediste.
    if (pos) { setMs(0); return; }

    if (reducido) { setX(state === "running" ? 120 : 24); setMs(0); return; }

    const quieto = state === "pending" || state === "stuck";
    if (!playIntro) {
      // Rondas posteriores del mismo día: entra directo al estado que toca.
      setMs(2200);
      setX(quieto ? 24 : 120);
      return;
    }
    const timers = ENTRADA.map(([t, destino, dur]) =>
      window.setTimeout(() => { setMs(dur); setX(destino); }, t));
    // A los 6500 adopta el estado real.
    timers.push(window.setTimeout(() => {
      setMs(600); setX(quieto ? 24 : 120);
    }, 6500));
    return () => timers.forEach(clearTimeout);
  }, [state, playIntro, reducido, pos]);

  if (!visible) return null;

  const sentado = state === "pending" || state === "stuck";
  const trabado = state === "stuck";
  // §10.2.4 — la cola es el diferencial que se ve de reojo.
  const colaSeg = trabado ? 0.34 : sentado ? 1.4 : 3.2;
  const clickeable = sentado && !!onClick;

  return (
    <>
      <style>{PALETA}{`
        @keyframes gm-cola { 0%,100%{transform:rotate(-8deg)} 50%{transform:rotate(14deg)} }
        @keyframes gm-bob  { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-3px)} }
        @keyframes gm-pata { 0%,100%{transform:rotate(14deg)} 50%{transform:rotate(-14deg)} }
        @keyframes gm-parp { 0%,92%,100%{transform:scaleY(0)} 95%{transform:scaleY(1)} }
        @media (prefers-reduced-motion: reduce) {
          .gm *, .gm { animation: none !important; }
        }
      `}</style>

      <div
        className="gm"
        ref={caja}
        onDoubleClick={devolver}

        style={{
          position: "fixed", zIndex: 40, width: ANCHO,
          // Movido: manda la posición elegida. Sin mover: el rincón de siempre.
          ...(pos
            ? { left: pos.x, top: pos.y, transform: "none" }
            : { left: 0, bottom: 26, transform: `translateX(${x}px)` }),
          transition: pos || agarrado
            ? "none"
            : `transform ${ms}ms ${ms > 2000 ? "linear" : "ease-out"}`,
          willChange: "transform",
          // ⚠️ **El contenedor NO recibe clics, ni siquiera ahora que se
          // arrastra.** Es una caja de 170×125 y casi todo es aire: si tomara
          // los eventos, se comería los clics de la tabla que tiene debajo —
          // que es justamente de lo que se está quejando el owner. Los eventos
          // van sobre las FIGURAS del SVG, que es donde está el gato.
          pointerEvents: "none",
          touchAction: "none",
        }}
      >
        <svg viewBox="0 0 175 125" width={ANCHO} role="img"
             style={{ display: "block", overflow: "visible",
                      pointerEvents: "none" }}>
          <g
            onPointerDown={agarrar}
            onPointerMove={mover}
            onPointerUp={ev => soltar(ev, clickeable ? onClick : undefined)}
            onPointerCancel={ev => soltar(ev)}
            style={{
              // Acá sí: el SVG resuelve el impacto figura por figura, así que
              // sólo el dibujo del gato agarra el ratón. El aire, no.
              pointerEvents: "auto",
              cursor: agarrado ? "grabbing" : arrastrable ? "grab"
                : clickeable ? "pointer" : "default",
              // Sin esto, en una pantalla táctil el arrastre lo interpreta el
              // navegador como scroll y el gato no se mueve.
              touchAction: "none",
            }}
          >
            {/* ⚠️ El tooltip va ACÁ, no en el contenedor: el contenedor tiene
                `pointer-events: none` a propósito, así que un `title` suyo no
                se mostraría nunca. Y que se pueda arrastrar hay que DECIRLO —
                una función que nadie descubre es una función que no existe, y
                el owner venía tapado por el gato sin saber que podía correrlo. */}
            <title>
              {[
                trabado ? "Guillermo está trabado — no se va solo"
                  : sentado ? `${pendingCount} pendientes esperándote`
                    : "Guillermo pasó por acá",
                arrastrable
                  ? "Arrastralo para moverlo · doble clic lo devuelve a su lugar"
                  : "",
              ].filter(Boolean).join(" — ")}
            </title>
          <g style={{
            animation: sentado || reducido ? undefined : "gm-bob .42s infinite",
            transform: sentado ? "translateY(6px) scaleY(0.9)" : undefined,
            transformOrigin: "80px 100px",
            transition: "transform 350ms",
          }}>
            {/* cola */}
            <path d="M36 74 C10 70 6 44 26 34" fill="none" stroke="var(--fur)"
                  strokeWidth="9" strokeLinecap="round"
                  style={{
                    transformOrigin: "36px 74px",
                    animation: reducido ? undefined
                      : `gm-cola ${colaSeg}s ease-in-out infinite`,
                  }} />
            {/* cuerpo */}
            <ellipse cx="80" cy="72" rx="46" ry="27" fill="var(--fur)" />
            <ellipse cx="86" cy="80" rx="34" ry="17" fill="var(--fur-light)" />
            <path d="M58 52 q10 8 20 0 M84 50 q10 8 20 0" fill="none"
                  stroke="var(--fur-dark)" strokeWidth="4" strokeLinecap="round" />
            {/* patas */}
            {[62, 78, 96, 112].map((px, i) => (
              <rect key={px} x={px} y="88" width="9" height="20" rx="4"
                    fill="var(--fur-light)"
                    style={{
                      transformOrigin: `${px + 4}px 90px`,
                      animation: sentado || reducido ? undefined
                        : `gm-pata .42s ${i % 2 ? ".21s" : "0s"} infinite`,
                    }} />
            ))}
            {/* cabeza */}
            <g style={{
              transform: trabado ? "rotate(-16deg) translateY(3px)" : undefined,
              transformOrigin: "118px 44px", transition: "transform 300ms",
            }}>
              <path d="M104 30 l8 -20 l14 14 z" fill="var(--fur)" />
              <path d="M106 28 l6 -13 l9 9 z" fill="var(--ear)" />
              <path d="M140 30 l14 -16 l4 20 z" fill="var(--fur)" />
              <path d="M142 29 l9 -10 l3 13 z" fill="var(--ear)" />
              <circle cx="128" cy="46" r="24" fill="var(--fur)" />
              <ellipse cx="132" cy="54" rx="15" ry="11" fill="var(--fur-light)" />
              {/* ojos: turquesa, según la referencia aprobada */}
              {[121, 139].map((cx) => (
                <g key={cx}>
                  <ellipse cx={cx} cy="43" rx="5" ry="6" fill="var(--eye)" />
                  <ellipse cx={cx} cy="43" rx="2" ry="5" fill="var(--ink)" />
                  <rect x={cx - 5} y="37" width="10" height="12" fill="var(--fur)"
                        style={{
                          transformOrigin: `${cx}px 37px`,
                          animation: reducido ? undefined : "gm-parp 5.5s infinite",
                        }} />
                </g>
              ))}
              <path d="M128 54 l-4 3 h8 z" fill="var(--ear)" />
              <path d="M128 58 q-5 5 -9 1 M128 58 q5 5 9 1" fill="none"
                    stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" />
            </g>
          </g>
          </g>
        </svg>

        {sentado && (
          <div
            onPointerDown={agarrar}
            onPointerMove={mover}
            onPointerUp={ev => soltar(ev, clickeable ? onClick : undefined)}
            onPointerCancel={ev => soltar(ev)}
            style={{
            // El globito es sólido y está justo donde uno agarra: si no
            // recibiera eventos, agarrarlo de ahí no haría nada.
            pointerEvents: "auto",
            cursor: agarrado ? "grabbing" : "grab",
            position: "absolute", left: 96, top: -6, padding: "2px 9px",
            borderRadius: 11, fontSize: 12, fontWeight: 700,
            background: trabado ? "var(--negative)" : "var(--warning, #B8860B)",
            color: "#fff", whiteSpace: "nowrap",
          }}>
            {trabado ? "trabado" : pendingCount}
          </div>
        )}
      </div>
    </>
  );
}
