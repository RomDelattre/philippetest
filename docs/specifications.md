# Cahier des spécifications – Planning ATS et agent de gestion des demandes

Version 0.5 – 3 novembre 2026 – Document de référence pour le développement (vibe coding)

## 0. Comment utiliser ce document

Ce document est la source de vérité du projet. Chaque exigence a un identifiant (F-xx fonctionnelle, R-xx règle métier, NF-xx non fonctionnelle) pour pouvoir la citer dans un prompt, par exemple « implémente F-12 en respectant R-05 ». Les hypothèses non confirmées sont marquées **\[H\]** et les décisions à prendre **\[Q\]** ; elles sont regroupées en section 16. Les mots DOIT, NE DOIT PAS et PEUT ont leur sens habituel de spécification. Le contenu de ce fichier est à recopier, en tout ou partie, dans le fichier CLAUDE.md à la racine du dépôt pour que l'agent de code le garde en contexte.

**Historique des versions**

v0.1 (3 novembre 2026) : première version.

v0.2 (3 novembre 2026) : une période est désormais toujours exprimée par une date de début et une date de fin (suppression de days_count partout) ; liens de réponse en deux temps (GET affiche, POST enregistre) ; correction des exceptions de P1 ; définition de l'assignment actif ; ajout des tables users, mission_types, absence_proposals et notifications ; conservation temporaire du corps des mails ; précisions sur le déplacement (F-07), l'expiration des jetons (F-21), la fusion et la division (F-15) ; coquilles corrigées.

v0.3 (3 novembre 2026) : décisions de la phase 2. Déposer une vignette dans la période de la demande reprend les dates de la demande (R-03) ; modifier les dates d'une demande ne déplace pas ses affectations (F-14) ; retrait d'une affectation en brouillon ; fusion avec complément des champs vides et lien merged_into_id (F-15) ; champs attachment_url et merged_into_id ; GET /requests?view=buffer\|all.

v0.4 (3 novembre 2026) : décisions de la phase 3. Le jeton est créé à l'envoi du mail et jamais stocké en clair (F-21, NF-02) ; une seule confirmation au demandeur par demande, mise à jour à chaque acceptation (F-23) ; un refus pose le badge « refusée par un technicien » (F-24) ; réponse manuelle possible aussi sur un brouillon (F-25) ; déplacer une proposition envoyée vers un autre technicien prépare un mail d'information à l'ancien (F-07) ; connecteur d'envoi fichier / SMTP (section 4) ; variables de modèles supplémentaires (F-52).

v0.5 (3 novembre 2026) : décisions de la phase 4. Confirmation explicite d'un chevauchement ou d'une activité sur absence, à la dépose comme au déplacement (R-02) ; les conflits week-end et jour férié restent des voyants sur les barres sans entrer dans le centre d'alertes (R-05, F-40) ; calcul des jours ouvrés et date de référence de R-06 précisés ; centre d'alertes et réponses des techniciens réunis sous la cloche (F-40) ; paramètres d'alerte, dont la validité des liens (F-43).

## 1. Contexte et objectifs

Philippe Zander affecte une vingtaine de techniciens (armûriers / mécaniciens, plus quelques électroniciens) à des demandes de chefs de projet : missions, salons et démos, ateliers, formations, tirs. Les demandes arrivent par mail (surtout), Teams, formulaire SharePoint ou à l'oral, et changent souvent. Le planning actuel est un Excel avec macros VBA, cellules fusionnées et mails collés en commentaires. Il est abandonné : **aucune reprise de l'historique**.

Objectif de la V1 : une application web interne qui remplace l'Excel (vue techniciens en lignes, jours en colonnes), une zone tampon « À attribuer » alimentée par un agent qui lit mails, Teams et formulaires SharePoint, un flux d'attribution par mail avec validation humaine, des absences automatiques depuis les mails IRH, et des alertes. L'outil optimise le planning ; ce n'est pas un outil de sélection de techniciens.

Principes non négociables :

- **P1** – L'outil suggère, Philippe décide. Aucune affectation, aucune modification d'affectation et aucune réaffectation n'est faite sans action humaine. Seules exceptions automatiques autorisées : remise d'une activité dans le tampon quand une absence la recouvre (R-09) et création d'absences (F-30). Les annulations d'assignments prévues par R-08 et R-10 ne sont pas des exceptions : elles découlent d'une décision de Philippe.

- **P2** – Aucun mail ne part sans validation de Philippe en V1.

- **P3** – Aucune donnée ne quitte l'infrastructure interne, modèle d'IA compris.

- **P4** – Raisonnement en journées entières, calendrier belge. Une période est toujours définie par une date de début et une date de fin incluses ; il n'existe aucune durée saisie seule (pas de nombre de jours).

- **P5** – Ne rien coder qui concerne la V2 (matrice de compétences, langues, règle des 60 %, fatigue, suggestions, compagnonnage, statistiques, relance automatique des infos manquantes).

## 2. Périmètre

### 2.1 Inclus en V1

Planning web (F-01 à F-08), zone tampon et vignettes (F-10 à F-15), attribution et réponses des techniciens (F-20 à F-26), absences (F-30 à F-32), conflits et alertes (F-40 à F-43), boîte d'envoi à valider (F-50 à F-52), agent d'ingestion mail, Teams, SharePoint (F-60 à F-69), paramètres, journal d'audit (F-70 à F-72), authentification et droits (F-80).

### 2.2 Exclu de la V1

