import { redirect } from "next/navigation";

// La carga manual ahora vive dentro de Room Stats ("✏️ Cargar / Editar mes").
export default function RoomStatsEntryRedirect() {
  redirect("/operation-insight/room-stats");
}
