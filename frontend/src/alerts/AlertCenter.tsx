// F-40 à F-43 : centre d'alertes (cloche), réponses des techniciens et paramètres d'alerte.
import { useEffect, useRef, useState } from "react";
import { api, type Alert, type AlertSettings, type AppNotification, sendJson } from "../api";
import { formatDate } from "../dates";
import { Modal, primaryBtn, secondaryBtn } from "../planning/Dialogs";

function dateTime(iso: string): string {
  return new Intl.DateTimeFormat("fr-BE", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Brussels" }).format(
    new Date(iso),
  );
}

const KIND_LABELS: Record<string, string> = {
  date_close: "Date proche",
  conflict: "Conflit",
  refused: "Refus",
  pending_too_long: "Réponse attendue",
  link_expired: "Lien expiré",
  pending_change: "Changement en attente",
  date_change: "Dates modifiées",
  back_to_buffer: "Remise dans le tampon",
};

type Tab = "alerts" | "responses";

export default function AlertCenter(props: {
  alerts: Alert[];
  notifications: AppNotification[];
  isAdmin: boolean;
  onRefresh: () => void;
  onOpen: (alert: Alert) => void;
}) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("alerts");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const red = props.alerts.filter((a) => a.level === "red").length;
  const unread = props.notifications.filter((n) => !n.read_at).length;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="flex items-center gap-1 rounded border border-slate-300 px-2 py-0.5"
        aria-expanded={open}
        aria-label={`Alertes : ${props.alerts.length} dont ${red} rouge(s) ; ${unread} réponse(s) non lue(s)`}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden>🔔</span>
        {red > 0 && <span className="rounded-full bg-red-600 px-1.5 text-xs font-semibold text-white">⛔ {red}</span>}
        {props.alerts.length - red > 0 && (
          <span className="rounded-full bg-amber-300 px-1.5 text-xs font-semibold text-slate-900">⚠ {props.alerts.length - red}</span>
        )}
        {unread > 0 && <span className="rounded-full bg-sky-700 px-1.5 text-xs font-semibold text-white">✉ {unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-1 w-[440px] rounded border border-slate-300 bg-white shadow-lg" role="dialog" aria-label="Centre d'alertes">
          <div className="flex items-center gap-1 border-b border-slate-200 px-2 py-1.5" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "alerts"} onClick={() => setTab("alerts")}
              className={`rounded px-2 py-0.5 text-sm ${tab === "alerts" ? "bg-slate-800 text-white" : "hover:bg-slate-100"}`}>
              Alertes ({props.alerts.length})
            </button>
            <button type="button" role="tab" aria-selected={tab === "responses"} onClick={() => setTab("responses")}
              className={`rounded px-2 py-0.5 text-sm ${tab === "responses" ? "bg-slate-800 text-white" : "hover:bg-slate-100"}`}>
              Réponses ({unread})
            </button>
            {props.isAdmin && (
              <button type="button" className="ml-auto text-xs text-sky-700 underline" onClick={() => setSettingsOpen(true)}>
                Paramètres d'alerte
              </button>
            )}
          </div>

          {tab === "alerts" &&
            (props.alerts.length === 0 ? (
              <p className="px-3 py-3 text-slate-500">Aucune alerte. Tout est en ordre.</p>
            ) : (
              <ul className="max-h-96 overflow-y-auto">
                {props.alerts.map((a) => (
                  <li key={a.key}>
                    <button
                      type="button"
                      className="flex w-full gap-2 border-b border-slate-100 px-3 py-1.5 text-left hover:bg-slate-50"
                      onClick={() => {
                        setOpen(false);
                        props.onOpen(a);
                      }}
                    >
                      <span className={a.level === "red" ? "text-red-700" : "text-amber-700"} aria-label={a.level === "red" ? "rouge" : "orange"}>
                        {a.level === "red" ? "⛔" : "⚠"}
                      </span>
                      <span className="flex-1">
                        <span className="block text-xs text-slate-500">
                          {KIND_LABELS[a.kind] ?? a.kind}
                          {a.date && ` · ${formatDate(a.date)}`}
                        </span>
                        {a.message}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ))}

          {tab === "responses" && (
            <>
              {unread > 0 && (
                <div className="flex border-b border-slate-100 px-3 py-1">
                  <button
                    type="button"
                    className="ml-auto text-xs text-sky-700 underline"
                    onClick={() => void sendJson("POST", "/notifications/read-all").then(props.onRefresh)}
                  >
                    Tout marquer comme lu
                  </button>
                </div>
              )}
              {props.notifications.length === 0 ? (
                <p className="px-3 py-3 text-slate-500">Aucune réponse reçue.</p>
              ) : (
                <ul className="max-h-96 overflow-y-auto">
                  {props.notifications.map((n) => (
                    <li key={n.id} className={`flex gap-2 border-b border-slate-100 px-3 py-1.5 ${n.read_at ? "text-slate-500" : ""}`}>
                      <span aria-hidden>{n.kind === "refused" ? "✕" : n.kind === "accepted" ? "✓" : "•"}</span>
                      <span className="flex-1">
                        {n.message}
                        <span className="block text-xs text-slate-500">{dateTime(n.created_at)}</span>
                      </span>
                      {!n.read_at && (
                        <button
                          type="button"
                          className="text-xs text-sky-700 underline"
                          onClick={() => void sendJson("POST", `/notifications/${n.id}/read`).then(props.onRefresh)}
                        >
                          Lu
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
      {settingsOpen && (
        <SettingsDialog
          onClose={() => setSettingsOpen(false)}
          onSaved={() => {
            setSettingsOpen(false);
            props.onRefresh();
          }}
        />
      )}
    </div>
  );
}

/** F-43 : seuils d'alerte modifiables par Philippe. */
function SettingsDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [value, setValue] = useState<AlertSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<AlertSettings>("/settings/alerts").then(setValue, () => setError("Chargement impossible."));
  }, []);
  const fields: [keyof AlertSettings, string][] = [
    ["alert_orange_days", "Demande non attribuée : alerte orange sous (jours ouvrés)"],
    ["alert_red_days", "Demande non attribuée : alerte rouge sous (jours ouvrés)"],
    ["pending_response_alert_days", "Réponse attendue depuis plus de (jours)"],
    ["token_validity_days", "Validité des liens de réponse (jours)"],
  ];
  const invalid = value ? value.alert_red_days >= value.alert_orange_days : true;
  return (
    <Modal title="Paramètres d'alerte" onClose={onClose}>
      {!value ? (
        <p className="text-sm text-slate-500">{error ?? "Chargement…"}</p>
      ) : (
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await sendJson("PUT", "/settings/alerts", value);
              onSaved();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Enregistrement impossible.");
            }
          }}
        >
          {fields.map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <span className="flex-1">{label}</span>
              <input
                type="number"
                min={key === "alert_red_days" ? 0 : 1}
                max={90}
                className="w-20 rounded border border-slate-300 px-2 py-1 text-right"
                value={value[key]}
                onChange={(e) => setValue({ ...value, [key]: Number(e.target.value) })}
              />
            </label>
          ))}
          {invalid && <p className="text-xs text-red-700">Le seuil rouge doit être inférieur au seuil orange.</p>}
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" className={secondaryBtn} onClick={onClose}>
              Annuler
            </button>
            <button type="submit" className={primaryBtn} disabled={invalid}>
              Enregistrer
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