Import de l'Excel ou de l'archive 2025, statistiques, suggestions de techniciens, matrice de compétences, langues, règle des 60 %, plan B, fatigue, mail automatique de relance des infos manquantes, demi-journées, plusieurs activités le même jour sur une ligne, planning détaillé des électroniciens, accès techniciens ou chefs de projet, application mobile. En revanche le modèle de données DOIT déjà horodater les étapes (demande, attribution, réponse, réalisation) pour permettre les statistiques plus tard, sans développement supplémentaire.

## 3. Contraintes et hypothèses d'environnement

- Entreprise du secteur de l'armement, hébergement interne obligatoire, données sensibles.

- Microsoft 365 complet disponible, Power Platform autorisé, Microsoft 365 Copilot disponible, Copilot Studio non, Azure considéré comme indisponible.

- Modèles d'IA internes, payés et hébergés par l'entreprise. **\[H\]** Ils exposent une API de type chat/completions compatible OpenAI ; à confirmer (Q-02).

- Accès à la boîte mail de Philippe : droits obtenus par le développeur. Pas d'API ni d'export de l'IRH : les absences passent uniquement par mails.

- Le développeur n'a pas de préférence de stack ni de niveau de code déclaré : la stack est recommandée en section 5 pour maximiser la fiabilité du code généré.

- Utilisateurs : Philippe (tous droits) et Olivier (planning et tampon, sans fonctions agent).

## 4. Architecture

L'application se compose de cinq blocs, tous déployés sur un serveur interne (conteneurs).

1.  **Front web** : application monopage servie en HTTPS interne.

2.  **API backend** : toute la logique métier, les règles de conflit, les statuts, l'audit.

3.  **Base de données** relationnelle.

4.  **Worker agent** : processus planifié qui récupère les sources, appelle le modèle d'IA interne et crée des propositions.

5.  **Connecteurs Microsoft** : couche d'accès à Outlook, Teams, SharePoint et à l'envoi de mails, isolée derrière des interfaces pour pouvoir changer de méthode d'accès sans toucher au reste.

Flux principal : source (mail, Teams, SharePoint) → connecteur → table source_messages → classification et extraction par le modèle → proposition (requests ou change_requests ou absences) → validation humaine → planning. Les mails sortants suivent : brouillon dans outbound_messages → validation de Philippe → envoi via le connecteur.

### 4.1 Accès aux sources Microsoft : deux options **\[Q-01\]**

- **Option A (recommandée si l'IT l'autorise)** : inscription d'une application dans l'identité d'entreprise avec les permissions Graph strictement nécessaires, limitées à la boîte de Philippe (politique d'accès applicatif). Le worker interroge directement mails, Teams et la liste SharePoint.

- **Option B (si l'IT refuse l'option A)** : flux Power Automate (autorisé) qui détectent les nouveaux mails, messages Teams et éléments SharePoint puis appellent un endpoint POST /api/ingest/raw de l'API avec un secret partagé. L'envoi des mails passe alors aussi par un flux Power Automate déclenché par l'API.

Dans les deux cas le reste de l'application est identique : le connecteur produit toujours le même objet RawEvent (section 9.1). Développer d'abord l'endpoint d'ingestion, qui sert aussi aux tests.

## 5. Stack recommandée

- Front : TypeScript, React, Vite, Tailwind, dnd-kit pour le glisser-déposer. La grille de planning est un composant maison en CSS Grid, sans bibliothèque de calendrier générique.

- Back : Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2. Le worker utilise APScheduler dans un conteneur séparé.

- Base : PostgreSQL (SQLite accepté en développement).

- Auth : OpenID Connect avec le compte professionnel (Entra ID) **\[H\]** ; à défaut, authentification Windows via le reverse proxy.

- Déploiement : Docker Compose sur un serveur interne, reverse proxy HTTPS.

- Tests : pytest, Vitest, Playwright pour le parcours principal.

- Langue de l'interface : français. Dates au format JJ/MM/AAAA, semaine commençant le lundi, fuseau Europe/Brussels.

## 6. Modèle de données

Toutes les tables ont id (UUID), created_at, updated_at et version (verrouillage optimiste), sauf audit_log et holidays qui n'ont que id et created_at.

- users : email (unique), display_name, role (admin ou planner), active. Les utilisateurs sont créés par le seed ou par un administrateur ; l'identité vient du compte d'entreprise (NF-01).

- **technicians** : last_name, first_name, email, role (mechanic ou electronician), active, sort_order. Les noms réels remplacent les noms anonymisés (A, B, C) via un script de seed.

- requests (la vignette) : ref lisible (ex. D-2026-0042), type_code (MI, SD, AT, FI_FE, TI_TE, nullable tant que non défini), title, requester_name, requester_email, cf, client, location, objective, technicians_needed, start_date, end_date, date_flexible (booléen), flex_justification, comments, products (JSON : produit, munitions, commentaire), status, cancelled_at, cancelled_by, missing_fields (JSON), needs_review (booléen), badges (JSON : dates modifiées, technicien absent), origin (mail, teams, sharepoint, manual), confidence, requested_at, needed_by, attachment_url (lien de pièce jointe, F-12), merged_into_id (demande conservée après une fusion, F-15). Il n'y a pas de champ nombre de jours : le nombre de jours affiché est calculé (end_date − start_date + 1, jours calendaires) et n'est jamais stocké. start_date et end_date sont nullables tant qu'elles ne sont pas connues ; si les deux sont renseignées, end_date ≥ start_date. status est stocké pour le filtrage mais n'est écrit que par la fonction de calcul R-01 du backend.

