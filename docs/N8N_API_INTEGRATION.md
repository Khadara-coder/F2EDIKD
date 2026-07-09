# Integration n8n avec l'API EDIFACT sur VM Azure

## Objectif

Le flux cible est celui-ci:

1. Outlook recoit un email contenant une commande.
2. n8n detecte l'email, recupere la piece jointe PDF et filtre les vraies commandes.
3. n8n envoie le PDF a l'application EDIFACT via API sur la VM Azure.
4. L'application analyse le PDF, determine un statut metier et enregistre la conversion.
5. Si la commande est acceptable automatiquement, elle peut etre envoyee vers SAP/Esker par SFTP.
6. Si la commande doit etre revue, elle reste en statut `REVIEW_REQUIRED` jusqu'a validation operateur.

```mermaid
flowchart LR
  A[Outlook] --> B[n8n]
  B --> C[Extraction piece jointe PDF]
  C --> D[POST /api/proxy/convert]
  D --> E{Decision metier}
  E -->|ACCEPTED| F[POST /api/conversions/{cid}/send-sftp]
  E -->|REVIEW| G[UI de revue]
  G --> H[POST /api/conversions/{cid}/approve]
  H --> F
  E -->|REJECTED ou FAILED| I[Notification n8n]
```

## Endpoint a utiliser en priorite

Pour ton workflow n8n, il faut utiliser `POST /api/proxy/convert` et non `POST /api/convert`.

Pourquoi:

- `POST /api/proxy/convert` enregistre la conversion en base.
- il alimente l'historique, la revue et l'audit.
- il produit l'identifiant de conversion reutilisable ensuite.

L'identifiant a reutiliser dans n8n est `pdf_hash`. Dans l'application, il est stocke comme `id` dans la table `conversions`.

## Architecture recommandee sur VM Azure

Le plus simple est d'installer n8n et l'API sur la meme VM Azure, ou au minimum sur le meme reseau prive.

- API FastAPI sur `http://127.0.0.1:8000`
- n8n appelle l'API via adresse interne
- UI exposee separement si besoin

Base URL recommandee dans n8n:

```text
http://127.0.0.1:8000
```

Si tu clones le repo directement dans la VM pour travailler, le parcours recommande est:

```powershell
git clone <repo>
cd EDIFACT
pip install -r requirements.txt
copy .env.vm.example .env.vm
./run_vm.ps1
```

Le script `run_vm.ps1` charge `.env.vm`, construit le frontend si besoin, puis demarre l'API sur la VM avec des valeurs adaptees au flux n8n.

Un template importable n8n est aussi disponible dans le repo:

```text
n8n_vm_email_to_edifact.json
```

Usage recommande:

1. importer `n8n_vm_email_to_edifact.json` dans n8n;
2. remplacer le premier node `DEV: Manual trigger` par ton trigger Outlook reel;
3. verifier que la piece jointe PDF arrive bien en binaire;
4. definir `EDIFACT_API_BASE`, `EDIFACT_API_KEY` et si besoin `EDIFACT_CALLBACK_URL` dans n8n.

## Authentification sur VM Azure

Sur une VM Azure, n8n n'aura pas les headers SSO Databricks.

L'etat actuel du code est le suivant:

- l'API supporte les sessions de profil pour l'interface utilisateur;
- l'API supporte les headers d'identite injectes par un proxy;
- l'API supporte maintenant une authentification technique via `X-API-Key` ou `Authorization: Bearer ...`.

Variables a definir dans `.env.vm`:

```env
APP_REQUIRE_AUTH=true
APP_API_KEYS=change-me-in-vm
APP_API_ACTOR=n8n
APP_API_ROLE=adv
```

Comportement:

1. n8n envoie la cle dans le header `X-API-Key`;
2. l'API identifie l'appelant comme `n8n`;
3. le role technique par defaut est `adv`, suffisant pour `convert`, `review`, `approve` et `send-sftp`.

Si tu veux encore plus simple en environnement strictement prive, tu peux toujours mettre `APP_REQUIRE_AUTH=false`, mais ce n'est plus le mode recommande.

## Endpoints utiles pour n8n

### 1. Creer une conversion depuis un PDF

```http
POST /api/proxy/convert
Content-Type: multipart/form-data
```

