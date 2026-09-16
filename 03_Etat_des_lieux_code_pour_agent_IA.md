# État des lieux du dépôt — complément au Contrat de développement (02)

**Objet : donner à l'agent auteur de `02_Contrat_developpement_agent_IA.md` une vue vérifiée du code réel**, afin qu'il puisse recaler ses RM/UX/AR sur l'existant prouvé au lieu du seul classeur `[S1]`. Chaque affirmation ci-dessous est appuyée par un chemin de fichier et, si possible, un nom de fonction — pas une supposition.

Méthode : lecture directe du dépôt (`src/`, `app/`, `frontend/`, `data/`, `tests/`), pas du classeur Excel ni des captures d'écran. Les incohérences entre le contrat et le code sont signalées explicitement.

---

## 1. Chemins cités par le contrat — confirmés existants

Les 8 chemins listés en §2 du contrat existent tous et correspondent bien aux responsabilités décrites :

| Chemin | Rôle réel observé |
|---|---|
| `app/extraction.py` | Pipeline d'extraction initiale (OCR/LLM), construit `adresses.Adresse de livraison detectee/validee` |
| `app/engines/rejection_engine.py` | Moteur de règles de rejet/anomalies au moment de l'extraction |
| `app/engines/shipto_scoring.py` *(non cité par le contrat, à ajouter)* | Cœur du matching Ship-to (`match_shipto_strict`, `score_shipto_candidates`) — **ne référence aucun champ TVA** |
| `app/masterdata.py` | Cache référentiel legacy (`get_master_data`), filtre les partenaires **Ship-to sur `PARVW == "SH"`** |
| `app/edifact_generator.py` | Génération du contenu EDIFACT à partir de la version de commande |
| `src/rejection_catalog.py` | Catalogue canonique des codes de rejet + alias |
| `src/pompac_rules.py` | Règles complémentaires (non auditées en détail ici) |
| `src/file2edi/store.py` | **Cœur métier** : `File2EdiStore`, toutes les mutations de commande/partenaires/lignes |
| `src/sftp_delivery.py` | Transport SFTP |
| `src/masterdata_runtime.py` *(non cité, à ajouter)* | Cache CSV/Parquet servant les endpoints `/api/masterdata/*/search` côté frontend — **ne filtre pas par `PARVW`**, contrairement à `app/masterdata.py` |
| `tests/test_rejection_catalog.py`, `tests/test_file2edi_review_workflow.py`, `tests/test_shipto_strict_match.py` | Tests réels exécutables (`pytest`) |

**Écart déjà corrigé cette semaine** : `app/masterdata.py` (validation) filtrait les Ship-to sur `PARVW == "SH"`, mais les endpoints de recherche du frontend (`src/masterdata_runtime.py`) ne le faisaient pas → une commande fantôme (bill-to/payer) pouvait apparaître dans la liste déroulante Ship-to du frontend, être sélectionnée, puis être rejetée silencieusement côté serveur. Corrigé dans `frontend/src/components/file2edi/ShiptoCodeSelectField.tsx` et `ShiptoNameSelectField.tsx` (filtre `PARVW === "SH"` ajouté). **Preuve concrète que les deux sources de référentiel (legacy `app/masterdata.py` vs `masterdata_runtime.py`) doivent être auditées comme une seule surface, pas deux.**

---

## 2. Modèle de données réel (SQLite, `data/file2edi_schema.sql`)

Le contrat (§3) propose un modèle cible ("Version de commande", "Valeur et provenance", "Confirmation ADV", "Artefact EDI", "Intention d'envoi"). **Aucun de ces objets n'existe** dans le schéma actuel. Voici ce qui existe réellement :

