"""F-21, F-22 : page de réponse du technicien, sans authentification.
GET affiche le résumé et un bouton ; seul le POST enregistre la réponse, pour que les analyses
automatiques de liens (antivirus, aperçus) ne consomment jamais le jeton."""

from datetime import UTC, datetime
from html import escape
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.auth import SessionDep
from app.models import Assignment, AssignmentStatus, Technician
from app.models import Request as Demand
from app.rules.templates import format_dates
from app.rules.tokens import hash_token
from app.services.outbox import tech_name, template_values
from app.services.responses import apply_response

router = APIRouter(prefix="/api")

_STYLE = """
body{font-family:system-ui,sans-serif;background:#f8fafc;color:#0f172a;margin:0;padding:16px}
main{max-width:560px;margin:24px auto;background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:20px}
h1{font-size:1.25rem;margin:0 0 12px}dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px}
dt{color:#475569}form{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}
button{font-size:1rem;padding:10px 16px;border-radius:6px;border:1px solid #334155;cursor:pointer;
background:#fff}
button.main{background:#0369a1;border-color:#0369a1;color:#fff}
.msg{padding:10px;border-radius:6px;background:#f1f5f9}
"""


def _page(title: str, content: str, status_code: int = 200) -> HTMLResponse:
    html = (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='robots' content='noindex'>"
        f"<title>{escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main><h1>{escape(title)}</h1>{content}</main></body></html>"
    )
    return HTMLResponse(html, status_code=status_code, headers={"Cache-Control": "no-store"})


def _find(session: SessionDep, token: str) -> tuple[Assignment | None, str | None]:
    """Renvoie l'affectation ou un message de refus (jeton inconnu, utilisé, expiré, révoqué)."""
    a = session.scalar(select(Assignment).where(Assignment.response_token_hash == hash_token(token)))
    if a is None:
        return None, "Ce lien n'est plus valable. Si besoin, contactez Philippe."
    if a.token_used_at is not None:
        return None, "Votre réponse a déjà été enregistrée. Merci."
    expires = a.token_expires_at
    if expires is not None and expires.replace(tzinfo=expires.tzinfo or UTC) < datetime.now(UTC):
        return None, "Ce lien a expiré. Contactez Philippe pour répondre."
    if a.status != AssignmentStatus.PENDING_RESPONSE:
        return None, "Cette proposition n'est plus d'actualité. Si besoin, contactez Philippe."
    return a, None


def _summary(session: SessionDep, a: Assignment) -> str:
    req = session.get(Demand, a.request_id)
    tech = session.get(Technician, a.technician_id)
    assert req is not None and tech is not None
    v = template_values(session, req, tech)
    rows = [
        ("Technicien", tech_name(tech)),
        ("Activité", f"{v['type']} – {req.title}" if req.title else v["type"]),
        ("Référence", req.ref),
        ("Dates", format_dates(a.start_date, a.end_date)),
        ("Lieu", v["lieu"]),
    ]
    return "<dl>" + "".join(f"<dt>{escape(k)}</dt><dd>{escape(val)}</dd>" for k, val in rows) + "</dl>"


@router.get("/respond/{token}", response_class=HTMLResponse)
def respond_page(token: str, session: SessionDep, answer: Annotated[str, Query()] = "accept") -> HTMLResponse:
    a, error = _find(session, token)
    if a is None:
        return _page("Réponse à une proposition", f"<p class='msg'>{escape(error or '')}</p>", 410)
    first = "accept" if answer != "refuse" else "refuse"
    labels = {"accept": "Je confirme : j'accepte", "refuse": "Je confirme : je refuse"}
    buttons = "".join(
        f"<button type='submit' name='answer' value='{key}' class='{'main' if key == first else ''}'>"
        f"{escape(labels[key])}</button>"
        for key in ([first, "refuse" if first == "accept" else "accept"])
    )
    return _page(
        "Réponse à une proposition",
        _summary(session, a) + f"<form method='post'>{buttons}</form>",
    )


@router.post("/respond/{token}", response_class=HTMLResponse)
async def respond_submit(token: str, request: Request, session: SessionDep) -> HTMLResponse:
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    answer = (form.get("answer") or [""])[0]
    if answer not in ("accept", "refuse"):
        return _page("Réponse à une proposition", "<p class='msg'>Réponse invalide.</p>", 400)
    a, error = _find(session, token)
    if a is None:
        return _page("Réponse à une proposition", f"<p class='msg'>{escape(error or '')}</p>", 410)
    tech = session.get(Technician, a.technician_id)
    actor = f"technician:{(tech.email if tech else None) or a.technician_id}"
    summary = _summary(session, a)
    apply_response(session, a, answer, actor, via_link=True)  # type: ignore[arg-type]
    session.commit()
    text = (
        "Merci, votre acceptation est enregistrée."
        if answer == "accept"
        else "Merci, votre refus est enregistré."
    )
    return _page("Réponse enregistrée", f"<p class='msg'>{escape(text)}</p>{summary}")
