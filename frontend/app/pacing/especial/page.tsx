"use client";
import { Suspense } from "react";
import { PacingShell } from "@/components/pacing/comun";
import { AnalisisEspecial } from "@/components/pacing/especial";

export default function PacingPage() {
  return (
    <PacingShell tab="especial">
      <Suspense fallback={null}><AnalisisEspecial /></Suspense>
    </PacingShell>
  );
}
