import { useEffect, useState } from "react";
import { api, ApiError, DEV_USER_KEY, type Health, type Me } from "./api";
import PlanningPage from "./planning/PlanningPage";

const DEV_USERS = [
  { email: "philippe.zander@example.local", label: "Philippe (admin)" },
  { email: "olivier@example.local", label: "Olivier (planificateur)" },
];

type Session = { me: Me; health: Health };
type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; session: Session };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

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

  const switchDevUser = (email: string) => {
    try {
      localStorage.setItem(DEV_USER_KEY, email);
    } catch {
      /* stockage indisponible */
    }
    setReloadKey((k) => k + 1);
  };

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-4 border-b border-slate-200 bg-white px-4 py-2">
        <h1 className="text-lg font-semibold">Planning ATS</h1>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {state.kind === "ready" && (
            <>
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
                {state.session.me.display_name} ·{" "}
                {state.session.me.role === "admin" ? "Administrateur" : "Planificateur"}
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
            <button
              className="mt-2 rounded border border-red-400 px-2 py-0.5 text-sm"
              onClick={() => setReloadKey((k) => k + 1)}
            >
              Réessayer
            </button>
          </div>
        )}
        {state.kind === "ready" && <PlanningPage key={state.session.me.id} />}
      </main>
    </div>
  );
}
