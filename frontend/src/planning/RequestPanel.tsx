// F-14 : fiche détaillée d'une demande ; F-15 : fusion et division.
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type MissionType, type RequestDetail, type RequestFields, sendJson, type Vignette } from "../api";
import { addDays, formatDate } from "../dates";
import { ConfirmDialog, dangerBtn, primaryBtn, secondaryBtn } from "./Dialogs";
import { ASSIGNMENT_STATUS_LABELS, BADGE_LABELS, FIELD_LABELS, ORIGIN_LABELS, REQUEST_STATUS_LABELS } from "./layout";
import RequestForm, { formErrors } from "./RequestForm";

const ACTIONS: Record<string, string> = {
  "request.create": "Demande créée",
  "request.update": "Demande modifiée",
  "request.review": "Demande vérifiée",
  "request.merge": "Fusion (demande conservée)",
  "request.merged_into": "Fusionnée dans une autre demande",
  "request.split": "Demande divisée",
  "request.create_from_split": "Créée par division",
  "assignment.create": "Affectation créée",
  "assignment.move": "Affectation déplacée",
  "assignment.cancel": "Affectation retirée",
};

function toFields(d: RequestDetail): RequestFields {
  const { type_code, title, requester_name, requester_email, cf, client, location, objective, technicians_needed,
    start_date, end_date, date_flexible, flex_justification, comments, products, needed_by, attachment_url } = d;
  return { type_code, title, requester_name, requester_email, cf, client, location, objective, technicians_needed,
    start_date, end_date, date_flexible, flex_justification, comments, products, needed_by, attachment_url };
}