- assignments : request_id, technician_id, start_date, end_date (obligatoires, end_date ≥ start_date), status (draft, pending_response, accepted, refused, cancelled), response_token_hash, token_expires_at, token_used_at, proposed_at, responded_at, partner_electronician_id (nullable, pour le binôme).

- **absences** : technician_id, start_date, end_date, category (leave, sick, recovery, other), source_message_id. Aucun motif médical stocké.

- **holidays** : date, label, préremplie pour la Belgique (fixes et mobiles dérivés de Pâques) sur 2026-2030.

- source_messages : source (mail, teams, sharepoint), external_id (unique avec source), request_id (demande liée, nullable), conversation_id, received_at, sender, subject, body_excerpt, body_text, body_purged_at, web_link, classification, confidence, extraction (JSON), processed_at, processing_status, error. body_text est conservé body_retention_days jours (paramètre, défaut 30) pour l'affichage côte à côte (F-61), le retraitement et le jeu d'évaluation, puis purgé ; extrait, lien et extraction sont conservés \[Q-05\].

- **change_requests** : request_id, kind (modification, cancellation), proposed_changes (JSON, anciens et nouveaux champs), source_message_id, status (pending, applied, ignored), decided_by, decided_at.

- absence_proposals : absences détectées dont le technicien n'a pas pu être résolu sans ambiguïté (F-30) : source_message_id, person_name, candidate_technician_ids (JSON), start_date, end_date, category, status (pending, applied, ignored), decided_by, decided_at.

- **outbound_messages** : kind (tech_proposal, requester_confirmation, generic), to_email, subject, body, status (draft, validated, sent, failed, discarded), request_id, assignment_id, validated_by, sent_at, error.

- **audit_log** : actor (utilisateur, agent ou system), action, entity_type, entity_id, before, after (JSON), horodatage.