Champ attendu:

- `file`: PDF de commande
- `callback_url`: optionnel, URL webhook n8n a notifier lors des changements d'etat

Exemple d'URL:

```text
http://127.0.0.1:8000/api/proxy/convert
```

Exemple de reponse:

```json
{
  "status": "OK",
  "filename": "commande.pdf",
  "pdf_hash": "4f3a7b1b0c2d",
  "cached": false,
  "processing_time_s": 3.1,
  "order": {
    "po_number": "PO-2026-001",
    "order_date": "20260709",
    "delivery_date": "20260712"
  },
  "customer": {
    "soldto": "1234567890",
    "shipto": "0987654321",
    "name": "Client X",
    "confidence": 92
  },
  "lines": {
    "count": 4,
    "items": []
  },
  "rejection": {
    "decision": "ACCEPTED",
    "reason": null,
    "blocking_count": 0,
    "warning_count": 0,
    "details": []
  },
  "edifact": {
    "generated": true,
    "message": "UNB+UNOC:3+...",
    "warnings": [],
    "errors": null
  },
  "error": null
}
```

Champs a exploiter dans n8n:

- `pdf_hash` comme `cid`
- `rejection.decision` pour piloter le workflow
- `edifact.generated` pour verifier que le message a ete genere

Valeurs utiles de `rejection.decision`:

- `ACCEPTED`
- `REVIEW`
- `REJECTED`

Mapping du statut persiste:

- `ACCEPTED` -> `ACCEPTED`
- `REVIEW` -> `REVIEW_REQUIRED`
- `REJECTED` -> `REJECTED`
- erreur technique -> `FAILED`

### 2. Lister les conversions

```http
GET /api/conversions?status=REVIEW_REQUIRED&limit=100
```

Parametres:

- `status`: filtre optionnel
- `q`: recherche texte
- `limit`: nombre maximum

Exemple de reponse:

```json
{
  "conversions": [
    {
      "id": "4f3a7b1b0c2d",
      "source_filename": "commande.pdf",
      "pdf_hash": "4f3a7b1b0c2d",
      "status": "REVIEW_REQUIRED",
      "delivery_status": "NOT_APPLICABLE",
      "po_number": "PO-2026-001",
      "soldto": "1234567890",
      "shipto": "0987654321",
      "tst_filename": null,
      "sftp_status": "NOT_APPLICABLE",
      "created_at": "2026-07-09 09:15:00",
      "updated_at": "2026-07-09 09:15:05"
    }
  ]
}
```

### 3. Lire le detail d'une conversion

```http
GET /api/conversions/{cid}
```

Cet endpoint sert a recuperer:

- le detail complet de la conversion;
- l'extraction JSON;
- les corrections;
- l'audit.

### 4. Sauvegarder des corrections de revue

```http
POST /api/conversions/{cid}/review
Content-Type: application/json
```

Exemple de body:

```json
{
  "po_number": "PO-2026-001",
  "corrections": {
    "soldto": "1234567890",
    "shipto": "0987654321"
  }
}
```

Cet endpoint ne valide pas la commande. Il enregistre les corrections et conserve le statut de revue.

### 5. Approuver apres revue

```http
POST /api/conversions/{cid}/approve
Content-Type: application/json
```

Exemple de body:

```json
{
  "corrections": {
    "soldto": "1234567890",
    "shipto": "0987654321"
  }
}
```

Reponse type:

```json
{
  "ok": true,
  "status": "ACCEPTED"
}
```

### 6. Rejeter manuellement

```http
POST /api/conversions/{cid}/reject
Content-Type: application/json
```

Exemple de body:

```json
{
  "rejection_code": "MANUAL_REJECTION",
  "rejection_message": "Commande incomplete"
}
```

### 7. Envoyer le fichier par SFTP

```http
POST /api/conversions/{cid}/send-sftp
```

Cet endpoint prend le `.tst` de la conversion et le depose sur le SFTP configure pour SAP/Esker.

### 8. Verifier la configuration SFTP

```http
GET /api/sftp/status
```

### 9. Healthcheck

```http
GET /healthz
```

## Workflow n8n recommande

### Etape 1. Detection Outlook

Dans n8n:

