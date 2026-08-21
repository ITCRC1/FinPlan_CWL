"use client";
/**
 * Master Data → Canales. **La pantalla vive en `components/MixerCanales`.**
 *
 * Owner, 2026-08-17: *«yo traería el mixer para acá… abro su sub-tab y ahí hago…
 * y para no mover nada de las conexiones, solo trae el número acá»*.
 *
 * El mixer se planifica ahora desde **Planning → Sales Channels**, que es donde
 * se ve su resultado. Esta ruta se deja montando el mismo componente para no
 * romper enlaces ni la costumbre de nadie: es la MISMA pantalla, no una copia.
 * Duplicarla habría sido garantizar que las dos se separen.
 */
import IrA from "@/components/IrA";
import MixerCanales from "@/components/MixerCanales";

export default function CanalesPage() {
  // ⚠️ La barra va ACÁ y no adentro de `MixerCanales`. El componente lo montan
  // DOS rutas —esta y Planning → Sales Channels— y aquélla ya tiene la suya:
  // ponerla adentro le pondría dos a una de las dos. Que cada ruta monte su
  // barra también es lo correcto de fondo: `IrA` resuelve sus destinos por
  // `pathname`, así que desde acá y desde allá las preguntas son distintas.
  //
  // Sin `esc`: el mixer maneja el escenario compartido de Planning por dentro,
  // y esta página no lo ve. El que venga en la dirección se propaga igual.
  return (
    <>
      <div className="pag pag-ancha" style={{ paddingTop: 16 }}>
        <IrA />
      </div>
      <MixerCanales />
    </>
  );
}