- **settings** : paires clé/valeur (seuils d'alerte, modèles de mails, fréquence de scrutation).

- mission_types : code (MI, SD, AT, FI_FE, TI_TE, plus AB pour l'absence et « ? » pour l'activité incertaine), label, color, sort_order, active (F-03, F-71) \[Q-08\].

- notifications : notifications internes (F-23, F-24) : kind, message, request_id, assignment_id, read_at.

- Les alertes (F-40) ne sont pas stockées : elles sont calculées à la demande à partir de l'état courant, ce qui les fait disparaître dès que la cause disparaît (F-41).

Un request nécessitant N techniciens possède jusqu'à N assignments actifs. Les statuts d'un assignment et de la demande sont décrits en section 7.

Un assignment est **actif** quand son statut est draft, pending_response ou accepted. Les statuts refused et cancelled sont inactifs ; ces assignments sont conservés pour l'historique et ne sont jamais supprimés.

## 7. Règles métier

- **R-01** Statut d'une demande (calculé). to_assign : aucun assignment actif. partially_assigned : au moins un actif mais moins que technicians_needed. pending : tous les postes pourvus par des assignments actifs, dont au moins un en draft ou pending_response. confirmed : tous les postes sont accepted. cancelled : cancelled_at renseigné par décision de Philippe ; ce statut prime sur tous les autres. Un refus rend l'assignment inactif (refused, conservé) et la demande repasse en to_assign ou partially_assigned.

- **R-02** Une activité par technicien et par jour. La grille n'a qu'une ligne par technicien. Un chevauchement, ou une activité posée sur une absence, n'est autorisé qu'après confirmation explicite (« Placer quand même ») au moment de la dépose ou du déplacement, et déclenche un conflit rouge (R-05).

- **R-03** Jours et périodes. Journées entières uniquement. Une demande et un assignment sont toujours définis par une date de début et une date de fin incluses ; il n'existe pas de nombre de jours saisi. Déposer une vignette datée sur un jour compris dans sa période crée un assignment couvrant exactement les dates de la demande. La déposer sur un jour hors de sa période décale la période à ce jour en gardant le même nombre de jours calendaires et demande une confirmation « dates différentes de la demande » ; la demande garde ses dates. Une demande sans dates complètes déposée sur le jour J crée un assignment de J à J, redimensionnable ; la confirmation propose (coché par défaut) d'écrire ces dates dans la demande.

- **R-04 Calendrier.** Week-ends et jours fériés belges sont grisés. Une activité peut les couvrir (salons, tirs) sans blocage.

- **R-05** Conflits. Rouge : chevauchement de deux activités d'un même technicien, ou activité sur une absence. Orange : activité sur week-end ou jour férié, modification de dates proposée sur une demande déjà attribuée, demande en attente de réponse depuis plus de N jours calendaires (paramètre, défaut 3), ou lien de réponse expiré (F-21). Un conflit est recalculé à chaque lecture, en tenant compte des activités voisines même hors de la fenêtre affichée, et n'est jamais corrigé automatiquement. Les conflits week-end et jour férié sont affichés sur les barres mais ne figurent pas dans le centre d'alertes, pour ne pas le noyer (salons et tirs les couvrent souvent).

- **R-06** Alerte d'attribution. Une demande to_assign ou partially_assigned dont start_date est dans moins de alert_orange_days jours ouvrés (défaut 10) passe en orange, et dans moins de alert_red_days (défaut 5) en rouge \[Q-03\]. Les jours ouvrés se comptent de demain jusqu'à la date de début incluse, hors week-ends et jours fériés belges ; une demande déjà commencée est rouge (« déjà commencée »), une demande terminée n'a plus d'alerte. Sans start_date, la date de référence est needed_by si elle existe ; sinon il n'y a pas d'alerte de date, seulement l'icône « informations manquantes ».

- **R-07 Jamais de décision silencieuse.** Toute création par l'agent est marquée needs_review = true. Toute modification ou annulation détectée est une change_request en attente.

- **R-08 Glissement.** Quand Philippe applique une modification de dates sur une demande attribuée, les assignments accepted ou pending sont annulés, la demande repasse en to_assign avec le badge « dates modifiées », et l'ancien technicien est conservé dans l'historique.

- **R-09 Absence sur activité.** Quand une absence recouvre un assignment actif, celui-ci est annulé, la demande est remise dans le tampon avec le badge « technicien absent » et une alerte est créée. C'est le seul cas de mouvement automatique, et il va vers le tampon, jamais vers un autre technicien.

- **R-10** Annulation. L'annulation d'une demande, décidée par Philippe, libère ses assignments actifs (cancelled) ; un mail de prévenance aux techniciens concernés est préparé en brouillon.

- **R-11 Binôme.** Un assignment peut référencer un électronicien en partner_electronician_id. Cette référence est purement informative ; elle ne génère ni mail ni contrôle de conflit en V1 **\[Q-04\]**.

- **R-12 Verrouillage.** Deux utilisateurs peuvent être connectés ; toute écriture vérifie version, sinon l'API renvoie 409 et le front recharge.

- **R-13 Idempotence.** Un même message source (source + external_id) ne crée jamais deux propositions.

## 8. Spécifications fonctionnelles

### 8.1 Planning (F-01 à F-08)

- **F-01** La vue principale affiche les techniciens mécaniciens actifs en lignes, les jours en colonnes, avec en-têtes mois et semaines (numéro de semaine ISO). En dessous, une section distincte liste les électroniciens (R-11).

- **F-02** Fenêtre glissante par défaut de 8 semaines autour d'aujourd'hui, avec zoom 4 semaines, 12 semaines et 6 mois, défilement horizontal fluide, ligne des noms figée et ligne des dates figée.

- **F-03** Chaque assignment est une barre couvrant ses jours, colorée par type_code, avec code, libellé court, lieu. Style distinct pour pending_response (hachuré) et accepted (plein). Les couleurs viennent d'une table de paramètres modifiable.

- **F-04** Les absences sont affichées en gris avec leur catégorie ; week-ends et jours fériés en fond grisé ; le jour courant est surligné.

- **F-05** Le clic sur une barre ouvre la fiche détaillée (F-14) dans un panneau latéral.

- **F-06** Filtres : technicien, type de mission, statut, demande. Recherche texte sur client, CF, demandeur.

- **F-07** Déplacer une barre au glisser-déposer (autre technicien ou autres dates) et la redimensionner. Tout déplacement d'un assignment pending_response ou accepted passe par une confirmation, remet l'assignment en draft, révoque son jeton (l'ancien lien devient invalide) et prépare un nouveau mail (F-20).

- **F-08** Indicateur visuel de conflit (voyant) sur chaque barre ou cellule concernée, rouge ou orange, avec info-bulle expliquant la cause.

### 8.2 Zone tampon et vignettes (F-10 à F-15)

- **F-10** Panneau « À attribuer » toujours visible à côté du planning (repliable), listant les demandes to_assign, partially_assigned et needs_review, triées par start_date croissante.

- **F-11** Une vignette affiche : réf, type (code et couleur), demandeur, client, lieu, dates de début et de fin, nombre de jours (calculé), nombre de techniciens restants à trouver, icônes d'alerte (date proche, à vérifier, modification en attente, annulation en attente, informations manquantes, badges R-08 et R-09).

- **F-12** Création manuelle d'une demande via un formulaire reprenant les champs du formulaire SharePoint existant : demandeur, objectif de la mission, CF, début, fin, client, nombre de techniciens, flexibilité et justification, commentaires, lignes produit / munitions / commentaire, pièces jointes en V1 limitées à un lien.

- **F-13** Les informations minimales obligatoires pour considérer une demande complète sont : type, nombre de techniciens, date de début, date de fin, lieu **\[Q-06\]**. Les champs manquants sont listés dans missing_fields et affichés ; leur absence n'empêche jamais l'attribution.

- **F-14** Fiche détaillée : tous les champs éditables, historique des événements, messages sources avec lien vers le mail ou le message d'origine, assignments, conflits, changements en attente. Modifier les dates d'une demande ne déplace jamais ses assignments (P1) : ils se déplacent sur le planning. Un assignment en brouillon (jamais envoyé) peut être retiré depuis la fiche ; il passe en cancelled et reste dans l'historique. Le nombre de techniciens ne peut pas descendre sous le nombre d'assignments actifs.

- **F-15** Fusion de deux vignettes (doublons détectés ou non) et division d'une demande en deux périodes. Fusion : Philippe choisit la demande conservée ; l'autre est annulée (merged_into_id pointe vers la conservée) et ses messages sources et ses assignments actifs sont rattachés à la demande conservée, dont les champs vides sont complétés ; la fusion est refusée si le nombre d'assignments actifs dépasse alors technicians_needed ou si un même technicien est affecté aux deux. Division : à une date de coupure (premier jour de la seconde partie) ; chaque assignment est rattaché à la partie qu'il recouvre ; un assignment à cheval est coupé en deux assignments de même technicien et même statut, sans nouveau mail.

### 8.3 Attribution (F-20 à F-26)

- **F-20** Déposer une vignette sur un technicien et des dates crée un assignment draft, calcule les conflits (R-05), puis crée un brouillon de mail dans outbound_messages (tech_proposal) et affiche un message « Mail préparé, à valider ».

- **F-21** Le mail au technicien contient le résumé de la demande et deux liens « J'accepte » et « Je refuse ». Ils portent le même jeton à usage unique, propre à l'assignment, expirant après 14 jours (paramètre) \[Q-07\]. Le brouillon garde les variables {lien_accepter} et {lien_refuser} ; le jeton n'est créé qu'au moment de l'envoi, seule son empreinte est stockée, et le corps conservé après envoi remplace les liens par « \[lien J'accepte\] » / « \[lien Je refuse\] » (NF-02). L'envoi passe l'assignment de draft à pending_response. À l'expiration, l'assignment reste pending_response et une alerte orange « lien expiré » apparaît ; Philippe peut préparer un nouveau mail (nouveau jeton) ou saisir la réponse (F-25). Les liens pointent vers PUBLIC_BASE_URL/api/respond/…, chemin qui doit rester accessible sans l'authentification d'entreprise.

- **F-22** Ouvrir un lien (GET) affiche une page interne minimale (aucune authentification, aucune autre information que le résumé) avec un bouton de confirmation de la réponse choisie ; la réponse n'est enregistrée qu'au clic (POST). Ainsi, les analyses automatiques de liens (antivirus de la messagerie, aperçus) ne consomment jamais le jeton. Un jeton déjà utilisé, révoqué ou expiré est rejeté avec un message clair.

- **F-23** Acceptation : l'assignment passe en accepted, un brouillon requester_confirmation est créé pour le demandeur, une notification interne (table notifications) s'affiche dans l'application. Il n'existe qu'un brouillon de confirmation par demande : tant qu'il n'est pas envoyé, il est mis à jour à chaque nouvelle acceptation et liste les techniciens acceptés.

- **F-24** Refus : l'assignment passe en refused, la demande revient dans le tampon avec le nom du technicien refusant en historique et le badge « refusée par un technicien » (retiré à la prochaine attribution), et une notification informe Philippe.

- **F-25** Enregistrement manuel de la réponse : un bouton permet de marquer un assignment comme accepté ou refusé sans passer par le lien, y compris avant l'envoi du mail (le brouillon de proposition est alors retiré). Le lien envoyé devient inutilisable. Limite connue : après une division (F-15), la seconde moitié d'une proposition en attente n'a pas de lien propre ; sa réponse se saisit ici.

- **F-26** Annulation d'une proposition par Philippe : l'assignment est cancelled, le lien envoyé n'est plus valable et un brouillon de mail d'information est préparé pour le technicien. Il en va de même pour l'ancien technicien quand une proposition envoyée est déplacée vers un autre technicien (F-07).

### 8.4 Absences (F-30 à F-32)

- **F-30** Les mails IRH identifiés par l'agent (F-65) créent automatiquement des absences, après résolution du technicien par adresse mail puis par nom. Si la résolution est ambiguë, une proposition en attente (\`absence_proposals\`) est créée dans l'écran des propositions de l'agent (F-61).

- **F-31** Création, modification et suppression manuelles d'une absence depuis le planning.

- **F-32** Application de R-09 à chaque nouvelle absence, avec création d'une alerte « activités remises dans le tampon ».

### 8.5 Alertes et conflits (F-40 à F-43)

- **F-40** Centre d'alertes (cloche) listant : dates proches non attribuées, conflits, réponses refusées, réponses en attente depuis trop longtemps et liens expirés, changements en attente, activités remises dans le tampon. Les alertes rouges sont en tête. Un second onglet de la cloche regroupe les réponses des techniciens (F-23, F-24). Le compteur distingue rouges (⛔) et oranges (⚠).

- **F-41** Chaque alerte renvoie en un clic vers la vignette ou la barre concernée et disparaît quand la cause disparaît.

- **F-42** Pas de notifications externes en V1.

- **F-43** Paramètres d'alerte modifiables par Philippe (R-05, R-06) : seuils orange et rouge en jours ouvrés (le rouge doit être inférieur à l'orange), délai d'attente d'une réponse, validité des liens de réponse.

