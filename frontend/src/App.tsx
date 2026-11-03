import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  DEV_USER_KEY,
  type Health,
  type Holiday,
  type Me,
  type MissionType,
  type Technician,
} from "./api";
import { formatDate } from "./dates";

const DEV_USERS = [
  { email: "philippe.zander@example.local", label: "Philippe (admin)" },
  { email: "olivier@example.local", label: "Olivier (planificateur)" },
];

type Data = {
  me: Me;
  health: Health;
  technicians: Technician[];
  missionTypes: MissionType[];
  holidays: Holiday[];
};

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; data: Data };

function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Brussels" }).format(new Date());
}

async function loadAll(): Promise<Data> {
  const from = todayIso();
  const to = `${Number(from.slice(0, 4)) + 1}${from.slice(4)}`;
  const [health, me, technicians, missionTypes, holidays] = await Promise.all([
    api<Health>("/health"),
    api<Me>("/me"),
    api<Technician[]>("/technicians"),
    api<MissionType[]>("/mission-types"),
    api<Holiday[]>(`/holidays?from=${from}&to=${to}`),
  ]);
  return { health, me, technicians, missionTypes, holidays };
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    loadAll()
      .then((data) => !cancelled && setState({ kind: "ready", data }))
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
    <div className="min-h-screen">
      <header className="flex items-center gap-4 border-b border-slate-200 bg-white px-4 py-2">
        <h1 className="text-lg font-semibold">Planning ATS</h1>
        <span className="text-xs text-slate-500">Phase 0 – socle technique</span>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {state.kind === "ready" && (
            <>
              {state.data.health.auth_mode === "dev" && (
                <label className="flex items-center gap-1 text-slate-600">
                  <span>Utilisateur de test</span>
                  <select
                    aria-label="Utilisateur de test"
                    className="rounded border border-slate-300 px-1 py-0.5"
                    value={state.data.me.email}
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
                {state.data.me.display_name} ·{" "}
                {state.data.me.role === "admin" ? "Administrateur" : "Planificateur"}
              </span>
            </>
          )}
        </div>
      </header>

      <main className="p-4">
        {state.kind === "loading" && <p className="text-slate-500">Chargement…</p>}
        {state.kind === "error" && (
          <div role="alert" className="rounded border border-red-300 bg-red-50 p-3 text-red-800">
            <p>{state.message}</p>
            <button
              className="mt-2 rounded border border-red-400 px-2 py-0.5 text-sm"
              onClick={() => setReloadKey((k) => k + 1)}
            >
              Réessayer
            </button>
          </div>
        )}
        {state.kind === "ready" && <Overview data={state.data} />}
      </main>
    </div>
  );
}

function Overview({ data }: { data: Data }) {
  const mechanics = data.technicians.filter((t) => t.role === "mechanic");
  const electronicians = data.technicians.filter((t) => t.role === "electronician");
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <section className="rounded border border-slate-200 bg-white p-3">
        <h2 className="mb-2 font-medium">Mécaniciens ({mechanics.length})</h2>
        <TechList items={mechanics} />
        <h2 className="mt-4 mb-2 font-medium">Électroniciens ({electronicians.length})</h2>
        <TechList items={electronicians} />
      </section>
      <section className="rounded border border-slate-200 bg-white p-3">
        <h2 className="mb-2 font-medium">Types d'activité</h2>
        <ul className="space-y-1 text-sm">
          {data.missionTypes.map((m) => (
            <li key={m.code} className="flex items-center gap-2">
              <span className="inline-block h-3 w-6 rounded-sm" style={{ backgroundColor: m.color }} />
              <code className="w-12 font-mono text-xs">{m.code}</code>
              <span>{m.label}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="rounded border border-slate-200 bg-white p-3">
        <h2 className="mb-2 font-medium">Jours fériés à venir</h2>
        {data.holidays.length === 0 ? (
          <p className="text-sm text-slate-500">Aucun jour férié sur les 12 prochains mois.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {data.holidays.map((h) => (
              <li key={h.date}>
                <span className="tabular-nums">{formatDate(h.date)}</span> – {h.label}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-xs text-slate-500">
          Base de données : {data.health.database} · Authentification : {data.health.auth_mode}
        </p>
      </section>
    </div>
  );
}

function TechList({ items }: { items: Technician[] }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">Aucun.</p>;
  return (
    <ul className="columns-2 text-sm">
      {items.map((t) => (
        <li key={t.id}>{[t.first_name, t.last_name].filter(Boolean).join(" ")}</li>
      ))}
    </ul>
  );
}
