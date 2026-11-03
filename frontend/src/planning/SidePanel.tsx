// F-05 : fiche de l'activité dans un panneau latéral. La fiche complète de la demande (F-14) vient en phase 2.
import { useEffect, useState } from "react";
import type { Assignment, MissionType, RequestSummary, Technician } from "../api";
import { formatDate, periodDays } from "../dates";
import { dangerBtn, primaryBtn, secondaryBtn } from "./Dialogs";
import { techName } from "./Grid";
import { ASSIGNMENT_STATUS_LABELS, type Period } from "./layout";

function dateTime(iso: string): string {
  return new Intl.DateTimeFormat("fr-BE", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Brussels" }).format(
    new Date(iso),
  );
}

const REQUEST_STATUS: Record<RequestSummary["status"], string> = {
  to_assign: "À attribuer",
  partially_assigned: "Partiellement attribuée",
  pending: "En attente de réponse",
  confirmed: "Confirmée",
  cancelled: "Annulée",
};

export default function SidePanel(props: {
  assignment: Assignment;
  request: RequestSummary | undefined;
  type: MissionType | undefined;
  technicians: Map<string, Technician>;
  mechanics: Technician[];
  onSave: (period: Period) => void;
  onClose: () => void;
  onOpenRequest: (requestId: string) => void;
  onRespond: (answer: "accept" | "refuse") => void;
  onCancel: () => void;
}) {
  const { assignment: a, request: r } = props;
  const [form, setForm] = useState<Period>({ technicianId: a.technician_id, start: a.start_date, end: a.end_date });
  useEffect(
    () => setForm({ technicianId: a.technician_id, start: a.start_date, end: a.end_date }),
    [a.id, a.technician_id, a.start_date, a.end_date],
  );
  const changed = form.technicianId !== a.technician_id || form.start !== a.start_date || form.end !== a.end_date;
  const invalid = !form.start || !form.end || form.end < form.start;
  const partner = a.partner_electronician_id ? props.technicians.get(a.partner_electronician_id) : undefined;
  const field = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";

  const rows: [string, string | null | undefined][] = [
    ["Type", r?.type_code ? `${r.type_code} – ${props.type?.label ?? ""}` : "Non défini"],
    ["Demandeur", r?.requester_name],
    ["Client", r?.client],
    ["Lieu", r?.location],
    ["CF", r?.cf],
    ["Demande", r?.start_date && r.end_date ? `du ${formatDate(r.start_date)} au ${formatDate(r.end_date)}` : "dates non renseignées"],
    ["Techniciens demandés", r ? String(r.technicians_needed) : null],
    ["Statut de la demande", r ? REQUEST_STATUS[r.status] : null],
    ["Binôme électronicien", partner ? techName(partner) : null],
  ];

  return (
    <aside className="flex w-[360px] shrink-0 flex-col border-l border-slate-300 bg-white" aria-label="Détail de l'activité">
      <div className="flex items-start gap-2 border-b border-slate-200 p-3">
        <div className="flex-1">
          <div className="text-xs text-slate-500">{r?.ref}</div>
          <h2 className="font-semibold">{r?.title || "Activité"}</h2>
          <div className="mt-1 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-xs">{ASSIGNMENT_STATUS_LABELS[a.status]}</div>
        </div>
        <button type="button" className={secondaryBtn} onClick={props.onClose} aria-label="Fermer le panneau">
          ✕
        </button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-3 text-sm">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          {rows
            .filter(([, v]) => v)
            .map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-slate-500">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
        </dl>
        <button type="button" className={secondaryBtn} onClick={() => props.onOpenRequest(a.request_id)}>
          Ouvrir la fiche de la demande
        </button>

        <section className="space-y-2 rounded border border-slate-200 p-2" aria-label="Réponse du technicien">
          <h3 className="font-medium">Proposition</h3>
          <p className="text-xs text-slate-600">
            {a.status === "draft" && "Brouillon : le mail au technicien attend votre validation."}
            {a.status === "pending_response" &&
              `Envoyée${a.proposed_at ? ` le ${dateTime(a.proposed_at)}` : ""}${a.token_expires_at ? ` · lien valable jusqu'au ${dateTime(a.token_expires_at)}` : ""}.`}
            {a.status === "accepted" && `Acceptée${a.responded_at ? ` le ${dateTime(a.responded_at)}` : ""}.`}
          </p>
          {(a.status === "draft" || a.status === "pending_response") && (
            <div className="flex flex-wrap gap-2">
              <span className="w-full text-xs text-slate-500">Réponse reçue autrement (téléphone, oral) :</span>
              <button type="button" className={secondaryBtn} onClick={() => props.onRespond("accept")}>
                ✓ Accepte
              </button>
              <button type="button" className={secondaryBtn} onClick={() => props.onRespond("refuse")}>
                ✕ Refuse
              </button>
            </div>
          )}
          <button type="button" className={dangerBtn} onClick={props.onCancel}>
            {a.status === "draft" ? "Retirer l'affectation" : "Annuler la proposition"}
          </button>
        </section>

        <form
          className="space-y-2 rounded border border-slate-200 p-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (changed && !invalid) props.onSave(form);
          }}
        >
          <h3 className="font-medium">Affectation</h3>
          <label className="block">
            Technicien
            <select className={field} value={form.technicianId} onChange={(e) => setForm({ ...form, technicianId: e.target.value })}>
              {props.mechanics.map((t) => (
                <option key={t.id} value={t.id}>
                  {techName(t)}
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              Début
              <input type="date" className={field} value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />
            </label>
            <label className="block">
              Fin
              <input type="date" className={field} value={form.end} min={form.start} onChange={(e) => setForm({ ...form, end: e.target.value })} />
            </label>
          </div>
          {!invalid && <p className="text-xs text-slate-500">{periodDays(form.start, form.end)} jour(s) calendaire(s)</p>}
          {invalid && <p className="text-xs text-red-700">La date de fin doit être postérieure ou égale à la date de début.</p>}
          <div className="flex justify-end">
            <button type="submit" className={primaryBtn} disabled={!changed || invalid}>
              Enregistrer
            </button>
          </div>
        </form>
      </div>
    </aside>
  );
}
