import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, sendJson, type Absence, type Assignment, type MissionType, type Planning } from "../api";
import { addDays, formatDate, todayIso } from "../dates";
import { type AbsenceDraft, AbsenceDialog, ConfirmDialog, secondaryBtn } from "./Dialogs";
import Grid, { techName } from "./Grid";
import {
  ASSIGNMENT_STATUS_LABELS,
  buildDays,
  EMPTY_FILTERS,
  type Filters,
  needsConfirmation,
  type Period,
  samePeriod,
  windowFor,
  type Zoom,
  ZOOMS,
} from "./layout";
import SidePanel from "./SidePanel";

type Notice = { kind: "info" | "error"; text: string } | null;
type PendingMove = { assignment: Assignment; period: Period } | null;

export default function PlanningPage({ today = todayIso() }: { today?: string }) {
  const [zoom, setZoom] = useState<Zoom>("8w");
  const [anchor, setAnchor] = useState(today);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [data, setData] = useState<Planning | null>(null);
  const [missionTypes, setMissionTypes] = useState<MissionType[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [absenceDraft, setAbsenceDraft] = useState<AbsenceDraft | null>(null);
  const [pendingMove, setPendingMove] = useState<PendingMove>(null);

  const win = windowFor(anchor, zoom);
  const { dayWidth } = ZOOMS[zoom];

  const reload = useCallback(async () => {
    try {
      const planning = await api<Planning>(`/planning?from=${win.start}&to=${win.end}`);
      setData(planning);
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Impossible de charger le planning.");
    }
  }, [win.start, win.end]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    api<MissionType[]>("/mission-types").then(setMissionTypes, () => setMissionTypes([]));
  }, []);

  const derived = useMemo(() => {
    const technicians = data?.technicians ?? [];
    const visible = (role: string) =>
      technicians.filter((t) => t.role === role && (!filters.technicianId || t.id === filters.technicianId));
    return {
      days: buildDays(win.start, win.days, data?.holidays ?? [], today),
      mechanics: visible("mechanic"),
      electronicians: visible("electronician"),
      allMechanics: technicians.filter((t) => t.role === "mechanic"),
      techById: new Map(technicians.map((t) => [t.id, t])),
      requests: new Map((data?.requests ?? []).map((r) => [r.id, r])),
      types: new Map(missionTypes.map((m) => [m.code, m])),
    };
  }, [data, missionTypes, filters.technicianId, win.start, win.days, today]);

  // ------------------------------------------------------------------ F-07 : déplacement
  const saveMove = async (a: Assignment, period: Period, confirm: boolean) => {
    // affichage immédiat, corrigé par le rechargement
    setData((d) =>
      d && {
        ...d,
        assignments: d.assignments.map((x) =>
          x.id === a.id ? { ...x, technician_id: period.technicianId, start_date: period.start, end_date: period.end } : x,
        ),
      },
    );
    try {
      await sendJson("PATCH", `/assignments/${a.id}`, {
        version: a.version,
        technician_id: period.technicianId,
        start_date: period.start,
        end_date: period.end,
        confirm,
      });
      setNotice({
        kind: "info",
        text: needsConfirmation(a.status)
          ? "Activité déplacée et remise en brouillon : l'ancien lien de réponse n'est plus valable."
          : "Activité déplacée.",
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 428) {
        setPendingMove({ assignment: a, period });
      } else if (err instanceof ApiError && err.status === 409) {
        setNotice({ kind: "error", text: "Le planning a été modifié par un autre utilisateur : il a été rechargé." });
      } else {
        setNotice({ kind: "error", text: err instanceof Error ? err.message : "Déplacement impossible." });
      }
    }
    await reload();
  };

  const requestMove = (a: Assignment, period: Period) => {
    if (samePeriod(period, { technicianId: a.technician_id, start: a.start_date, end: a.end_date })) return;
    if (needsConfirmation(a.status)) setPendingMove({ assignment: a, period });
    else void saveMove(a, period, false);
  };

  // ------------------------------------------------------------------ F-31 : absences
  const saveAbsence = async (draft: AbsenceDraft): Promise<string | null> => {
    const body = {
      technician_id: draft.technician_id,
      start_date: draft.start_date,
      end_date: draft.end_date,
      category: draft.category,
    };
    try {
      if (draft.id) await sendJson("PATCH", `/absences/${draft.id}`, { ...body, version: draft.version });
      else await sendJson("POST", "/absences", body);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        await reload();
        return "L'absence a été modifiée entre-temps : fermez et rouvrez-la.";
      }
      return err instanceof Error ? err.message : "Enregistrement impossible.";
    }
    setAbsenceDraft(null);
    setNotice({ kind: "info", text: draft.id ? "Absence modifiée." : "Absence créée." });
    await reload();
    return null;
  };

  const deleteAbsence = async (ab: Absence): Promise<string | null> => {
    try {
      await sendJson("DELETE", `/absences/${ab.id}?version=${ab.version}`);
    } catch (err) {
      return err instanceof Error ? err.message : "Suppression impossible.";
    }
    setAbsenceDraft(null);
    setNotice({ kind: "info", text: "Absence supprimée." });
    await reload();
    return null;
  };

  const selected = data?.assignments.find((a) => a.id === selectedId);
  const shift = (weeks: number) => setAnchor((x) => addDays(x, weeks * 7));
  const step = Math.max(1, ZOOMS[zoom].weeks / 2);
  const ctl = "rounded border border-slate-300 bg-white px-2 py-1 text-sm";
  const pendingTech = pendingMove && derived.techById.get(pendingMove.period.technicianId);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Barre d'outils : zoom, navigation, filtres (F-02, F-06) */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-3 py-2">
        <div className="flex items-center gap-1">
          <button type="button" className={secondaryBtn} onClick={() => shift(-step)} aria-label="Période précédente">
            ←
          </button>
          <button type="button" className={secondaryBtn} onClick={() => setAnchor(today)}>
            Aujourd'hui
          </button>
          <button type="button" className={secondaryBtn} onClick={() => shift(step)} aria-label="Période suivante">
            →
          </button>
        </div>
        <span className="text-sm text-slate-600 tabular-nums">
          du {formatDate(win.start)} au {formatDate(win.end)}
        </span>
        <select aria-label="Zoom" className={ctl} value={zoom} onChange={(e) => setZoom(e.target.value as Zoom)}>
          {(Object.keys(ZOOMS) as Zoom[]).map((z) => (
            <option key={z} value={z}>
              {ZOOMS[z].label}
            </option>
          ))}
        </select>
        <span className="mx-1 h-5 w-px bg-slate-300" />
        <select aria-label="Filtrer par technicien" className={ctl} value={filters.technicianId} onChange={(e) => setFilters({ ...filters, technicianId: e.target.value })}>
          <option value="">Tous les techniciens</option>
          {(data?.technicians ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {techName(t)}
            </option>
          ))}
        </select>
        <select aria-label="Filtrer par type" className={ctl} value={filters.typeCode} onChange={(e) => setFilters({ ...filters, typeCode: e.target.value })}>
          <option value="">Tous les types</option>
          {missionTypes
            .filter((m) => m.code !== "AB" && m.code !== "?")
            .map((m) => (
              <option key={m.code} value={m.code}>
                {m.code} – {m.label}
              </option>
            ))}
        </select>
        <select aria-label="Filtrer par statut" className={ctl} value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value as Filters["status"] })}>
          <option value="">Tous les statuts</option>
          {(["draft", "pending_response", "accepted"] as const).map((s) => (
            <option key={s} value={s}>
              {ASSIGNMENT_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <select aria-label="Filtrer par demande" className={ctl} value={filters.requestId} onChange={(e) => setFilters({ ...filters, requestId: e.target.value })}>
          <option value="">Toutes les demandes</option>
          {[...derived.requests.values()]
            .sort((x, y) => x.ref.localeCompare(y.ref))
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.ref} – {r.title}
              </option>
            ))}
        </select>
        <input
          type="search"
          aria-label="Rechercher client, CF ou demandeur"
          placeholder="Client, CF, demandeur…"
          className={`${ctl} w-48`}
          value={filters.text}
          onChange={(e) => setFilters({ ...filters, text: e.target.value })}
        />
        {JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS) && (
          <button type="button" className="text-sm text-sky-700 underline" onClick={() => setFilters(EMPTY_FILTERS)}>
            Réinitialiser
          </button>
        )}
        <Legend />
      </div>

      {notice && (
        <div
          role={notice.kind === "error" ? "alert" : "status"}
          className={`flex items-center gap-2 px-3 py-1.5 text-sm ${notice.kind === "error" ? "bg-red-50 text-red-800" : "bg-emerald-50 text-emerald-800"}`}
        >
          <span className="flex-1">{notice.text}</span>
          <button type="button" aria-label="Fermer le message" onClick={() => setNotice(null)}>
            ✕
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto" data-testid="planning-scroll">
          {loadError && !data && (
            <div role="alert" className="m-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              {loadError}{" "}
              <button type="button" className="underline" onClick={() => void reload()}>
                Réessayer
              </button>
            </div>
          )}
          {!data && !loadError && <p className="p-3 text-slate-500">Chargement du planning…</p>}
          {data && (
            <Grid
              days={derived.days}
              dayWidth={dayWidth}
              mechanics={derived.mechanics}
              electronicians={derived.electronicians}
              assignments={data.assignments}
              requests={derived.requests}
              absences={data.absences}
              missionTypes={derived.types}
              filters={filters}
              selectedId={selectedId}
              onSelect={setSelectedId}
              onAbsenceClick={(ab) => setAbsenceDraft({ ...ab })}
              onEmptyClick={(technicianId, iso) =>
                setAbsenceDraft({ technician_id: technicianId, start_date: iso, end_date: iso, category: "leave" })
              }
              onDrop={requestMove}
            />
          )}
        </div>
        {selected && (
          <SidePanel
            assignment={selected}
            request={derived.requests.get(selected.request_id)}
            type={derived.types.get(derived.requests.get(selected.request_id)?.type_code ?? "")}
            technicians={derived.techById}
            mechanics={derived.allMechanics}
            onSave={(period) => requestMove(selected, period)}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>

      {pendingMove && (
        <ConfirmDialog
          title="Déplacer une activité déjà proposée ?"
          message={
            <>
              <p>
                {derived.requests.get(pendingMove.assignment.request_id)?.ref} est{" "}
                {pendingMove.assignment.status === "accepted" ? "acceptée" : "en attente de réponse"}. Nouvelle
                affectation : <strong>{pendingTech ? techName(pendingTech) : ""}</strong>, du{" "}
                <strong>{formatDate(pendingMove.period.start)}</strong> au <strong>{formatDate(pendingMove.period.end)}</strong>.
              </p>
              <p className="mt-2">
                L'activité repasse en brouillon et le lien de réponse déjà envoyé ne sera plus valable. Un nouveau mail
                devra être validé.
              </p>
            </>
          }
          confirmLabel="Déplacer"
          onCancel={() => setPendingMove(null)}
          onConfirm={() => {
            const m = pendingMove;
            setPendingMove(null);
            void saveMove(m.assignment, m.period, true);
          }}
        />
      )}

      {absenceDraft && data && (
        <AbsenceDialog
          initial={absenceDraft}
          technicians={data.technicians}
          onSave={saveAbsence}
          onDelete={deleteAbsence}
          onClose={() => setAbsenceDraft(null)}
        />
      )}
    </div>
  );
}

function Legend() {
  const sw = "inline-block h-3 w-6 rounded-sm border border-slate-600 align-middle";
  return (
    <div className="ml-auto flex items-center gap-3 text-xs text-slate-600" aria-label="Légende">
      <span>
        <span className={`${sw} bg-slate-600`} /> Accepté
      </span>
      <span>
        <span className={sw} style={{ backgroundImage: "repeating-linear-gradient(135deg, #475569 0 4px, #47556999 4px 8px)" }} /> En attente
      </span>
      <span>
        <span className={`${sw} border-dashed bg-white`} /> ✎ Brouillon
      </span>
      <span>
        <span className={`${sw} bg-slate-400`} /> AB Absence
      </span>
    </div>
  );
}
