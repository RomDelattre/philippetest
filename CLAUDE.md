# Planning ATS – consignes pour l'agent de code

Source de vérité : `docs/specifications.md` (export du cahier des spécifications v0.2,
original Word dans `docs/`). Chaque exigence a un identifiant (F-xx, R-xx, NF-xx, Q-xx) :
cite-les dans les commits, les tests et les commentaires quand c'est utile.

## Principes non négociables

- **P1** – L'outil suggère, Philippe décide. Aucune affectation, modification ou réaffectation
  sans action humaine. Seules exceptions automatiques : remise dans le tampon quand une absence
  recouvre une activité (R-09) et création d'absences depuis les mails IRH (F-30).
- **P2** – Aucun mail ne part sans validation de Philippe (brouillon dans `outbound_messages`).
- **P3** – Aucune donnée ne quitte l'infrastructure interne (modèle d'IA interne uniquement,
  aucun service SaaS, aucun CDN, aucune télémétrie).
- **P4** – Journées entières, calendrier belge. Une période = `start_date` + `end_date` incluses.
  **Il n'existe pas de nombre de jours stocké** : il se calcule (`end - start + 1`).
- **P5** – Ne rien coder de la V2 (compétences, langues, règle des 60 %, fatigue, suggestions,
  compagnonnage, statistiques, relance automatique).

## Règles à ne jamais enfreindre

- `requests.status` n'est écrit que par `app/rules/status.py::compute_request_status` (R-01).
- Assignment **actif** = `draft`, `pending_response`, `accepted`. `refused` / `cancelled` sont
  conservés, jamais supprimés.
- Toute écriture utilise le verrouillage optimiste (`version`) ; conflit → HTTP 409 (R-12).
- Toute création par l'agent : `needs_review = true` ; toute modification ou annulation détectée :
  `change_requests` en attente (R-07). Un message source n'est traité qu'une fois (R-13).
- Lien de réponse technicien : GET affiche, seul le POST enregistre (F-22).
- `audit_log` est en ajout seul (NF-05) : chaque action métier y écrit une ligne.
- Aucun secret dans le dépôt (NF-03) : tout passe par les variables d'environnement.
- **Ne jamais modifier une migration Alembic existante** : en créer une nouvelle
  (`alembic revision --autogenerate -m "..."`), la relire, puis vérifier `alembic check`.

## Méthode

1. Un prompt = une exigence ou un petit groupe (« F-20 et R-02 »).
2. Écrire d'abord les tests, puis le code.
3. Fin de phase : revue dédiée (« vérifie P1 et R-01 à R-13 ») avant de passer à la suite.
4. Si une décision change, mettre à jour le cahier (section concernée + historique des versions).

## Stack et conventions

- Backend : Python 3.12, FastAPI, SQLAlchemy 2 (typé `Mapped[...]`), Alembic, Pydantic v2.
  Code dans `backend/app/`, règles métier pures dans `backend/app/rules/` (sans accès HTTP).
- Front : TypeScript strict, React, Vite, Tailwind, dnd-kit. Grille de planning maison en CSS Grid.
- Base : PostgreSQL (SQLite accepté en dev et en tests).
- Interface en français, dates JJ/MM/AAAA, semaine du lundi, fuseau Europe/Brussels.
  Les dates métier circulent en ISO `AAAA-MM-JJ`.
- La couleur ne porte jamais seule l'information (codes, icônes, hachures).

## Commandes

```bash
# Backend (depuis backend/)
uv venv -p 3.12 .venv && uv pip install -p .venv -e '.[dev]'
.venv/bin/alembic upgrade head && .venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload          # API sur :8000, docs sur /api/docs
.venv/bin/pytest && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy app

# Front (depuis frontend/)
npm install && npm run dev                        # :5173, proxy /api vers :8000
npm test && npm run build

# Tout en conteneurs (depuis la racine)
cp .env.example .env    # puis définir POSTGRES_PASSWORD
docker compose up -d --build && docker compose exec api python -m app.seed
```

## Authentification (F-80, NF-01)

`AUTH_MODE` : `dev` (utilisateur simulé, en-tête `X-Dev-User`, interdit en production),
`proxy` (le reverse proxy d'entreprise authentifie et transmet l'e-mail dans
`PROXY_USER_HEADER` ; l'API ne doit alors être joignable que via ce proxy), `oidc` (jeton
Bearer validé par JWKS). L'utilisateur doit exister dans `users` (rôles `admin`, `planner`).

## État d'avancement

- Phase 0 : faite (socle, modèle de données complet, migration 0001, auth, seed, tests).
- Phase 1 : faite. API `GET /planning`, `GET/PATCH /assignments/{id}`, CRUD `/absences`
  (`backend/app/api/planning.py`) ; grille `frontend/src/planning/` (calculs purs dans `layout.ts`).
  Reporté : nouveau mail après déplacement (F-07 → F-20, phase 3), R-09 sur absence (F-32, phase 6),
  voyants de conflit (F-08, phase 4).
- Prochaine étape : phase 2 (tampon, vignettes, formulaire manuel, F-10 à F-15).

## Repères front

- Glisser-déposer : `@dnd-kit/core`, une barre = poignée début + corps (déplacement) + poignée fin.
  Pas de transformation visuelle : un aperçu (`drag-preview`) est dessiné dans la ligne cible.
- Le panneau latéral offre l'alternative clavier au glisser-déposer (technicien, début, fin).
- Toute écriture envoie `version` ; 409 → message et rechargement ; 428 → dialogue de confirmation.
