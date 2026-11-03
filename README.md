# Planning ATS

Application web interne qui remplace le planning Excel des techniciens : grille techniciens × jours,
zone tampon « À attribuer », attribution par mail avec validation humaine, absences issues des
mails IRH, alertes, et agent d'ingestion (mail, Teams, SharePoint) branché sur un modèle d'IA interne.

- Spécifications : [`docs/specifications.md`](docs/specifications.md) (v0.4)
- Consignes de développement : [`CLAUDE.md`](CLAUDE.md)

## Démarrage rapide (Docker)

```bash
cp .env.example .env          # définir au minimum POSTGRES_PASSWORD
docker compose up -d --build
docker compose exec api python -m app.seed
```

L'application est servie sur http://localhost:8080 (API : `/api`, documentation : `/api/docs`).
En mode `AUTH_MODE=dev`, un sélecteur permet de passer de Philippe (admin) à Olivier (planificateur).

Derrière un proxy d'entreprise qui inspecte le TLS, renseigner `EXTRA_CA_FILE` (chemin du
certificat racine, placé dans le dossier du projet, par exemple `.certs/`) pour que le build
puisse télécharger les dépendances.

## Mails

Aucun mail ne part sans validation dans l'écran « Mails à valider » (administrateur).
`MAIL_BACKEND=file` écrit les mails en `.eml` dans le volume `mails` (développement) ;
`MAIL_BACKEND=smtp` passe par le relais interne (`SMTP_HOST`, `SMTP_PORT`…).
Les liens « J'accepte / Je refuse » pointent vers `PUBLIC_BASE_URL/api/respond/…` : ce chemin doit être
exempté de l'authentification d'entreprise sur le reverse proxy.

## Remplacer les techniciens anonymisés par les vrais noms

```bash
docker compose cp mon-fichier.csv api:/tmp/techniciens.csv
docker compose exec api python -m app.seed --no-demo --technicians /tmp/techniciens.csv
```

Format : voir `backend/data/technicians.example.csv` (séparateur `;`).

## Structure

```
backend/   API FastAPI, modèle SQLAlchemy, migrations Alembic, seed, tests pytest
frontend/  React + Vite + Tailwind, tests Vitest
docs/      cahier des spécifications (Word et Markdown)
```