### 8.6 Mails à valider (F-50 à F-52)

- **F-50** Écran « Mails à valider » : liste des brouillons avec destinataire, objet, corps éditable, demande liée.

- **F-51** Actions : envoyer, envoyer un lot sélectionné, modifier, supprimer. Le statut passe à sent ou failed avec message d'erreur, et un nouvel envoi est possible.

- **F-52** L'expéditeur est Philippe (envoi depuis sa boîte via le connecteur). Les modèles de mails (proposition au technicien, confirmation au demandeur, annulation) sont des gabarits modifiables, avec les variables {demandeur}, {type}, {dates}, {lieu}, {lien_accepter}, {lien_refuser}, ainsi que {technicien}, {techniciens}, {ref}, {titre}, {client} et {cf}. Le modèle de proposition doit contenir les deux variables de lien. Olivier ne voit pas cet écran. En attendant le connecteur Microsoft \[Q-01\], l'envoi passe par un relais SMTP interne ou, en développement, par des fichiers .eml (MAIL_BACKEND).

### 8.7 Paramètres, audit, droits (F-70 à F-80)

- **F-70** Gestion de la liste des techniciens et électroniciens (ajout, désactivation, ordre d'affichage).

- **F-71** Gestion des types de mission : les cinq codes MI, SD, AT, FI/FE, TI/TE avec libellé et couleur **\[Q-08\]**, plus l'indication d'absence et d'activité incertaine.

- **F-72** Journal d'audit consultable par Philippe, filtrable par entité, acteur et date.

- **F-80** Rôles : admin (Philippe : tout) et planner (Olivier : planning, tampon, vignettes, absences ; pas d'agent, pas de mails à valider, pas de paramètres, pas d'audit) **\[Q-09\]**.

## 9. Agent d'ingestion

### 9.1 Objet commun à toutes les sources

{  
"source": "mail \| teams \| sharepoint",  
"external_id": "string",  
"conversation_id": "string \| null",  
"received_at": "ISO 8601",  
"sender_name": "string",  
"sender_email": "string \| null",  
"subject": "string \| null",  
"body_text": "string",  
"web_link": "string \| null",  
"attachments": \[{"name": "string"}\],  
"structured_fields": {}  
}

Pour SharePoint, structured_fields contient les champs du formulaire (Demandeur, Objectif, CF, Début, Fin, Client, Nombre de techniciens, Flexibilité, Justification, Commentaires, lignes Produit / Munitions / Commentaire) et l'extraction par modèle n'est pas nécessaire : le mapping est direct et déterministe.

### 9.2 Pipeline

1.  **Collecte** : le connecteur récupère les nouveaux éléments depuis le dernier curseur (toutes les 5 minutes, paramètre) et écrit un source_messages (R-13).

2.  **Préfiltrage déterministe** : ignorer newsletters, notifications automatiques, réponses automatiques, messages sans contenu textuel. Ce filtre est configurable et ne doit rien supprimer, seulement marquer ignored.

3.  **Classification** par le modèle interne : request, modification, cancellation, absence, other, avec un score de confiance.

4.  **Extraction** pour request, modification, cancellation, absence selon le schéma ci-dessous. Le modèle DOIT répondre en JSON valide uniquement ; toute réponse invalide est rejetée, retentée une fois, puis marquée en erreur dans source_messages.

5.  **Rapprochement** (modification et annulation) : retrouver la demande concernée par, dans l'ordre, conversation_id déjà lié, numéro de CF identique, même demandeur avec client et dates proches. Si le rapprochement est ambigu ou absent, la proposition est créée sans demande liée et Philippe choisit.

6.  **Création** : nouvelle demande → requests avec needs_review = true ; modification ou annulation → change_requests pending ; absence → F-30.

7.  **Journalisation** : chaque étape écrit dans audit_log avec actor = agent.

### 9.3 Schéma d'extraction

{  
"classification": "request \| modification \| cancellation \| absence \| other",  
"confidence": 0.0,  
"request": {  
"type_code": "MI \| SD \| AT \| FI_FE \| TI_TE \| null",  
"technicians_needed": 0,  
"start_date": "YYYY-MM-DD \| null",  
"end_date": "YYYY-MM-DD \| null",  
"location": "string \| null",  
"client": "string \| null",  
"cf": "string \| null",  
"requester_name": "string \| null",  
"date_flexible": true,  
"summary": "string"  
},  
"changes": {"field": "new_value"},  
"absence": {  
"person_name": "string",  
"start_date": "YYYY-MM-DD",  
"end_date": "YYYY-MM-DD",  
"category": "leave \| sick \| recovery \| other"  
},  
"missing_fields": \["string"\]  
}

Règles d'extraction : ne jamais inventer une valeur absente, mettre null ; résoudre les dates relatives (« semaine prochaine ») à partir de received_at ; une date de début et une durée explicite (« 3 jours à partir du 12/03 ») donnent end_date = début + durée − 1 jour calendaire ; une durée sans date de début (« 3 jours en mars ») laisse start_date et end_date à null, la durée est reprise dans summary et les deux dates vont dans missing_fields \[H\] ; si le mail est une réponse dans un fil, déduire l'objet du dernier message mais en tenant compte de l'historique cité ; les demi-journées sont arrondies à la journée entière.

### 9.4 Exigences

- **F-60** Le worker tourne en continu, avec reprise sur erreur et tableau de bord d'état (dernière exécution, nombre d'éléments traités, erreurs).