| Table réelle | Colonnes clés | Rapprochement avec le modèle cible du contrat |
|---|---|---|
| `file2edi_orders` | `order_id`, `client_name`, `customer_order_number`, `order_date`, `requested_delivery_date`, `status`, `review_required`, `manually_edited_fields` *(ajoutée le 16/09)*, `corrections_json`, `updated_at` | Partiel équivalent de "Version de commande" — **pas de numéro de version explicite**, seulement `updated_at` ; pas de champ "auteur de la dernière mutation" séparé |
| `file2edi_order_partners` | `partner_id`, `order_id`, `partner_function` (`soldto`/`shipto`/`billto`/`payer`), `partner_code`, `partner_name`, adresse, `manually_edited`, `edited_fields_json` | Équivalent partiel de "Paire partenaire" — `edited_fields_json` stocke `manual`/`auto` par champ (proche de "Valeur et provenance"), mais **pas d'horodatage par champ**, pas de version |
| `file2edi_order_lines` | `line_id`, `line_number`, `bosch_article`, `quantity`, `unit_price`, `status`, `manually_edited` | Équivalent de "Ligne" — **pas d'identifiant stable indépendant de `line_number`** (le contrat T-P10/RM insiste sur ce point) |
| `file2edi_order_anomalies` | `anomaly_id` (format `{order_id}:{field_name}`), `severity`, `field_name`, `status` (`Ouverte`/`Bloquante`/`Corrigée`) | Équivalent de "Diagnostic" — **un seul diagnostic actif par `field_name` et par commande** (clé primaire dérivée), donc pas d'historique des occurrences successives |
| `file2edi_business_events` | `actor`, `action`, `entity_type`, `entity_id`, `details_json` | Amorce de "Confirmation ADV" / traçabilité §11, mais **pas de structure "acteur / action versionnée / cible / empreinte / motif"** telle que proposée en §8 |
| *(inexistant)* | — | Pas de table "Artefact EDI" séparée : le contenu généré est stocké dans `file2edi_orders.edifact_content` / `edifact_filename`, sans empreinte de contenu ni lien de version explicite |
| *(inexistant)* | — | Pas de table "Intention d'envoi" avec clé de déduplication : l'anti-duplication actuelle repose sur `PO_NUMBER_DUPLICATE` (comparaison texte au référentiel SAP), pas sur une clé de transport dédiée |

**Conclusion pour l'agent auteur** : le modèle cible du contrat (§3) est un **redesign complet**, pas une évolution incrémentale du schéma actuel. Le classer explicitement comme tel (lot L2/L3, gros effort) plutôt que comme un ajustement.

---

## 3. RM-01 à RM-10 — statut réel avec preuves de code