- utiliser un node Outlook ou Microsoft Graph;
- filtrer la boite de reception cible;
- verifier qu'un PDF est present;
- ignorer les pieces jointes non PDF.

### Etape 2. Envoi du PDF vers l'API

Configurer un node `HTTP Request` avec:

- Method: `POST`
- URL: `{{$env.EDIFACT_API_BASE}}/api/proxy/convert`
- Header: `X-API-Key: {{$env.EDIFACT_API_KEY}}`
- Send Binary Data: `true`
- Content type: `multipart/form-data`
- Champ `callback_url`: `{{$env.EDIFACT_CALLBACK_URL}}` si tu veux une remontee d'etat push

Variable conseillee dans n8n:

```text
EDIFACT_API_BASE=http://127.0.0.1:8000
EDIFACT_API_KEY=change-me-in-vm
EDIFACT_CALLBACK_URL=https://<ton-n8n>/webhook/f2edi-status
```

### Etape 3. Brancher selon la decision

Tester `{{$json.rejection.decision}}`.

Cas `ACCEPTED`:

1. recuperer `pdf_hash`
2. appeler `POST /api/conversions/{pdf_hash}/send-sftp`

Cas `REVIEW`:

1. notifier un operateur
2. faire la revue dans l'interface
3. appeler `POST /api/conversions/{pdf_hash}/approve`
4. appeler `POST /api/conversions/{pdf_hash}/send-sftp`

Cas `REJECTED`:

1. journaliser le rejet
2. envoyer une notification
3. arreter le flux SAP

## Remontee d'etat vers n8n

Le besoin est bien compris, mais il faut distinguer le mode deja disponible du mode cible.

Mode disponible maintenant:

- l'application retourne le premier statut dans la reponse de `POST /api/proxy/convert`;
- n8n peut relire l'etat via `GET /api/conversions/{cid}` ou `GET /api/conversions?...`.

Mode push maintenant disponible:

- si `callback_url` est fourni au moment du `POST /api/proxy/convert`, l'application appelle ce webhook n8n sur les evenements `conversion_created`, `user_corrected`, `user_approved`, `user_rejected`, `sftp_sent` et `sftp_failed`.

Mode cible non encore implemente:

- un mecanisme plus riche de subscription/webhook signe et gere centralement.

Donc, aujourd'hui, tu as les deux modes: lecture API depuis n8n, ou callback sortant simple via `callback_url`.

## Variables a verifier sur la VM Azure

- `APP_REQUIRE_AUTH`
- `ENABLE_PROFILE_LOGIN`
- `DB_PATH`
- `PDF_STORAGE_DIR`
- `OUTBOX_DIR`
- `LOG_DIR`
- `SFTP_HOST`
- `SFTP_PORT`
- `SFTP_USERNAME`
- `SFTP_PASSWORD`
- `SFTP_REMOTE_DIR`

Point de depart recommande sur VM privee:

```env
APP_REQUIRE_AUTH=true
ENABLE_PROFILE_LOGIN=true
APP_API_KEYS=change-me-in-vm
APP_API_ACTOR=n8n
APP_API_ROLE=adv
```

## Si tu veux un vrai callback vers n8n

Il faudra ajouter dans l'API:

1. un `callback_url` passe par n8n au moment du `POST /api/proxy/convert`
2. un appel HTTP sortant de l'application vers ce webhook lors d'un changement de statut

Ce mecanisme n'est pas encore present dans le code actuel.

## Conclusion pratique

Oui, je comprends exactement la cible.

Le bon schema pour ce projet sur VM Azure est:

1. Outlook detecte la commande.
2. n8n extrait le PDF.
3. n8n appelle `POST /api/proxy/convert` sur la VM.
4. n8n lit `pdf_hash` et `rejection.decision`.
5. si `ACCEPTED`, n8n declenche l'envoi SFTP.
6. si `REVIEW`, un operateur valide puis l'envoi SFTP est lance.
7. si `REJECTED`, n8n notifie et stoppe le traitement.

## Prochaine etape recommandee

1. preparer un workflow n8n JSON complet Outlook -> PDF -> API -> revue -> SFTP
2. ou ajouter un vrai webhook de callback dans l'API pour eviter le polling