- **F-61** Écran « Propositions de l'agent » : liste des vignettes à vérifier, des changements en attente, des absences ambiguës, des messages classés en erreur ou en faible confiance ; chaque ligne montre le message source et l'extraction côte à côte.

- **F-62** Actions sur une proposition : accepter, corriger puis accepter, ignorer. Un message ignoré ne revient pas.

- **F-63** Les messages other ne sont jamais montrés à Philippe sauf via un onglet « Non classés » optionnel pour contrôler l'agent.

- **F-64** Teams : surveiller les chats et canaux auxquels Philippe participe, uniquement les nouveaux messages, et appliquer le même pipeline.

- **F-65** Mails IRH : reconnus par expéditeur et par classification absence. Liste d'expéditeurs IRH configurable.

- **F-66** SharePoint : surveiller la liste du formulaire ; chaque nouvel élément crée une demande, chaque élément modifié crée une change_request.

- **F-67** La confidentialité est un critère de conception : le texte envoyé au modèle est limité au sujet, à l'expéditeur et au corps (signatures et citations longues retirées), jamais aux pièces jointes en V1.

- **F-68** Le modèle et les prompts sont paramétrables dans un fichier de configuration (URL interne, nom du modèle, température 0). Aucune clé en dur.

- **F-69** Mode simulation : l'agent peut être lancé sur un dossier de mails de test sans accès Microsoft, pour développer et tester hors ligne.

