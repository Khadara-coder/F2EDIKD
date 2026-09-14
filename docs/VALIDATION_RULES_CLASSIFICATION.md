# Classification des Règles de Validation

**Objectif :** disposer d'une grille stable pour comprendre, prioriser et faire évoluer les validations File2EDI.

## 1. Les axes de classification

Une règle doit être décrite selon plusieurs axes complémentaires. Une seule catégorie ne suffit pas.

| Axe | Valeurs | Question posée |
|---|---|---|
| **Nature** | structurelle, syntaxique, sémantique, référentielle, métier, technique, intégration | Que contrôle la règle ? |
| **Étape** | ingestion, classification, extraction, matching, validation métier, EDI, livraison | Quand s'applique-t-elle ? |
| **Portée** | document/commande, ligne article, livraison, système | Quel objet est impacté ? |
| **Impact** | bloquant, revue, information | Le traitement peut-il continuer ? |
| **Action** | corriger le document, corriger les données maîtres, demander une décision utilisateur, relancer, escalader | Comment récupérer ? |

La taxonomie technique existante dans `src/rejection_catalog.py` porte déjà les axes **domaine**, **étape**, **sévérité**, **blocking**, **scope** et **requires_user_input**. La présente classification lui ajoute la **nature du contrôle** et l'**action de récupération**.

## 2. Classification fonctionnelle

### A. Contrôles d'ingestion et de structure documentaire

Ils vérifient que le fichier peut être traité et qu'il correspond au type de document attendu.

| Codes principaux | Nature | Portée | Impact habituel |
|---|---|---|---|
| `NOT_A_PDF` | structurelle | document | bloquant |
| `PDF_PARSE_FAILURE` | technique/structurelle | document | bloquant, relance possible |
| `NOT_AN_ORDER` | classification sémantique | document | bloquant |
| `CONTRACT_KEYWORD` | classification sémantique | document | bloquant |
| `ORDER_CHANGE` | classification métier | document | bloquant |
| `CONTRACT_BREAK_ADDRESSES_MISSING` | structurelle | document | bloquant |
| `CONTRACT_BREAK_ARTICLES_MISSING` | structurelle | document | bloquant |

**Question métier :** le fichier est-il exploitable et représente-t-il une commande initiale ?

### B. Contrôles de complétude et de syntaxe des données extraites

Ils portent sur les valeurs extraites du PDF, avant leur comparaison avec les référentiels.

| Codes principaux | Nature | Portée | Impact habituel |
|---|---|---|---|
| `ORDER_KEY_MISSING` | complétude | commande | bloquant/revue |
| `ORDER_DATE_INVALID` | syntaxique | commande | bloquant/revue |
| `DELIVERY_DATE_INVALID` | syntaxique | ligne | bloquant/revue |
| `NO_LINE_ITEMS` | complétude | commande | bloquant |
| `QUANTITY_MISSING` | complétude | ligne | bloquant |
| `ARTICLE_QUANTITY_INVALID` | syntaxique/métier | ligne | bloquant |
| `PRICE_MISSING` | complétude | ligne | bloquant/revue |
| `UNIT_PRICE_MISSING` | complétude | ligne | bloquant |
| `EXTRACTION_LLM_SALVAGE` | technique | commande | revue |

**Question métier :** les champs nécessaires sont-ils présents et dans un format utilisable ?

### C. Contrôles de rapprochement avec les données maîtres

Ils ne jugent pas seulement le format : ils vérifient qu'une valeur extraite correspond à une entité connue.

| Codes principaux | Nature | Portée | Impact habituel |
|---|---|---|---|
| `PARTNER_UNRESOLVED` | synthèse de fallback | commande | revue non bloquante |
| `SOLDTO_NOT_FOUND` | référentielle | commande | bloquant |
| `SOLDTO_AMBIGUOUS_MATCH` | matching | commande | bloquant/revue |
| `SHIPTO_CANDIDATES_MISSING` | référentielle | livraison | bloquant/revue |
| `SHIPTO_NO_STRONG_MATCH` | matching | livraison | bloquant/revue |
| `SHIPTO_AMBIGUOUS_MATCH` | matching | livraison | bloquant/revue |
| `SHIPTO_SOLDTO_MISMATCH` | relation référentielle | livraison | bloquant/revue |
| `NO_DELIVERY_ADDRESS` | complétude/référentielle | livraison | bloquant |
| `ARTICLE_NOT_FOUND` | référentielle | ligne | bloquant/revue |
| `NO_VALID_ARTICLE` | référentielle | commande | bloquant/revue |
| `MATERIAL_STATUS_INVALID` | référentielle/métier | ligne | bloquant/revue |

**Question métier :** l'acteur, l'adresse et l'article existent-ils dans le bon référentiel ?

### D. Contrôles de règles métier commerciales

Ils vérifient qu'une commande identifiable est autorisée et cohérente avec le processus métier.