function dateTime(iso: string): string {
  const d = new Date(iso);
  return new Intl.DateTimeFormat("fr-BE", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Brussels" }).format(d);
}

export default function RequestPanel(props: {
  requestId: string;
  missionTypes: MissionType[];
  allRequests: () => Promise<Vignette[]>;
  onChanged: (message: string, openId?: string) => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [form, setForm] = useState<RequestFields | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [mergeOptions, setMergeOptions] = useState<Vignette[] | null>(null);
  const [mergeWith, setMergeWith] = useState("");
  const [splitDate, setSplitDate] = useState("");
  const [confirm, setConfirm] = useState<null | "merge" | "split">(null);

  const load = useCallback(async () => {
    try {
      const d = await api<RequestDetail>(`/requests/${props.requestId}`);
      setDetail(d);
      setForm(toFields(d));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chargement impossible.");
    }
  }, [props.requestId]);

  useEffect(() => {
    setDetail(null);
    setMergeOptions(null);
    setMergeWith("");
    setSplitDate("");
    void load();
  }, [load]);

  const run = async (action: () => Promise<RequestDetail | void>, message: string) => {
    setBusy(true);
    try {
      const result = await action();
      props.onChanged(message, result && result.id !== props.requestId ? result.id : undefined);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await load();
        setError("La demande a été modifiée entre-temps : elle a été rechargée.");
      } else setError(err instanceof Error ? err.message : "Action impossible.");
    }
    setBusy(false);
  };

  if (!detail || !form)
    return (
      <aside className="w-[400px] shrink-0 border-l border-slate-300 bg-white p-3" aria-label="Fiche de la demande">
        {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : <p className="text-sm text-slate-500">Chargement…</p>}
      </aside>
    );

  const locked = detail.cancelled_at !== null;
  const dirty = JSON.stringify(form) !== JSON.stringify(toFields(detail));
  const errors = formErrors(form);
  const changed = Object.fromEntries(
    Object.entries(form).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(toFields(detail)[k as keyof RequestFields])),
  );
  const canSplit = detail.start_date && detail.end_date && detail.start_date < detail.end_date;
  const otherRef = mergeOptions?.find((v) => v.id === mergeWith);

  return (
    <aside className="flex w-[400px] shrink-0 flex-col border-l border-slate-300 bg-white" aria-label="Fiche de la demande">
      <div className="flex items-start gap-2 border-b border-slate-200 p-3">
        <div className="flex-1">
          <div className="text-xs text-slate-500">
            {detail.ref} · {ORIGIN_LABELS[detail.origin]}
            {detail.confidence !== null && ` · confiance ${Math.round(detail.confidence * 100)} %`}
          </div>
          <h2 className="font-semibold">{detail.title || "Sans titre"}</h2>
          <div className="mt-1 flex flex-wrap gap-1 text-xs">
            <span className="rounded bg-slate-100 px-1.5 py-0.5">{REQUEST_STATUS_LABELS[detail.status]}</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5">
              {detail.remaining}/{detail.technicians_needed} technicien(s) à trouver
            </span>
            {detail.needs_review && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-900">⚑ À vérifier</span>}
            {detail.badges.map((b) => (
              <span key={b} className="rounded bg-orange-100 px-1.5 py-0.5 text-orange-900">! {BADGE_LABELS[b] ?? b}</span>
            ))}
          </div>
        </div>
        <button type="button" className={secondaryBtn} onClick={props.onClose} aria-label="Fermer la fiche">
          ✕
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-3 text-sm">
        {error && <p role="alert" className="rounded bg-red-50 p-2 text-red-800">{error}</p>}
        {detail.merged_into_ref && <p className="rounded bg-slate-100 p-2">Fusionnée dans {detail.merged_into_ref}.</p>}
        {locked && !detail.merged_into_ref && <p className="rounded bg-slate-100 p-2">Demande annulée : elle n'est plus modifiable.</p>}
        {detail.missing_fields.length > 0 && (
          <p className="rounded bg-slate-100 p-2">
            <strong>Informations manquantes :</strong> {detail.missing_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")}.
            Elles n'empêchent pas l'attribution.
          </p>
        )}
        {detail.needs_review && !locked && (
          <button
            type="button"
            className={secondaryBtn}
            disabled={busy}
            onClick={() =>
              void run(() => sendJson<RequestDetail>("PATCH", `/requests/${detail.id}`, { version: detail.version, needs_review: false }), "Demande marquée comme vérifiée.")
            }
          >
            ✓ Marquer comme vérifiée
          </button>
        )}

        <section>
          <h3 className="mb-1 font-medium">Affectations</h3>
          {detail.assignments.length === 0 ? (
            <p className="text-slate-500">Aucune. Glissez la vignette sur un technicien.</p>
          ) : (
            <ul className="space-y-1">
              {detail.assignments.map((a) => (
                <li key={a.id} className={`flex items-center gap-2 ${a.status === "cancelled" || a.status === "refused" ? "text-slate-400 line-through" : ""}`}>
                  <span className="flex-1">
                    {a.technician_name} · {formatDate(a.start_date)} → {formatDate(a.end_date)}
                  </span>
                  <span className="text-xs">{ASSIGNMENT_STATUS_LABELS[a.status]}</span>
                  {a.status === "draft" && (
                    <button
                      type="button"
                      className={`${dangerBtn} px-1.5 py-0 text-xs`}
                      disabled={busy}
                      onClick={() => void run(() => sendJson("DELETE", `/assignments/${a.id}?version=${a.version}`), "Affectation retirée.")}
                    >
                      Retirer
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {detail.pending_changes.length > 0 && (
          <section>
            <h3 className="mb-1 font-medium">Changements en attente</h3>
            <ul className="space-y-1">
              {detail.pending_changes.map((c) => (
                <li key={c.id} className="rounded bg-sky-50 p-1.5">
                  {c.kind === "cancellation" ? "⊘ Annulation demandée" : "✎ Modification proposée"} le {dateTime(c.created_at)}
                  {c.kind === "modification" && (
                    <span className="block text-xs text-slate-600">
                      {Object.entries(c.proposed_changes).map(([k, v]) => `${FIELD_LABELS[k] ?? k} : ${String(v)}`).join(" ; ")}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (dirty && errors.length === 0)
              void run(
                () => sendJson<RequestDetail>("PATCH", `/requests/${detail.id}`, { version: detail.version, ...changed }),
                "Demande enregistrée.",
              );
          }}
        >
          <h3 className="font-medium">Informations</h3>
          <fieldset disabled={locked} className="space-y-2">
            <RequestForm value={form} onChange={setForm} missionTypes={props.missionTypes} missing={detail.missing_fields} />
          </fieldset>
          {detail.assignments.some((a) => a.status !== "cancelled" && a.status !== "refused") &&
            (changed.start_date !== undefined || changed.end_date !== undefined) && (
              <p className="text-xs text-amber-800">Les affectations existantes gardent leurs dates : déplacez-les sur le planning si besoin.</p>
            )}
          {errors.map((e) => (
            <p key={e} className="text-xs text-red-700">{e}</p>
          ))}
          {!locked && (
            <div className="flex justify-end gap-2">
              <button type="button" className={secondaryBtn} disabled={!dirty} onClick={() => setForm(toFields(detail))}>
                Annuler les changements
              </button>
              <button type="submit" className={primaryBtn} disabled={!dirty || errors.length > 0 || busy}>
                Enregistrer
              </button>
            </div>
          )}
        </form>

        {!locked && (
          <section className="space-y-2 rounded border border-slate-200 p-2">
            <h3 className="font-medium">Fusion et division</h3>
            <div className="flex items-end gap-2">
              <label className="flex-1 text-xs text-slate-600">
                Fusionner avec (l'autre demande sera absorbée)
                <select
                  className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  value={mergeWith}
                  onFocus={() => !mergeOptions && props.allRequests().then(setMergeOptions, () => setMergeOptions([]))}
                  onChange={(e) => setMergeWith(e.target.value)}
                >
                  <option value="">— choisir —</option>
                  {(mergeOptions ?? [])
                    .filter((v) => v.id !== detail.id && v.status !== "cancelled")
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.ref} – {v.title || "Sans titre"}
                        {v.start_date ? ` (${formatDate(v.start_date)})` : ""}
                      </option>
                    ))}
                </select>
              </label>
              <button type="button" className={secondaryBtn} disabled={!mergeWith || busy} onClick={() => setConfirm("merge")}>
                Fusionner
              </button>
            </div>
            <div className="flex items-end gap-2">
              <label className="flex-1 text-xs text-slate-600">
                Diviser : la seconde partie commence le
                <input
                  type="date"
                  className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  disabled={!canSplit}
                  min={detail.start_date ? addDays(detail.start_date, 1) : undefined}
                  max={detail.end_date ?? undefined}
                  value={splitDate}
                  onChange={(e) => setSplitDate(e.target.value)}
                />
              </label>
              <button type="button" className={secondaryBtn} disabled={!canSplit || !splitDate || busy} onClick={() => setConfirm("split")}>
                Diviser
              </button>
            </div>
            {!canSplit && <p className="text-xs text-slate-500">La division demande une période d'au moins deux jours.</p>}
          </section>
        )}

        {detail.sources.length > 0 && (
          <section>
            <h3 className="mb-1 font-medium">Messages sources</h3>
            <ul className="space-y-1">
              {detail.sources.map((s) => (
                <li key={s.id}>
                  {dateTime(s.received_at)} · {s.sender ?? "?"} ·{" "}
                  {s.web_link ? (
                    <a className="text-sky-700 underline" href={s.web_link} target="_blank" rel="noreferrer">
                      {s.subject || "message"}
                    </a>
                  ) : (
                    (s.subject ?? "message")
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h3 className="mb-1 font-medium">Historique</h3>
          <ul className="space-y-0.5 text-xs text-slate-600">
            {detail.history.map((h, i) => (
              <li key={i}>
                <span className="tabular-nums">{dateTime(h.created_at)}</span> · {ACTIONS[h.action] ?? h.action} ·{" "}
                {h.actor.replace(/^user:/, "")}
                {h.entity_type === "assignments" && h.after?.start_date
                  ? ` (${formatDate(String(h.after.start_date))} → ${formatDate(String(h.after.end_date))})`
                  : ""}
              </li>
            ))}
          </ul>
        </section>
      </div>

      {confirm === "merge" && otherRef && (
        <ConfirmDialog
          title="Fusionner les deux demandes ?"
          message={
            <p>
              {detail.ref} est conservée. {otherRef.ref} sera annulée ; ses messages et ses affectations en cours sont
              rattachés à {detail.ref}, et ses informations complètent les champs vides.
            </p>
          }
          confirmLabel="Fusionner"
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            setConfirm(null);
            void run(
              () =>
                sendJson<RequestDetail>("POST", `/requests/${detail.id}/merge`, {
                  version: detail.version,
                  other_id: otherRef.id,
                  other_version: otherRef.version,
                }),
              `${otherRef.ref} fusionnée dans ${detail.ref}.`,
            );
            setMergeWith("");
            setMergeOptions(null);
          }}
        />
      )}
      {confirm === "split" && (
        <ConfirmDialog
          title="Diviser la demande ?"
          message={
            <p>
              {detail.ref} couvrira du {formatDate(detail.start_date!)} au {formatDate(addDays(splitDate, -1))}. Une nouvelle
              demande couvrira du {formatDate(splitDate)} au {formatDate(detail.end_date!)}. Les affectations à cheval sont
              coupées en deux, sans nouveau mail.
            </p>
          }
          confirmLabel="Diviser"
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            setConfirm(null);
            void run(
              () => sendJson<RequestDetail>("POST", `/requests/${detail.id}/split`, { version: detail.version, split_date: splitDate }),
              "Demande divisée : la nouvelle partie est ouverte.",
            );
          }}
        />
      )}
    </aside>
  );
}
