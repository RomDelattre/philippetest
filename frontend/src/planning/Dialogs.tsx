import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Absence, AbsenceCategory, Technician } from "../api";
import { ABSENCE_LABELS } from "./layout";
import { techName } from "./Grid";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("input, select, button")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-md rounded-md bg-white p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-3 text-base font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

const btn = "rounded border px-3 py-1 text-sm";
export const primaryBtn = `${btn} border-sky-700 bg-sky-700 text-white hover:bg-sky-800 disabled:opacity-50`;
export const secondaryBtn = `${btn} border-slate-300 bg-white hover:bg-slate-50`;
export const dangerBtn = `${btn} border-red-300 text-red-700 hover:bg-red-50`;

export function ConfirmDialog(props: {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal title={props.title} onClose={props.onCancel}>
      <div className="text-sm text-slate-700">{props.message}</div>
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" className={secondaryBtn} onClick={props.onCancel}>
          Annuler
        </button>
        <button type="button" className={primaryBtn} onClick={props.onConfirm}>
          {props.confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

export interface AbsenceDraft {
  id?: string;
  version?: number;
  technician_id: string;
  start_date: string;
  end_date: string;
  category: AbsenceCategory;
}

/** F-31 : création, modification et suppression manuelles d'une absence. */
export function AbsenceDialog(props: {
  initial: AbsenceDraft;
  technicians: Technician[];
  onSave: (draft: AbsenceDraft) => Promise<string | null>;
  onDelete?: (absence: Absence) => Promise<string | null>;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(props.initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const editing = Boolean(draft.id);
  const invalid = !draft.start_date || !draft.end_date || draft.end_date < draft.start_date;

  const run = async (action: () => Promise<string | null>) => {
    setBusy(true);
    setError(await action());
    setBusy(false);
  };

  const field = "mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm";
  return (
    <Modal title={editing ? "Modifier l'absence" : "Nouvelle absence"} onClose={props.onClose}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!invalid) void run(() => props.onSave(draft));
        }}
      >
        <label className="block text-sm">
          Technicien
          <select className={field} value={draft.technician_id} onChange={(e) => setDraft({ ...draft, technician_id: e.target.value })}>
            {props.technicians.map((t) => (
              <option key={t.id} value={t.id}>
                {techName(t)}
              </option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Date de début
            <input type="date" required className={field} value={draft.start_date} onChange={(e) => setDraft({ ...draft, start_date: e.target.value })} />
          </label>
          <label className="block text-sm">
            Date de fin
            <input type="date" required className={field} value={draft.end_date} min={draft.start_date} onChange={(e) => setDraft({ ...draft, end_date: e.target.value })} />
          </label>
        </div>
        <label className="block text-sm">
          Catégorie
          <select className={field} value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value as AbsenceCategory })}>
            {(Object.keys(ABSENCE_LABELS) as AbsenceCategory[]).map((c) => (
              <option key={c} value={c}>
                {ABSENCE_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs text-slate-500">Seule la catégorie est conservée, jamais le motif.</p>
        {invalid && <p className="text-sm text-red-700">La date de fin doit être postérieure ou égale à la date de début.</p>}
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="flex items-center gap-2 pt-1">
          {editing && props.onDelete && (
            <button
              type="button"
              className={dangerBtn}
              disabled={busy}
              onClick={() => void run(() => props.onDelete!(draft as Absence))}
            >
              Supprimer
            </button>
          )}
          <span className="flex-1" />
          <button type="button" className={secondaryBtn} onClick={props.onClose}>
            Annuler
          </button>
          <button type="submit" className={primaryBtn} disabled={busy || invalid}>
            Enregistrer
          </button>
        </div>
      </form>
    </Modal>
  );
}
