// F-10, F-11 : zone tampon « À attribuer » et vignettes, déplaçables sur le planning.
import { useDraggable } from "@dnd-kit/core";
import type { MissionType, Vignette } from "../api";
import { formatDate, periodDays } from "../dates";
import { primaryBtn } from "./Dialogs";
import { BADGE_LABELS, FIELD_LABELS } from "./layout";

export function VignetteCard({
  v,
  type,
  selected,
  onOpen,
  overlay = false,
}: {
  v: Vignette;
  type: MissionType | undefined;
  selected?: boolean;
  onOpen?: (id: string) => void;
  overlay?: boolean;
}) {
  const { setNodeRef, listeners, attributes, isDragging } = useDraggable({
    id: overlay ? `overlay:${v.id}` : `new:${v.id}`,
    data: { kind: "new", requestId: v.id },
    disabled: overlay,
  });
  const dated = v.start_date && v.end_date;
  const icons: { key: string; icon: string; label: string; tone: string }[] = [];
  if (v.date_alert)
    icons.push({
      key: "date",
      icon: "⏰",
      label: v.working_days_left ? `Date proche : ${v.working_days_left} j ouvré(s)` : "Date dépassée ou imminente",
      tone: v.date_alert === "red" ? "bg-red-600 text-white" : "bg-amber-300 text-slate-900",
    });
  if (v.needs_review) icons.push({ key: "review", icon: "⚑", label: "À vérifier", tone: "bg-amber-100 text-amber-900" });
  if (v.pending_changes.includes("modification"))
    icons.push({ key: "mod", icon: "✎", label: "Modification en attente", tone: "bg-sky-100 text-sky-900" });
  if (v.pending_changes.includes("cancellation"))
    icons.push({ key: "cancel", icon: "⊘", label: "Annulation en attente", tone: "bg-red-100 text-red-900" });
  if (v.missing_fields.length)
    icons.push({
      key: "missing",
      icon: "?",
      label: `Manque : ${v.missing_fields.map((f) => FIELD_LABELS[f] ?? f).join(", ")}`,
      tone: "bg-slate-200 text-slate-800",
    });
  for (const b of v.badges) icons.push({ key: b, icon: "!", label: BADGE_LABELS[b] ?? b, tone: "bg-orange-100 text-orange-900" });

  return (
    <li
      ref={overlay ? undefined : setNodeRef}
      {...(overlay ? {} : listeners)}
      {...(overlay ? {} : attributes)}
      onClick={() => onOpen?.(v.id)}
      data-testid={`vignette-${v.id}`}
      aria-label={`${v.ref} ${v.title}`}
      className={`cursor-grab list-none rounded border select-none bg-white p-2 text-xs shadow-sm active:cursor-grabbing ${selected ? "ring-2 ring-sky-600" : ""} ${isDragging ? "opacity-40" : ""} ${overlay ? "w-64 shadow-lg" : ""}`}
      style={{ borderLeft: `4px solid ${type?.color ?? "#94a3b8"}` }}
    >
      <div className="flex items-center gap-1.5">
        <span className="font-mono font-semibold">{v.type_code ?? "?"}</span>
        <span className="text-slate-500">{v.ref}</span>
        <span className="ml-auto rounded bg-slate-100 px-1 font-medium" title="Techniciens restant à trouver">
          {v.remaining}/{v.technicians_needed} à trouver
        </span>
      </div>
      <div className="mt-0.5 truncate text-sm font-medium" title={v.title}>
        {v.title || "Sans titre"}
      </div>
      <div className="truncate text-slate-600">
        {[v.requester_name, v.client, v.location].filter(Boolean).join(" · ") || "—"}
      </div>
      <div className="tabular-nums text-slate-700">
        {dated
          ? `${formatDate(v.start_date!)} → ${formatDate(v.end_date!)} · ${periodDays(v.start_date!, v.end_date!)} j`
          : "Dates à préciser"}
        {v.date_flexible && <span className="ml-1 text-slate-500">(flexible)</span>}
      </div>
      {icons.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-1">
          {icons.map((i) => (
            <li key={i.key} className={`rounded px-1 ${i.tone}`} title={i.label}>
              <span aria-hidden>{i.icon} </span>
              {i.label}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function Buffer(props: {
  vignettes: Vignette[] | null;
  error: string | null;
  types: Map<string, MissionType>;
  selectedId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onOpen: (id: string) => void;
  onCreate: () => void;
}) {
  const count = props.vignettes?.length ?? 0;
  if (props.collapsed)
    return (
      <button
        type="button"
        onClick={props.onToggle}
        className="w-8 shrink-0 border-r border-slate-300 bg-slate-100 text-xs font-medium text-slate-700 [writing-mode:vertical-rl]"
        aria-label="Afficher la zone À attribuer"
      >
        À attribuer ({count}) ▸
      </button>
    );
  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-slate-300 bg-slate-50" aria-label="À attribuer">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-2 py-1.5">
        <h2 className="font-semibold">À attribuer</h2>
        <span className="rounded-full bg-slate-200 px-1.5 text-xs tabular-nums">{count}</span>
        <button type="button" className={`${primaryBtn} ml-auto px-2 py-0.5`} onClick={props.onCreate}>
          + Demande
        </button>
        <button type="button" onClick={props.onToggle} aria-label="Replier la zone À attribuer" className="px-1">
          ◂
        </button>
      </div>
      <p className="px-2 pt-1 text-[11px] text-slate-500">Glissez une vignette sur un technicien pour l'attribuer.</p>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {props.error && (
          <p role="alert" className="text-sm text-red-700">
            {props.error}
          </p>
        )}
        {!props.vignettes && !props.error && <p className="text-sm text-slate-500">Chargement…</p>}
        {props.vignettes && count === 0 && <p className="text-sm text-slate-500">Rien à attribuer.</p>}
        <ul className="space-y-2">
          {props.vignettes?.map((v) => (
            <VignetteCard
              key={v.id}
              v={v}
              type={v.type_code ? props.types.get(v.type_code) : undefined}
              selected={props.selectedId === v.id}
              onOpen={props.onOpen}
            />
          ))}
        </ul>
      </div>
    </aside>
  );
}
