import { useCallback, useEffect, useState } from "react";
import AlertCenter from "./alerts/AlertCenter";
import { type Alert, api, ApiError, type AppNotification, DEV_USER_KEY, type Health, type Me, type OutboxItem } from "./api";
import OutboxPage from "./outbox/OutboxPage";
import PlanningPage, { type PlanningFocus } from "./planning/PlanningPage";

const DEV_USERS = [
  { email: "philippe.zander@example.local", label: "Philippe (admin)" },
  { email: "olivier@example.local", label: "Olivier (planificateur)" },
];

type Session = { me: Me; health: Health };
type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; session: Session };
type View = "planning" | "outbox";

const POLL_MS = 60_000;

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [view, setView] = useState<View>("planning");
  const [planningRefresh, setPlanningRefresh] = useState(0);
  const [outboxCount, setOutboxCount] = useState<number | null>(null);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [focus, setFocus] = useState<PlanningFocus | null>(null);
  const isAdmin = state.kind === "ready" && state.session.me.role === "admin";

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    Promise.all([api<Health>("/health"), api<Me>("/me")])
      .then(([health, me]) => !cancelled && setState({ kind: "ready", session: { health, me } }))
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError && err.status === 403
            ? "Votre compte n'est pas autorisé à utiliser le planning."
            : "Impossible de joindre le serveur. Réessayez dans quelques instants.";
        setState({ kind: "error", message });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const refreshCounts = useCallback(() => {
    if (state.kind !== "ready") return;
    api<AppNotification[]>("/notifications").then(setNotifications, () => undefined);
    api<Alert[]>("/alerts").then(setAlerts, () => undefined);
    if (state.session.me.role === "admin")
      api<OutboxItem[]>("/outbox?view=pending").then((l) => setOutboxCount(l.length), () => setOutboxCount(null));
  }, [state]);

  useEffect(() => {
    refreshCounts();
    const id = window.setInterval(refreshCounts, POLL_MS);
    return () => window.clearInterval(id);
  }, [refreshCounts]);

  useEffect(() => {
    if (!isAdmin && view === "outbox") setView("planning");
  }, [isAdmin, view]);

  const switchDevUser = (email: string) => {
    try {
      localStorage.setItem(DEV_USER_KEY, email);
    } catch {
      /* stockage indisponible */
    }
    setReloadKey((k) => k + 1);
  };

  const navBtn = (active: boolean) =>
    `rounded px-3 py-1 text-sm ${active ? "bg-slate-800 text-white" : "text-slate-700 hover:bg-slate-100"}`;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2">
        <h1 className="mr-2 text-lg font-semibold">Planning ATS</h1>
        {state.kind === "ready" && (
          <nav className="flex items-center gap-1" aria-label="Navigation">
            <button type="button" className={navBtn(view === "planning")} aria-current={view === "planning"} onClick={() => {
                setView("planning");
                setPlanningRefresh((n) => n + 1);
              }}>
              Planning
            </button>
            {isAdmin && (
              <button type="button" className={navBtn(view === "outbox")} aria-current={view === "outbox"} onClick={() => setView("outbox")}>
                Mails à valider
                {outboxCount !== null && outboxCount > 0 && (
                  <span className="ml-1.5 rounded-full bg-amber-400 px-1.5 text-xs font-semibold text-slate-900">{outboxCount}</span>
                )}
              </button>
            )}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-3 text-sm">
          {state.kind === "ready" && (
            <>
              <AlertCenter
                alerts={alerts}
                notifications={notifications}
                isAdmin={isAdmin}
                onRefresh={refreshCounts}
                onOpen={(a) => {
                  setView("planning");
                  setFocus({ requestId: a.request_id, assignmentId: a.assignment_id, date: a.date, nonce: Date.now() });
                }}
              />
              {state.session.health.auth_mode === "dev" && (
                <label className="flex items-center gap-1 text-slate-600">
                  <span>Utilisateur de test</span>
                  <select
                    aria-label="Utilisateur de test"
                    className="rounded border border-slate-300 px-1 py-0.5"
                    value={state.session.me.email}
                    onChange={(e) => switchDevUser(e.target.value)}
                  >
                    {DEV_USERS.map((u) => (
                      <option key={u.email} value={u.email}>
                        {u.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <span data-testid="current-user">
                {state.session.me.display_name} · {state.session.me.role === "admin" ? "Administrateur" : "Planificateur"}
              </span>
            </>
          )}
        </div>
      </header>

      <main className="min-h-0 flex-1">
        {state.kind === "loading" && <p className="p-4 text-slate-500">Chargement…</p>}
        {state.kind === "error" && (
          <div role="alert" className="m-4 rounded border border-red-300 bg-red-50 p-3 text-red-800">
            <p>{state.message}</p>
            <button className="mt-2 rounded border border-red-400 px-2 py-0.5 text-sm" onClick={() => setReloadKey((k) => k + 1)}>
              Réessayer
            </button>
          </div>
        )}
        {state.kind === "ready" && (
          <>
            {/* le planning reste monté pour garder filtres et position */}
            <div className={view === "planning" ? "h-full" : "hidden"}>
              <PlanningPage key={state.session.me.id} isAdmin={isAdmin} onActivity={refreshCounts} refreshToken={planningRefresh} focus={focus} />
            </div>
            {view === "outbox" && isAdmin && <OutboxPage onChanged={refreshCounts} />}
          </>
        )}
      </main>
    </div>
  );
}