| Codes principaux | Nature | Portée | Impact habituel |
|---|---|---|---|
| `CONTRACT_KEYWORD` | métier/classification | commande | bloquant |
| `ORDER_CHANGE` | métier/classification | commande | bloquant |
| `PO_NUMBER_DUPLICATE` | métier/dédoublonnage | commande | revue ou blocage selon décision |
| `DUPLICATE_ALREADY_SENT` | métier/dédoublonnage | commande | bloquant |
| `RESUBMISSION_DETECTED` | contrôle d'idempotence | commande | information/revue |
| `ARTICLE_QUANTITY_INVALID` | règle commerciale | ligne | bloquant |
| `MATERIAL_STATUS_INVALID` | règle commerciale | ligne | bloquant |

**Question métier :** la commande est-elle admissible, non contradictoire et non déjà traitée ?

### E. Contrôles de cohérence EDIFACT

Ils vérifient que les données validées peuvent être représentées dans le message cible.

| Codes principaux | Nature | Portée | Impact habituel |
|---|---|---|---|
| `EDIFACT_MISSING_BGM` | structurelle EDI | commande | bloquant |
| `EDIFACT_MISSING_DTM_137` | structurelle EDI | commande | bloquant |
| `EDIFACT_MISSING_NAD_BY` | structurelle EDI | commande | bloquant |
| `EDIFACT_MISSING_NAD_DP` | structurelle EDI | commande | bloquant |
| `EDIFACT_MISSING_LIN` | structurelle EDI | commande | bloquant |
| `EDIFACT_LINE_INTEGRITY_MISMATCH` | cohérence EDI | commande | bloquant |
| `EDIFACT_NAD_DP_MISMATCH` | cohérence EDI | livraison | bloquant |

**Question métier :** le message D.96A est-il complet et cohérent avec la commande validée ?

### F. Contrôles techniques et de livraison

Ils signalent que le système ou le canal de sortie ne permet pas de terminer le traitement.

| Codes principaux | Nature | Portée | Impact habituel |
|---|---|---|---|
| `MASTERDATA_MISSING` | technique | système | bloquant, synchronisation |
| `MASTERDATA_SCHEMA_INVALID` | technique | système | bloquant, correction technique |
| `DELIVERY_SFTP_FAILED` | intégration | commande | bloquant, retry |
| `DELIVERY_EMAIL_FAILED` | intégration | commande | bloquant, retry/escalade |

**Question métier :** l'application dispose-t-elle de ses dépendances et a-t-elle livré le résultat ?

## 3. Hiérarchie opérationnelle recommandée

Pour exploiter cette classification dans l'interface et les rapports :

1. **Bloquant technique** : arrêter et escalader (`NOT_A_PDF`, `MASTERDATA_SCHEMA_INVALID`, erreur SFTP persistante).
2. **Bloquant métier** : ne pas envoyer à SAP (`SOLDTO_NOT_FOUND`, `ARTICLE_NOT_FOUND`, `DUPLICATE_ALREADY_SENT`).
3. **Revue utilisateur** : suspendre sans rejeter définitivement (`EXTRACTION_LLM_SALVAGE`, ambiguïté de matching).
4. **Information** : journaliser et poursuivre (`RESUBMISSION_DETECTED`).

Le champ `severity` du moteur (`blocking` ou `warning`) sert à prendre la décision immédiate. Le champ `issue_severity` du catalogue (`INFO`, `WARNING`, `ERROR`, `CRITICAL`) sert à qualifier la gravité. Ces champs ne doivent pas être confondus.

## 4. Points de cohérence contrôlés

- `ARTICLE_NOT_FOUND` est maintenant renvoyé par le moteur avec `severity: "blocking"`, conformément à `blocking: True` dans la taxonomie.
- `NO_LINE_ITEMS` est maintenant bloquant dans `rejection_engine.py`, car l'absence de ligne empêche la génération EDIFACT (`EDIFACT_MISSING_LIN`).
- `PO_NUMBER_DUPLICATE` reste une alerte de revue (`severity: "warning"`) et est maintenant non bloquant dans la taxonomie ; l'utilisateur peut confirmer qu'il s'agit d'une nouvelle commande.
- Les seuils de confiance Sold-to/Ship-to sont des critères de matching documentés, pas des codes de rejet canoniques : aucun usage applicatif n'a été trouvé pour `SOLDTO_CONFIDENCE_MIN` ou `SHIPTO_CONFIDENCE_MIN`.
- `QUANTITY_INVALID` et `INVALID_QUANTITY` sont des alias ; le code canonique du catalogue est `ARTICLE_QUANTITY_INVALID`.
- `DELIVERY_EMAIL_FAILED` existe dans la taxonomie, mais doit être couvert par un scénario de test et un flux de reprise explicite.

## 5. Format cible pour chaque nouvelle règle

Toute nouvelle règle devrait être documentée avec cette fiche :

```text
Code canonique:
Nature:
Domaine:
Étape:
Portée: ORDER | LINE | DELIVERY | SYSTEM
Condition de déclenchement:
Bloquante: oui/non
Saisie utilisateur requise: oui/non
Retry autorisé: oui/non
Action de récupération:
Test associé:
```

Cette fiche évite de mélanger une erreur d'extraction, une incohérence métier et une panne d'intégration sous un même simple statut « rejet ».
