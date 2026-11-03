// F-50 à F-52 : écran « Mails à valider » (administrateur), historique des envois, modèles de mails.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type MailTemplates,
  type OutboundKind,
  type OutboxItem,
  sendJson,
  type SendResult,
} from "../api";
import { ConfirmDialog, dangerBtn, primaryBtn, secondaryBtn } from "../planning/Dialogs";

const KIND_LABELS: Record<OutboundKind, string> = {
  tech_proposal: "Proposition au technicien",
  requester_confirmation: "Confirmation au demandeur",
  generic: "Information",
};

const TEMPLATE_LABELS: Record<keyof MailTemplates, string> = {
  tech_proposal: "Proposition au technicien",
  requester_confirmation: "Confirmation au demandeur",
  tech_cancellation: "Annulation / information au technicien",
};

const VARIABLES = [
  "{technicien}", "{techniciens}", "{demandeur}", "{type}", "{titre}", "{dates}", "{lieu}", "{client}", "{cf}",
  "{ref}", "{lien_accepter}", "{lien_refuser}",
];

function dateTime(iso: string): string {
  return new Intl.DateTimeFormat("fr-BE", { dateStyle: "short", timeStyle: "short", timeZone: "Europe/Brussels" }).format(
    new Date(iso),
  );
}

type Tab = "pending" | "sent" | "templates";