## 10. API (résumé)

Préfixe /api, JSON, authentification obligatoire sauf /api/respond/{token} et /api/ingest/raw (secret partagé).

- GET /planning?from=&to= : techniciens, assignments, absences, jours fériés, conflits calculés.

- GET /requests?view=buffer\|all (vignettes), POST /requests, GET/PATCH /requests/{id}, POST /requests/{id}/merge, POST /requests/{id}/split.

- POST /requests/{id}/assignments (attribution, R-03), PATCH /assignments/{id} (déplacement, réponse manuelle), DELETE /assignments/{id} (retrait d'un brouillon ; l'annulation d'une proposition envoyée relève de F-26).

- GET /respond/{token}?answer=accept\|refuse : page de confirmation, sans effet. POST /respond/{token} (corps : answer) : enregistre la réponse.

- GET/POST/PATCH/DELETE /absences.

- GET /alerts, GET /notifications, POST /notifications/{id}/read, GET /agent/proposals (vignettes à vérifier, changements, absences ambiguës, erreurs), POST /agent/proposals/{id}/accept\|ignore, GET /agent/status.

- POST /change-requests/{id}/apply\|ignore.

- GET /outbox, PATCH /outbox/{id}, POST /outbox/send (lot), DELETE /outbox/{id}.

- GET /me, GET /health, GET/PATCH /settings, GET/PATCH /mission-types, GET /audit, GET/POST/PATCH /technicians.

- POST /ingest/raw (corps RawEvent).

## 11. Interface

L'écran principal est une page unique : barre supérieure (filtres, zoom, cloche, boutons Mails à valider et Propositions de l'agent avec compteurs), zone tampon à gauche ou en bas, grille de planning dominante, panneau latéral de détail à droite. Le style doit rester sobre et dense, lisible sur un écran 1920 px. Le glisser-déposer doit afficher l'aperçu des jours couverts et signaler les conflits avant le lâcher. Tout état vide, chargement et erreur est traité. Le contraste doit être suffisant et les couleurs ne doivent jamais être le seul porteur d'information (codes, icônes, hachures).

## 12. Sécurité et protection des données

- **NF-01** Authentification de tous les utilisateurs par le compte d'entreprise ; aucune création de compte locale.

- **NF-02** Les liens de réponse technicien utilisent un jeton aléatoire de 128 bits minimum, stocké haché, à usage unique, expirant.

- **NF-03** Secrets (accès Graph, modèle, base) dans des variables d'environnement ou un coffre interne, jamais dans le dépôt.

- **NF-04** Absences : seule la catégorie est conservée. Le corps des mails est conservé body_retention_days jours (défaut 30) puis purgé ; extrait, lien et extraction sont conservés \[Q-05\].

- **NF-05** Journal d'audit non modifiable depuis l'application, conservé selon la politique interne.

- **NF-06** Sauvegardes quotidiennes de la base, test de restauration documenté.

- **NF-07** Principe du moindre privilège pour les permissions Microsoft, limitées à la boîte de Philippe et à la liste SharePoint concernée.

- **NF-08** Validation formelle par l'IT et le DPO avant la mise en production de l'agent **\[Q-10\]**.

## 13. Exigences non fonctionnelles

- **NF-10** Affichage d'une fenêtre de 8 semaines × 25 lignes en moins de 1 seconde ; glisser-déposer fluide à 60 images par seconde.

- **NF-11** Calcul de conflits côté serveur, réponse en moins de 300 ms pour une fenêtre de 6 mois.

- **NF-12** Traitement d'un mail par l'agent en moins de 60 secondes, avec 100 mails par jour dont environ 20 demandes (volume à confirmer).

- **NF-13** Disponibilité cible 99 % en heures ouvrées ; l'indisponibilité de l'agent ne doit jamais bloquer le planning.

- **NF-14** Code typé, linté, formaté, migrations versionnées, journalisation structurée.

## 14. Tests et données de test

- Un jeu de seed : 20 mécaniciens et 5 électroniciens fictifs (A, B, C…), jours fériés belges 2026-2030, 30 demandes variées.

- Un dossier fixtures/mails/ de mails anonymisés : les deux exemples de demandes disponibles (visite de délégation, visite AHF), plus des mails fabriqués de modification, d'annulation, d'absence IRH et de bruit. Demander à Philippe des exemples réels anonymisés dès que possible, car ce sont les cas qui règlent la qualité de l'agent.

- Tests unitaires obligatoires sur : calcul de statut (R-01), conflits (R-05), alertes (R-06), jours fériés belges, rapprochement (9.2 étape 5), jetons de réponse (dont : un GET ne consomme jamais le jeton), idempotence (R-13), calcul des périodes (R-03).

- Un jeu d'évaluation de l'agent (mails → JSON attendu) avec un taux minimal de réussite par champ avant mise en service, par exemple 90 % sur classification et 85 % sur dates et nombre de techniciens.

- Un test de bout en bout : création d'une demande par mail simulé → vignette → attribution → mail validé → acceptation par jeton → mail de confirmation en brouillon.

