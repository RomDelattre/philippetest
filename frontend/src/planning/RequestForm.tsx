// F-12 : formulaire d'une demande, repris du formulaire SharePoint (création et fiche F-14).
import type { MissionType, ProductLine, RequestFields } from "../api";
import { periodDays } from "../dates";
import { secondaryBtn } from "./Dialogs";

export const EMPTY_REQUEST: RequestFields = {
  type_code: null,
  title: "",
  requester_name: null,
  requester_email: null,
  cf: null,
  client: null,
  location: null,
  objective: null,
  technicians_needed: 1,
  start_date: null,
  end_date: null,
  date_flexible: false,
  flex_justification: null,
  comments: null,
  products: [],
  needed_by: null,
  attachment_url: null,
};

export function formErrors(f: RequestFields): string[] {
  const errors: string[] = [];
  if (f.start_date && f.end_date && f.end_date < f.start_date)
    errors.push("La date de fin doit être postérieure ou égale à la date de début.");
  if (!Number.isInteger(f.technicians_needed) || f.technicians_needed < 1)
    errors.push("Le nombre de techniciens doit être au moins 1.");
  if (f.attachment_url && !/^https?:\/\//i.test(f.attachment_url))
    errors.push("Le lien doit commencer par http:// ou https://");
  return errors;
}

const field = "mt-0.5 w-full rounded border border-slate-300 px-2 py-1 text-sm";
const label = "block text-xs font-medium text-slate-600";

function Text(props: {
  label: string;
  value: string | null;
  onChange: (v: string | null) => void;
  type?: string;
  required?: boolean;
  hint?: string;
}) {
  return (
    <label className={label}>
      {props.label}
      {props.hint && <span className="ml-1 font-normal text-amber-700">({props.hint})</span>}
      <input
        type={props.type ?? "text"}
        className={field}
        value={props.value ?? ""}
        onChange={(e) => props.onChange(e.target.value === "" ? null : e.target.value)}
      />
    </label>
  );
}

export default function RequestForm({
  value,
  onChange,
  missionTypes,
  missing = [],
}: {
  value: RequestFields;
  onChange: (v: RequestFields) => void;
  missionTypes: MissionType[];
  missing?: string[];
}) {
  const set = <K extends keyof RequestFields>(k: K, v: RequestFields[K]) => onChange({ ...value, [k]: v });
  const hint = (f: string) => (missing.includes(f) ? "manquant" : undefined);
  const setProduct = (i: number, patch: Partial<ProductLine>) =>
    set(
      "products",
      value.products.map((p, j) => (j === i ? { ...p, ...patch } : p)),
    );

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <label className={label}>
          Type
          {hint("type_code") && <span className="ml-1 font-normal text-amber-700">(manquant)</span>}
          <select className={field} value={value.type_code ?? ""} onChange={(e) => set("type_code", e.target.value || null)}>
            <option value="">— à définir —</option>
            {missionTypes
              .filter((m) => m.code !== "AB")
              .map((m) => (
                <option key={m.code} value={m.code}>
                  {m.code} – {m.label}
                </option>
              ))}
          </select>
        </label>
        <label className={label}>
          Nombre de techniciens
          <input
            type="number"
            min={1}
            className={field}
            value={value.technicians_needed}
            onChange={(e) => set("technicians_needed", Number(e.target.value))}
          />
        </label>
      </div>
      <Text label="Titre court" value={value.title} onChange={(v) => set("title", v ?? "")} />
      <div className="grid grid-cols-2 gap-2">
        <Text label="Demandeur" value={value.requester_name} onChange={(v) => set("requester_name", v)} />
        <Text label="E-mail du demandeur" type="email" value={value.requester_email} onChange={(v) => set("requester_email", v)} />
        <Text label="CF" value={value.cf} onChange={(v) => set("cf", v)} />
        <Text label="Client" value={value.client} onChange={(v) => set("client", v)} />
      </div>
      <Text label="Lieu" value={value.location} hint={hint("location")} onChange={(v) => set("location", v)} />
      <label className={label}>
        Objectif de la mission
        <textarea className={field} rows={2} value={value.objective ?? ""} onChange={(e) => set("objective", e.target.value || null)} />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <Text label="Début" type="date" hint={hint("start_date")} value={value.start_date} onChange={(v) => set("start_date", v)} />
        <Text label="Fin" type="date" hint={hint("end_date")} value={value.end_date} onChange={(v) => set("end_date", v)} />
      </div>
      {value.start_date && value.end_date && value.end_date >= value.start_date && (
        <p className="text-xs text-slate-500">{periodDays(value.start_date, value.end_date)} jour(s) calendaire(s)</p>
      )}
      <Text label="À attribuer avant le" type="date" value={value.needed_by} onChange={(v) => set("needed_by", v)} />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={value.date_flexible} onChange={(e) => set("date_flexible", e.target.checked)} />
        Dates flexibles
      </label>
      {value.date_flexible && (
        <Text label="Justification de la flexibilité" value={value.flex_justification} onChange={(v) => set("flex_justification", v)} />
      )}
      <label className={label}>
        Commentaires
        <textarea className={field} rows={2} value={value.comments ?? ""} onChange={(e) => set("comments", e.target.value || null)} />
      </label>

      <fieldset className="rounded border border-slate-200 p-2">
        <legend className="px-1 text-xs font-medium text-slate-600">Produits / munitions</legend>
        {value.products.length === 0 && <p className="text-xs text-slate-500">Aucune ligne.</p>}
        {value.products.map((p, i) => (
          <div key={i} className="mb-1 grid grid-cols-[1fr_1fr_1fr_auto] gap-1">
            <input aria-label={`Produit ${i + 1}`} placeholder="Produit" className={field} value={p.product} onChange={(e) => setProduct(i, { product: e.target.value })} />
            <input aria-label={`Munitions ${i + 1}`} placeholder="Munitions" className={field} value={p.ammunition ?? ""} onChange={(e) => setProduct(i, { ammunition: e.target.value || null })} />
            <input aria-label={`Commentaire ${i + 1}`} placeholder="Commentaire" className={field} value={p.comment ?? ""} onChange={(e) => setProduct(i, { comment: e.target.value || null })} />
            <button
              type="button"
              aria-label={`Supprimer la ligne ${i + 1}`}
              className="px-1 text-red-700"
              onClick={() => set("products", value.products.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className={`${secondaryBtn} mt-1 px-2 py-0.5 text-xs`}
          onClick={() => set("products", [...value.products, { product: "", ammunition: null, comment: null }])}
        >
          + Ligne
        </button>
      </fieldset>
      <Text label="Pièce jointe (lien)" type="url" value={value.attachment_url} onChange={(v) => set("attachment_url", v)} />
    </div>
  );
}