export default function OutboxPage({ onChanged }: { onChanged: () => void }) {
  const [tab, setTab] = useState<Tab>("pending");
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1 border-b border-slate-200 bg-white px-3 py-2" role="tablist">
        {(
          [
            ["pending", "À valider"],
            ["sent", "Envoyés"],
            ["templates", "Modèles"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded px-3 py-1 text-sm ${tab === key ? "bg-sky-700 text-white" : "hover:bg-slate-100"}`}
          >
            {label}
          </button>
        ))}
        <p className="ml-auto text-xs text-slate-500">Aucun mail ne part sans votre validation. Expéditeur : votre boîte.</p>
      </div>
      <div className="min-h-0 flex-1">
        {tab === "pending" && <Pending onChanged={onChanged} />}
        {tab === "sent" && <Sent />}
        {tab === "templates" && <TemplatesEditor />}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- à valider

function Pending({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<OutboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Pick<OutboxItem, "to_email" | "subject" | "body"> | null>(null);
  const [notice, setNotice] = useState<{ kind: "info" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<OutboxItem | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await api<OutboxItem[]>("/outbox?view=pending");
      setItems(list);
      setSelected((s) => new Set([...s].filter((id) => list.some((m) => m.id === id))));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403 ? "Écran réservé à l'administrateur." : "Chargement impossible.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const current = useMemo(() => items?.find((m) => m.id === currentId) ?? items?.[0] ?? null, [items, currentId]);
  useEffect(() => {
    setDraft(current ? { to_email: current.to_email, subject: current.subject, body: current.body } : null);
  }, [current]);

  const dirty = Boolean(current && draft && (draft.to_email !== current.to_email || draft.subject !== current.subject || draft.body !== current.body));
  const missingLinks =
    current?.kind === "tech_proposal" && draft
      ? ["{lien_accepter}", "{lien_refuser}"].filter((p) => !draft.body.includes(p))
      : [];

  const save = async (): Promise<OutboxItem | null> => {
    if (!current || !draft) return null;
    try {
      const saved = await sendJson<OutboxItem>("PATCH", `/outbox/${current.id}`, { version: current.version, ...draft });
      setItems((list) => list?.map((m) => (m.id === saved.id ? saved : m)) ?? null);
      return saved;
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof ApiError && err.status === 409 ? "Mail modifié entre-temps : rechargé." : String(err) });
      await load();
      return null;
    }
  };

  const send = async (list: OutboxItem[]) => {
    setBusy(true);
    try {
      const results = await sendJson<SendResult[]>("POST", "/outbox/send", { items: list.map((m) => ({ id: m.id, version: m.version })) });
      const ok = results.filter((r) => r.status === "sent").length;
      const failed = results.filter((r) => r.error);
      setNotice(
        failed.length
          ? { kind: "error", text: `${ok} envoyé(s), ${failed.length} en échec : ${[...new Set(failed.map((r) => r.error))].join(" ; ")}` }
          : { kind: "info", text: `${ok} mail(s) envoyé(s).` },
      );
      setSelected(new Set());
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Envoi impossible." });
    }
    setBusy(false);
    await load();
    onChanged();
  };

  const sendCurrent = async () => {
    if (!current) return;
    const latest = dirty ? await save() : current;
    if (latest) await send([latest]);
  };

  if (error) return <p role="alert" className="p-4 text-red-700">{error}</p>;
  if (!items) return <p className="p-4 text-slate-500">Chargement…</p>;

  const field = "mt-0.5 w-full rounded border border-slate-300 px-2 py-1 text-sm";
  const selectedItems = items.filter((m) => selected.has(m.id));

  return (
    <div className="flex h-full min-h-0">
      <section className="flex w-[420px] shrink-0 flex-col border-r border-slate-300 bg-slate-50" aria-label="Mails à valider">
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 text-sm">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              aria-label="Tout sélectionner"
              checked={items.length > 0 && selected.size === items.length}
              onChange={(e) => setSelected(e.target.checked ? new Set(items.map((m) => m.id)) : new Set())}
            />
            Tout
          </label>
          <span className="text-slate-500">{items.length} mail(s)</span>
          <button
            type="button"
            className={`${primaryBtn} ml-auto`}
            disabled={selectedItems.length === 0 || busy}
            onClick={() => void send(selectedItems)}
          >
            Envoyer la sélection ({selectedItems.length})
          </button>
        </div>
        {notice && (
          <div role={notice.kind === "error" ? "alert" : "status"} className={`px-3 py-1.5 text-sm ${notice.kind === "error" ? "bg-red-50 text-red-800" : "bg-emerald-50 text-emerald-800"}`}>
            {notice.text}
          </div>
        )}
        {items.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">Aucun mail en attente de validation.</p>
        ) : (
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {items.map((m) => (
              <li
                key={m.id}
                className={`flex cursor-pointer gap-2 border-b border-slate-200 px-3 py-2 text-sm ${current?.id === m.id ? "bg-sky-50" : "bg-white hover:bg-slate-50"}`}
                onClick={() => setCurrentId(m.id)}
              >
                <input
                  type="checkbox"
                  aria-label={`Sélectionner ${m.subject}`}
                  checked={selected.has(m.id)}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) =>
                    setSelected((s) => {
                      const next = new Set(s);
                      if (e.target.checked) next.add(m.id);
                      else next.delete(m.id);
                      return next;
                    })
                  }
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1 text-xs text-slate-500">
                    <span>{KIND_LABELS[m.kind]}</span>
                    {m.request_ref && <span>· {m.request_ref}</span>}
                    {m.status === "failed" && <span className="ml-auto rounded bg-red-100 px-1 text-red-800">⚠ Échec</span>}
                  </div>
                  <div className="truncate font-medium">{m.subject}</div>
                  <div className="truncate text-xs text-slate-600">
                    {m.to_email || <span className="text-red-700">Adresse manquante</span>}
                    {m.technician_name && ` · ${m.technician_name}`}
                  </div>
                  {m.status === "failed" && m.error && <div className="text-xs text-red-700">{m.error}</div>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {current && draft && (
        <section className="min-w-0 flex-1 overflow-y-auto bg-white p-4" aria-label="Mail sélectionné">
          <div className="mb-2 text-xs text-slate-500">
            {KIND_LABELS[current.kind]} {current.request_ref && `· ${current.request_ref}`} · préparé le {dateTime(current.created_at)}
          </div>
          <form
            className="max-w-3xl space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              void save().then((saved) => saved && setNotice({ kind: "info", text: "Mail enregistré." }));
            }}
          >
            <label className="block text-xs font-medium text-slate-600">
              Destinataire
              <input type="email" className={field} value={draft.to_email} onChange={(e) => setDraft({ ...draft, to_email: e.target.value })} />
            </label>
            {!draft.to_email.includes("@") && <p className="text-xs text-red-700">Adresse du destinataire manquante.</p>}
            <label className="block text-xs font-medium text-slate-600">
              Objet
              <input className={field} value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
            </label>
            <label className="block text-xs font-medium text-slate-600">
              Message
              <textarea className={`${field} font-mono`} rows={16} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
            </label>
            {current.kind === "tech_proposal" && (
              <p className={`text-xs ${missingLinks.length ? "text-red-700" : "text-slate-500"}`}>
                {missingLinks.length
                  ? `Variables obligatoires absentes : ${missingLinks.join(", ")}.`
                  : "{lien_accepter} et {lien_refuser} seront remplacés par des liens personnels, valables une seule fois."}
              </p>
            )}
            <div className="flex gap-2">
              <button type="button" className={dangerBtn} onClick={() => setConfirmDelete(current)}>
                Supprimer
              </button>
              <span className="flex-1" />
              <button type="submit" className={secondaryBtn} disabled={!dirty}>
                Enregistrer
              </button>
              <button
                type="button"
                className={primaryBtn}
                disabled={busy || !draft.to_email.includes("@") || missingLinks.length > 0}
                onClick={() => void sendCurrent()}
              >
                {current.status === "failed" ? "Renvoyer" : "Envoyer"}
              </button>
            </div>
          </form>
        </section>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Supprimer ce mail ?"
          message={<p>Le mail ne sera pas envoyé. L'affectation éventuelle reste en brouillon sur le planning.</p>}
          confirmLabel="Supprimer"
          onCancel={() => setConfirmDelete(null)}
          onConfirm={async () => {
            const m = confirmDelete;
            setConfirmDelete(null);
            try {
              await sendJson("DELETE", `/outbox/${m.id}?version=${m.version}`);
              setNotice({ kind: "info", text: "Mail supprimé." });
            } catch (err) {
              setNotice({ kind: "error", text: err instanceof Error ? err.message : "Suppression impossible." });
            }
            await load();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- envoyés

function Sent() {
  const [items, setItems] = useState<OutboxItem[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    api<OutboxItem[]>("/outbox?view=sent").then(setItems, () => setItems([]));
  }, []);
  if (!items) return <p className="p-4 text-slate-500">Chargement…</p>;
  if (items.length === 0) return <p className="p-4 text-sm text-slate-500">Aucun mail envoyé.</p>;
  return (
    <ul className="h-full overflow-y-auto bg-white">
      {items.map((m) => (
        <li key={m.id} className="border-b border-slate-200 px-4 py-2 text-sm">
          <button type="button" className="w-full text-left" onClick={() => setOpen(open === m.id ? null : m.id)} aria-expanded={open === m.id}>
            <span className="text-xs text-slate-500">
              {m.sent_at && dateTime(m.sent_at)} · {KIND_LABELS[m.kind]} {m.request_ref && `· ${m.request_ref}`}
            </span>
            <span className="block font-medium">{m.subject}</span>
            <span className="block text-xs text-slate-600">{m.to_email}</span>
          </button>
          {open === m.id && <pre className="mt-2 whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono text-xs">{m.body}</pre>}
        </li>
      ))}
    </ul>
  );
}

// --------------------------------------------------------------------------- modèles (F-52)

function TemplatesEditor() {
  const [tpl, setTpl] = useState<MailTemplates | null>(null);
  const [saved, setSaved] = useState<MailTemplates | null>(null);
  const [notice, setNotice] = useState<{ kind: "info" | "error"; text: string } | null>(null);
  useEffect(() => {
    api<MailTemplates>("/settings/mail-templates").then(
      (t) => {
        setTpl(t);
        setSaved(t);
      },
      () => setNotice({ kind: "error", text: "Chargement impossible." }),
    );
  }, []);
  if (!tpl) return <p className="p-4 text-slate-500">{notice?.text ?? "Chargement…"}</p>;
  const dirty = JSON.stringify(tpl) !== JSON.stringify(saved);
  const field = "mt-0.5 w-full rounded border border-slate-300 px-2 py-1 text-sm";
  return (
    <form
      className="h-full space-y-4 overflow-y-auto bg-white p-4"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          const t = await sendJson<MailTemplates>("PUT", "/settings/mail-templates", tpl);
          setTpl(t);
          setSaved(t);
          setNotice({ kind: "info", text: "Modèles enregistrés. Ils s'appliquent aux prochains brouillons." });
        } catch (err) {
          setNotice({ kind: "error", text: err instanceof Error ? err.message : "Enregistrement impossible." });
        }
      }}
    >
      <p className="text-sm text-slate-600">
        Variables disponibles : <code className="text-xs">{VARIABLES.join(" ")}</code>. Le modèle de proposition doit contenir{" "}
        <code className="text-xs">{"{lien_accepter}"}</code> et <code className="text-xs">{"{lien_refuser}"}</code>.
      </p>
      {(Object.keys(TEMPLATE_LABELS) as (keyof MailTemplates)[]).map((key) => (
        <fieldset key={key} className="max-w-3xl space-y-2 rounded border border-slate-200 p-3">
          <legend className="px-1 text-sm font-medium">{TEMPLATE_LABELS[key]}</legend>
          <label className="block text-xs font-medium text-slate-600">
            Objet
            <input className={field} value={tpl[key].subject} onChange={(e) => setTpl({ ...tpl, [key]: { ...tpl[key], subject: e.target.value } })} />
          </label>
          <label className="block text-xs font-medium text-slate-600">
            Message
            <textarea
              className={`${field} font-mono`}
              rows={10}
              value={tpl[key].body}
              onChange={(e) => setTpl({ ...tpl, [key]: { ...tpl[key], body: e.target.value } })}
            />
          </label>
        </fieldset>
      ))}
      {notice && (
        <p role={notice.kind === "error" ? "alert" : "status"} className={`text-sm ${notice.kind === "error" ? "text-red-700" : "text-emerald-700"}`}>
          {notice.text}
        </p>
      )}
      <button type="submit" className={primaryBtn} disabled={!dirty}>
        Enregistrer les modèles
      </button>
    </form>
  );
}