## 15. Plan de développement par phases

Chaque phase doit être utilisable et testée avant la suivante. À la fin de chaque phase, mettre à jour ce document si une décision change.

| Phase | Contenu                                                                                       | Critère de fin                                                |
|-------|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------|
| 0     | Dépôt, Docker Compose, base, migrations, auth, seed, CLAUDE.md                                | L'application démarre en local avec données de test           |
| 1     | Planning (F-01 à F-08 sans conflits), techniciens, fériés, absences manuelles                 | Philippe peut visualiser et déplacer des activités            |
| 2     | Tampon, vignettes, formulaire manuel (F-10 à F-15)                                            | Une demande saisie apparaît et s'attribue par glisser-déposer |
| 3     | Attribution, boîte d'envoi, jetons, réponses (F-20 à F-26, F-50 à F-52)                       | Parcours complet avec mails validés                           |
| 4     | Conflits, alertes, centre d'alertes (F-40 à F-43, F-08)                                       | Tous les cas R-05 et R-06 testés                              |
| 5     | Agent mail en mode simulation, puis branché à la boîte de Philippe (F-60 à F-63, F-67 à F-69) | Évaluation au-dessus des seuils                               |
| 6     | Absences IRH, modifications, annulations (F-30 à F-32, F-65, R-08 à R-10)                     | Alertes correctes sur cas simulés                             |
| 7     | Teams et SharePoint (F-64, F-66)                                                              | Trois sources alimentées                                      |
| 8     | Audit, paramètres, droits d'Olivier, finitions, sauvegardes, documentation (F-70 à F-80, NF)  | Présentation finale à Philippe                                |

Les phases 1 à 4 ne dépendent d'aucune autorisation IT : elles peuvent démarrer immédiatement, pendant que la demande d'accès Microsoft (Q-01, Q-10) est traitée.

**État au 3 novembre 2026** : phases 0 à 4 réalisées (socle ; planning et absences manuelles ; tampon, vignettes, fiche, fusion et division ; attribution par mail et réponses ; conflits R-05, alertes R-06, voyants F-08, centre d'alertes F-40 à F-43, confirmation des chevauchements R-02). Reporté volontairement : application ou rejet des changements en attente, R-08 à R-10, absences IRH (phase 6) ; agent (phase 5). Reste à brancher l'OIDC réel \[Q-15\] et le connecteur Microsoft d'envoi \[Q-01\].

### 15.1 Conseils pour le vibe coding

- Un fichier CLAUDE.md contenant les principes P1 à P5, la stack, les conventions et ce document en référence.

- Un prompt par exigence ou petit groupe d'exigences, toujours avec les identifiants (« F-20 et R-02 »), et la demande explicite d'écrire d'abord les tests.

- Faire relire chaque phase par un nouveau prompt de revue (« vérifie le respect de P1 et des règles R-01 à R-13 ») avant de continuer.

- Ne jamais laisser l'agent de code modifier les migrations existantes ; en créer de nouvelles.

## 16. Questions ouvertes et hypothèses

| Id   | Sujet                                                                        | Hypothèse de travail                                                                                                                                        |
|------|------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Q-01 | Méthode d'accès Microsoft (Graph direct ou Power Automate)                   | À décider avec l'IT ; connecteur abstrait pour ne pas bloquer                                                                                               |
| Q-02 | API du modèle interne (format, modèle, limites)                              | Compatible OpenAI ; à confirmer                                                                                                                             |
| Q-03 | Délais d'alerte                                                              | 10 et 5 jours ouvrés                                                                                                                                        |
| Q-04 | Binôme électronicien                                                         | Simple mention, sans mail ni contrôle                                                                                                                       |
| Q-05 | Durée de conservation du contenu des mails                                   | Corps conservé 30 jours (paramètre) puis purgé ; extrait, lien et extraction conservés                                                                      |
| Q-06 | Informations minimales d'une demande                                         | Type, nombre de techniciens, date de début, date de fin, lieu                                                                                               |
| Q-07 | Réponse du technicien par lien dans le mail                                  | Lien à jeton, réponse enregistrée après clic sur la page (POST) ; saisie manuelle en secours ; le serveur doit être joignable depuis le poste du technicien |
| Q-08 | Signification et couleur des codes MI, SD, AT, FI/FE, TI/TE                  | À fournir par Philippe                                                                                                                                      |
| Q-09 | Droits d'Olivier                                                             | Planning, tampon et absences en modification, sans agent ni mails                                                                                           |
| Q-10 | Validation IT et DPO                                                         | Prérequis avant mise en production de l'agent                                                                                                               |
| Q-11 | Teams : chats et canaux couverts                                             | Ceux de Philippe uniquement ; un demandeur qui écrit à quelqu'un d'autre ne sera pas vu                                                                     |
| Q-12 | Volume réel de mails                                                         | 100 par jour dont 20 demandes, à mesurer                                                                                                                    |
| Q-13 | Signification des codes AB et du symbole « ? » de l'Excel                    | AB = absence, « ? » = activité incertaine ; à confirmer                                                                                                     |
| Q-14 | Serveur interne cible (OS, Docker autorisé, nom de domaine interne)          | À obtenir de l'IT avant la phase 8                                                                                                                          |
| Q-15 | Paramètres OpenID Connect (tenant, identifiant d'application, URL de retour) | Mode développement avec utilisateur simulé (AUTH_MODE=dev) ; OIDC activé dès réception des paramètres                                                       |
