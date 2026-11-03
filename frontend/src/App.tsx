import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type AppNotification, DEV_USER_KEY, type Health, type Me, type OutboxItem, sendJson } from "./api";
import OutboxPage from "./outbox/OutboxPage";
import PlanningPage from "./planning/PlanningPage";

const DEV_USERS = [
  { email: "philippe.zander@example.local", label: "Philippe (admin)" },
  { email: "olivier@example.local", label: "Olivier (planificateur)" },
];

type Session = { me: Me; health: Health };
type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; session: Session };
type View = "planning" | "outbox";

const POLL_MS = 60_000;

function dateTime(iso: string): string {
  return new Intl.DateTimeFormat("fr-BE", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Brussels" }).format(
    new Date(iso),
  );
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [view, setView] = useState<View>("planning");
  const [planningRefresh, setPlanningRefresh] = useState(0);
  const [outboxCount, setOutboxCount] = useState<number | null>(null);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const isAdmin = state.kind === "ready" && state.session.me.role === "admin";
  const notifRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    if (!showNotifications) return;
    const close = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setShowNotifications(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [showNotifications]);

  const switchDevUser = (email: string) => {
    try {
      localStorage.setItem(DEV_USER_KEY, email);
    } catch {
      /* stockage indisponible */
    }
    setReloadKey((k) => k + 1);
  };

  const unread = notifications.filter((n) => !n.read_at).length;
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
              <div className="relative" ref={notifRef}>
                <button
                  type="button"
                  className="rounded border border-slate-300 px-2 py-0.5"
                  aria-expanded={showNotifications}
                  aria-label={`Notifications, ${unread} non lue(s)`}
                  onClick={() => setShowNotifications((v) => !v)}
                >
                  🔔 {unread > 0 && <span className="rounded-full bg-red-600 px-1.5 text-xs font-semibold text-white">{unread}</span>}
                </button>
                {showNotifications && (
                  <div className="absolute right-0 z-50 mt-1 w-96 rounded border border-slate-300 bg-white shadow-lg" role="dialog" aria-label="Notifications">
                    <div className="flex items-center border-b border-slate-200 px-3 py-1.5">
                      <span className="font-medium">Réponses des techniciens</span>
                      {unread > 0 && (
                        <button
                          type="button"
                          className="ml-auto text-xs text-sky-700 underline"
                          onClick={() => void sendJson("POST", "/notifications/read-all").then(refreshCounts)}
                        >
                          Tout marquer comme lu
                        </button>
                      )}
                    </div>
                    {notifications.length === 0 ? (
                      <p className="px-3 py-2 text-slate-500">Aucune notification.</p>
                    ) : (
                      <ul className="max-h-80 overflow-y-auto">
                        {notifications.map((n) => (
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
                                onClick={() => void sendJson("POST", `/notifications/${n.id}/read`).then(refreshCounts)}
                              >
                                Lu
                              </button>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
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
              <PlanningPage key={state.session.me.id} isAdmin={isAdmin} onActivity={refreshCounts} refreshToken={planningRefresh} />
            </div>
            {view === "outbox" && isAdmin && <OutboxPage onChanged={refreshCounts} />}
          </>
        )}
      </main>
    </div>
  );
}