| RM | Statut | Preuve |
|---|---|---|
| **RM-01** (revue/correction même sans anomalie) | ✅ Implémenté | `frontend/src/components/file2edi/OrderGeneralInfoPanel.tsx` : tous les champs (`EditableField`, `*SelectField`) sont éditables inconditionnellement, jamais gated par la présence d'une anomalie |
| **RM-02** (correction à côté du PDF) | ✅ Implémenté | `frontend/src/pages/RevuePage.tsx` : layout `grid-cols-[13fr_7fr]` avec `PdfPreviewPanel` à gauche et le panneau de correction à droite, sur la même page |
| **RM-03** (adresse prioritaire, TVA secondaire) | ✅ Cohérent au niveau du moteur | `app/engines/shipto_scoring.py::match_shipto_strict` ne prend **aucun paramètre TVA** ; la TVA n'intervient que côté frontend (`resolveSoldtoCodes` dans `ShiptoCodeSelectField.tsx`) pour élargir la liste de candidats, jamais pour trancher un match |
| **RM-04** (adresse > Ship-to > Sold-to à l'extraction) | ⚠️ Non vérifié en profondeur | Nécessite un audit dédié de `app/extraction.py` + `app/engines/shipto_scoring.py` pour tracer l'ordre exact des étapes d'identification initiale (hors périmètre de cette session, centrée sur les mutations manuelles post-extraction) |
| **RM-05** (Sold-to → Ship-to unique) | ✅ Implémenté et testé | `store.py::_propagate_soldto_change` → `_rematch_shipto_after_update`, bloc "Infer/strict match" ; test `test_shipto_infers_unique_distinct_parent_soldto_when_soldto_empty` |
| **RM-06** (Sold-to sans Ship-to unique → vidage) | ✅ Implémenté, **périmètre exact figé de facto cette semaine** (voir §4 ci-dessous) | `store.py::_propagate_soldto_change`, branche `if not soldto_code:` ; tests `test_clearing_soldto_code_clears_address_and_raises_anomaly`, `test_soldto_change_voids_mismatched_shipto_but_keeps_order_number_and_dates` |
| **RM-07** (Ship-to renseigné → adresse auto) | ✅ Implémenté et testé | `store.py::_rematch_shipto_after_update`, `fill_map` ; test `test_shipto_address_change_rematches_existing_code_to_unique_masterdata_partner` |
| **RM-08** (Ship-to → Sold-to unique sinon vide) | ✅ Implémenté et testé | `store.py::_rematch_shipto_after_update`, bloc `parent_soldtos_for_shipto` / `diff_parents` ; tests `test_shipto_infers_unique_distinct_parent_soldto_when_soldto_empty` et `test_shipto_does_not_infer_soldto_when_multiple_parents_or_same_code` |
| **RM-09** (confirmations à la première personne) | ❌ Non implémenté | Aucune trace de libellés "J'ai corrigé…" dans le frontend actuel ; les actions existantes sont des boutons d'action classiques (Enregistrer, Vider, Rechercher), pas des attestations |
| **RM-10** (regrouper les diagnostics en situations) | ❌ Non implémenté | Les anomalies (`file2edi_order_anomalies`) sont affichées une par une (probablement via un composant de type liste dans `RevuePage.tsx`), pas de couche de regroupement en "situations UX" |

---

## 4. AR-01 / AR-02 — décisions prises de facto cette semaine, **à valider formellement**

Le contrat interdit explicitement d'inventer le périmètre exact de l'effacement (AR-01) et la résolution des relations plusieurs-à-plusieurs (AR-02) sans arbitrage métier tracé. Dans les faits, au fil de cette session de développement, le comportement suivant a été implémenté et poussé en dépôt (commits `8082146`, `116c6ce` sur la branche `dev`) **sur simple confirmation orale dans un chat, pas via un arbitrage AR-01/AR-02 documenté** :

| Déclencheur | Champs vidés | Champs explicitement préservés |
|---|---|---|
| Sold-to vidé manuellement | `partner_name`, `address_line_1`, `postal_code`, `city` du **Sold-to** ; `client_name` de la commande ; **et désormais aussi tous les champs du Ship-to** (`partner_code`, `partner_name`, adresse) | `customer_order_number`, `order_date`, `requested_delivery_date`, `document_reference` |
| Nouveau Sold-to choisi, dont la famille ne contient pas le Ship-to courant | Ship-to (`partner_code`, `partner_name`, adresse) ; `client_name` | `customer_order_number`, dates |
| Ship-to sélectionné explicitement (dans la liste) mais qui ne correspond à aucun Ship-to du Sold-to courant | Ship-to (`partner_code`, `partner_name`, adresse) ; `client_name` | `customer_order_number`, dates |

**Ce qui n'est PAS géré (AR-02 reste ouvert)** : le cas "A a plusieurs Ship-to ET le Ship-to a plusieurs Sold-to" (cascade + blocage plusieurs-à-plusieurs décrit en §5 du contrat, tests T-P07/T-P08). Le code actuel ne finalise pas de paire dans ce cas — il laisse Sold-to ou Ship-to vide selon lequel a été modifié en dernier, sans mécanisme de "sélection conjointe" ni de "confirmation maintenue si compatible".

**Recommandation pour l'agent auteur** : documenter ce tableau comme **la proposition de réponse à AR-01**, à faire approuver formellement par le pilote métier désigné (§Annexe B), plutôt que de le considérer comme une fonctionnalité déjà validée. Le prochain agent ne doit pas supposer que ce périmètre est figé de manière définitive.

---

## 5. Catalogue de rejet — vérification chiffrée (confirme le contrat)

- `REJECTION_CATALOG` dans `src/rejection_catalog.py` contient **exactement 38 clés canoniques** — le chiffre du contrat est exact.
- `CODE_ALIASES` contient **exactement 17 alias** pointant vers **10 codes canoniques distincts** — exact également.
- `SOLDTO_CONFIDENCE_MIN` et `SHIPTO_CONFIDENCE_MIN` : confirmé absents de tout usage applicatif (`docs/VALIDATION_RULES_CLASSIFICATION.md` le documente déjà explicitement). Aucune implémentation à faire disparaître, juste une mention à retirer du catalogue si jamais réintégrée.

Cette partie du contrat (§7, Annexe A) est fiable et n'a pas besoin d'être recorrigée.

---

## 6. Registre d'actions UX-01 à UX-23 et tests T-P/T-U/T-I — état réel : **0 % implémenté**

Recherche exhaustive de chaque identifiant (`UX-01.*` à `UX-23.*`, `T-P01` à `T-P18`, `T-U01` à `T-U18`, `T-I01` à `T-I18`) dans tout le dépôt (code + config + docs existants) : **aucune occurrence en dehors du fichier `02_Contrat_developpement_agent_IA.md` lui-même.**

Conséquences pour l'agent auteur :
- Le §16-21 (registre d'actions), le schéma JSON du §8, et les 54 scénarios §13-15 sont un **design cible complet**, pas une évolution de fonctionnalités existantes. À traiter comme lot L3 (gros effort produit + technique), pas comme des tests à "faire passer au vert" sur du code déjà là.
- Le mécanisme actuel le plus proche des "confirmations" est le champ `edited_fields_json` (`manual`/`auto` par champ) — c'est une **provenance de valeur**, pas une attestation humaine structurée avec acteur/motif/preuve comme demandé en §8.

---

## 7. Tests réels existants (à ne pas dupliquer, à faire évoluer)

| Fichier | Couverture réelle | Recoupement avec les tests proposés §13 |
|---|---|---|
| `tests/test_file2edi_review_workflow.py` (17 tests) | Vidage Sold-to/Ship-to, propagation billing, inférence Sold-to↔Ship-to unique, doublon PO, `manuallyEditedFields` | Couvre partiellement T-P01, T-P02, T-P04, T-P05, T-P06 |
| `tests/test_shipto_strict_match.py` (8 tests) | Matching strict par adresse, ambiguïté sans code postal, rematch sur édition manuelle | Couvre partiellement T-P10 (ambiguïté), pas T-P07/T-P08 (cascade multi-niveaux) |
| `tests/test_rejection_catalog.py` | Cohérence du catalogue (existence, alias) | Sans équivalent direct dans §13-15, complémentaire |

**Aucun test n'existe pour** : T-P07 (cascade), T-P08 (plusieurs-à-plusieurs), l'intégralité de T-U01-18 (confirmations UX), T-I01-18 (EDI/transport). Normal puisque le code correspondant n'existe pas non plus.

---

## 8. Recommandations concrètes pour améliorer le document 02

1. **Ajouter à la liste des chemins audités** : `app/engines/shipto_scoring.py`, `app/masterdata.py`, `src/masterdata_runtime.py` (référentiel), `frontend/src/components/file2edi/*SelectField.tsx` (UI de sélection partenaires) — le contrat actuel ne cite que le backend, alors que RM-05 à RM-08 ont une moitié d'implémentation côté frontend (listes de recherche, filtrage `PARVW`).
2. **Distinguer clairement, pour chaque RM/UX**, trois statuts au lieu de "P" générique : `IMPLÉMENTÉ-TESTÉ`, `IMPLÉMENTÉ-NON-TRACÉ-COMME-ARBITRAGE` (cas RM-06 ci-dessus), `NON-IMPLÉMENTÉ`. Le tableau §3 ci-dessus peut être copié tel quel dans le contrat.
3. **AR-01 et AR-02** : proposer le tableau de la section 4 comme brouillon de décision à faire approuver, plutôt que de repartir d'une page blanche.
4. **Corriger le §3 du contrat** (modèle de données cible) : préciser explicitement qu'aucune des tables proposées n'existe aujourd'hui — actuellement le document laisse penser qu'il s'agit d'un raffinement, alors que c'est une refonte.
5. **RM-09/RM-10** : confirmer qu'il s'agit bien d'un chantier neuf (aucune UI de confirmation à la première personne n'existe) avant de dimensionner le lot L3.
6. **Vérifier RM-04** spécifiquement dans `app/extraction.py`/`app/engines/shipto_scoring.py` avant de le marquer "C" (observé) — non fait dans cette session car hors périmètre des mutations manuelles post-extraction.

---

*Document produit par lecture directe du dépôt le 16/09/2026, en complément du contrat existant. Ne remplace aucun arbitrage métier ; signale uniquement les écarts entre le contrat et le code observé.*
