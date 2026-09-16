# Saisie des commandes SAP
## Contrat de réalisation pour l'agent IA

**File2EDI | Développement full stack et recette | Version 1.0 | 15 septembre 2026**

### Mission

Faire évoluer la revue des commandes pour que l'ADV corrige directement les données préremplies à côté du PDF, comprenne les conséquences des automatismes et confirme le travail effectivement réalisé. Conserver les diagnostics du moteur, mais les présenter sous forme de situations métier et de confirmations contextuelles.

L'identification initiale privilégie l'adresse de livraison, puis le Ship-to et le Sold-to. Les modifications manuelles des partenaires ont des effets bidirectionnels de remplissage ou d'effacement. La TVA est un critère secondaire de recherche, pas une preuve autonome du bon lieu de livraison. [U1-U4]

### Instruction de travail

**Commencer par auditer le dépôt disponible, décrire l'existant prouvé et relier les écarts aux identifiants de ce document. Ne pas remplacer les règles par un parcours générique Sold-to d'abord. Ne pas résoudre une ambiguïté métier en inventant un comportement silencieux.**

Les propositions sont conçues pour être traduites dans la stack existante. Les noms d'objets, d'actions et d'interfaces ci-dessous sont des contrats sémantiques proposés ; ils ne prétendent pas décrire des API déjà présentes.

### Résultats attendus

Un audit de correspondance, un registre des arbitrages, des modifications incrémentales avec compatibilité explicite, des tests traçables, une migration contrôlée et un compte rendu des preuves d'exécution. Aucune transmission réelle vers SAP ni modification d'un référentiel de production sans autorisation appropriée.

### Statut des exigences

**E :** demande explicite du porteur du projet. **C :** observation dans une source. **P :** cible ou garde-fou proposé, à faire approuver. **A :** arbitrage ouvert AR-xx. Les RM-xx sont établies ; les noms techniques, fiches UX et états cible sont proposés sauf indication contraire.

**Le document ne remplace pas une décision métier manquante.** Poursuivre les travaux indépendants d'un arbitrage, mais ne pas activer une mutation destructive ou une autorisation d'envoi sur la base d'une hypothèse.

<!-- PAGE -->
## 1. Base de vérité et exigences RM

### Ordre de prise en compte

Pour un point explicitement clarifié, appliquer les dernières demandes [U1-U4]. Le classeur [S1] décrit le catalogue existant ; il peut contenir des formulations antérieures. Les captures [S2] décrivent le rendu visible, pas les garanties serveur. Une proposition de l'assistant n'est pas une décision métier approuvée.

| Identifiant | Exigence établie |
|---|---|
| RM-01 | L'ADV vérifie et corrige les données avant envoi, même sans anomalie automatique. [U1] |
| RM-02 | Correction directe dans l'espace de travail avec le PDF. [U3] |
| RM-03 | Adresse de livraison prioritaire ; TVA secondaire. [U3] |
| RM-04 | Identification initiale adresse > Ship-to > Sold-to ; TVA utilisable pour réduire la recherche. [U3] |
| RM-05 | Changement du Sold-to et Ship-to unique : renseigner Ship-to, adresse et informations associées. [U4] |
| RM-06 | Changement du Sold-to sans Ship-to unique : "tout se vide dans l'en-tête" ; portée précise non définie, AR-01. [U4] |
| RM-07 | Ship-to renseigné : adresse et informations associées renseignées automatiquement. [U4] |
| RM-08 | Ship-to avec Sold-to unique : renseigner ce Sold-to ; sinon Sold-to vide. [U4] |
| RM-09 | Confirmations à la première personne, comme "J'ai corrigé la quantité" ; pas de couple accepter / refuser imposé. [U2] |
| RM-10 | Regrouper les diagnostics en situations compréhensibles ; plusieurs issues contextuelles, sans nombre fixe. [U2] |

### Limites à conserver dans l'implémentation

La phrase "tout se vide" ne fournit pas une liste de colonnes. Ne pas l'interpréter comme effacement autorisé du numéro de commande, des dates, de la TVA, du document source ou même du Sold-to nouvellement choisi sans AR-01. Préserver les valeurs antérieures et le PDF comme preuves n'empêche pas l'effacement des champs de travail approuvés.

L'unicité, les filtres, les droits de correction d'adresse et la finalisation des relations plusieurs-à-plusieurs ne sont pas entièrement spécifiés. Ne pas inventer de règle "prendre le premier", de score minimal ou de conservation automatique du partenaire opposé. **AR-02 à AR-05**

Les règles commerciales de quantité, prix, date, substitution et vente doivent provenir du code audité ou d'une décision métier. Ne pas importer les statuts du document FAB-DIS ou des notes BI dans ce moteur sans validation spécifique.

<!-- PAGE -->
## 2. Audit du dépôt avant modification

### Inventaire à produire

Retrouver le modèle de commande, les lignes, l'extraction, le matching, les rattachements partenaires, l'édition de l'en-tête, les gestionnaires de changement, les catalogues de messages, la validation, la génération EDI, le transport, les statuts, les droits et l'audit. Identifier aussi les traitements asynchrones et l'enregistrement des corrections.

Les chemins ci-dessous sont **cités par le classeur**, non vérifiés dans le dépôt : `app/extraction.py`, `app/engines/rejection_engine.py`, `app/edifact_generator.py`, `src/rejection_catalog.py`, `src/pompac_rules.py`, `src/file2edi/store.py`, `src/sftp_delivery.py` et `tests/test_rejection_catalog.py`. Commencer par vérifier leur présence, leur responsabilité réelle et leurs appels. [S1, Règles colonnes R-T]

### Constats documentaires à réconcilier

| Sujet | Constat source et conséquence pour l'audit |
|---|---|
| Couverture | 38 codes dans Affichages ; 38 canoniques et 2 critères non canoniques dans Règles. Ne pas créer deux erreurs supplémentaires pour les seuils. |
| Utilisation réelle | 11 codes canoniques sont renseignés "Oui" dans Utilisée actuellement ; 27 sont "À vérifier". Ces mentions ne prouvent pas le comportement exécuté. |
| Tests | Un même fichier de tests est cité pour les 38 codes ; aucune preuve d'exécution n'est fournie par le classeur. |
| Partenaires | Les consignes Affichages L11 et L13 sont centrées sur le Sold-to courant ; les faire évoluer en cohérence avec RM-03 à RM-08, sans supprimer le contrôle de relation. |
| Doublon envoyé | Affichages L17 propose de continuer / renvoyer alors que le code signifie déjà envoyé. Ne pas conserver ce raccourci comme autorisation automatique. |
| Revue et statut | EXTRACTION_LLM_SALVAGE, PARTNER_UNRESOLVED et PO_NUMBER_DUPLICATE sont non bloquants dans Affichages mais demandent une revue. RESUBMISSION_DETECTED est informatif et sans revue requise. |
| Portée et cause | ARTICLE_NOT_FOUND est ORDER dans Règles, alors que l'action est par ligne ; NO_VALID_ARTICLE a un nom agrégé mais une description "un ou plusieurs". Vérifier avant de changer leur sémantique. |

### Livrable d'audit

Pour chaque RM, UX et code existant, fournir module, fonction, entrée / sortie, statut observé, test actuel, écart, modification prévue et preuve. Marquer clairement **trouvé dans le code**, **exécuté en test**, **non trouvé** ou **à arbitrer**. Ne pas transformer un succès de test de catalogue en preuve de fonctionnement de bout en bout.

<!-- PAGE -->
## 3. Modèle de données cible proposé

Adapter ces concepts aux objets et contrats existants ; ne pas imposer une nouvelle stack. Les identifiants techniques proposés peuvent changer, mais leur sémantique et leur traçabilité doivent rester explicites.

| Objet | Données minimales et invariants proposés |
|---|---|
| Version de commande | Identifiant stable, version métier, version du document, version des référentiels pertinents, données de travail, auteur de la dernière mutation. |
| Valeur et provenance | Valeur extraite, transcription corrigée, valeur sélectionnée dans le référentiel, origine et horodatage ; ne pas confondre les trois. |
| Paire partenaire | Sold-to, Ship-to, adresse partenaire, adresse documentaire, TVA / provenance, filtres actifs, rattachements et statut de résolution. |
| Ligne | Identifiant stable indépendant de l'ordre d'affichage, valeurs, provenance, inclusion / exclusion motivée, confirmations et diagnostics. |
| Diagnostic | Code canonique, alias d'origine, portée, contexte, version, résultat du contrôle, cause ou dépendance connue. |
| Situation UI | Identifiant UX, portée, diagnostics liés, variantes de message, actions disponibles, raison des actions indisponibles et effet sur les opérations. |
| Confirmation ADV | Acteur issu de l'authentification, action / libellé versionnés, cible, empreinte des données, constat ou modification, motif, instant et résultat serveur. |
| Artefact EDI | Identifiant, version de commande source, empreinte du contenu, configuration de génération, état de validation et lien vers le fichier. |
| Intention / tentative d'envoi | Identité métier et destination, artefact, clé de déduplication, statut, tentatives, preuve de transport et retour SAP lorsqu'il existe. |

### Null, inconnu et invalide sont distincts

Une liste de candidats peut être chargée et vide, chargée et multiple, en cours de chargement, indisponible ou invalide. Ne pas utiliser la même liste vide pour ces cinq états. Une valeur non renseignée n'est pas une valeur confirmée comme absente du document.

Une confirmation d'incertitude de matching peut rester valable tant que ses données et rattachements restent pertinents. Elle ne doit pas désactiver l'existence du partenaire ni la validité du couple. Une modification du contexte peut la rendre à revoir. **AR-14**

### Identifiants et valeurs

Conserver les identifiants de commande, partenaires et articles comme identifiants, sans conversion numérique destructrice des zéros initiaux. Utiliser la représentation numérique exacte prévue par la stack pour les montants et quantités ; la validité métier n'est pas définie par un type informatique seul. **P / AR-06**

<!-- PAGE -->
## 4. Contrat des changements de partenaires

### Une commande explicite, une opération cohérente

Proposition : le serveur reçoit l'intention de modification, calcule les rattachements dans un contexte stable, applique les effets approuvés, contrôle le résultat et renvoie la nouvelle version complète du bloc. Les remplissages dérivés ne sont pas simulés par des appels récursifs aux gestionnaires de saisie manuelle. **P / AR-02**

| Intention | Cardinalité connue | Transformation à appliquer |
|---|---|---|
| Choisir un Sold-to S | Un Ship-to T admissible | Renseigner T et ses données ; le traitement du choix racine et des propagations inverses suit AR-02. RM-05. |
| Choisir un Sold-to S | Zéro ou plusieurs T | Effacer uniquement le périmètre approuvé dans AR-01 ; motif distinct pour zéro et plusieurs. RM-06. |
| Choisir un Ship-to T | Un Sold-to S admissible | Renseigner adresse / données de T et S. RM-07 / RM-08. |
| Choisir un Ship-to T | Zéro ou plusieurs S | Renseigner adresse / données de T ; vider S. Ne pas effacer l'adresse parce que S manque. RM-07 / RM-08. |
| Choisir un partenaire | Référentiel indisponible / incomplet | Ne pas déduire la cardinalité ; signaler l'indisponibilité, sans appliquer un effacement calculé sur une fausse liste vide. P. |

### Pseudocode de structure, soumis aux politiques approuvées

```text
changer_partenaire(commande, intention, version_attendue):
  verifier_acteur_et_version()
  charger_contexte_et_rattachements_coherents()
  si contexte_indisponible: retourner_erreur_sans_mutation()
  exiger_politiques_approuvees(AR_01, AR_02, AR_03)
  changement = calculer_effets_de_l_intention()
  appliquer_changement_en_une_operation()
  invalider_confirmations_affectees()
  marquer_artefact_ancien_non_courant()
  reevaluer_controles_et_situations()
  enregistrer_nouvelle_version_et_trace()
  retourner_etat_complet_et_explication_des_changements()
```

Ne pas traiter le pseudocode comme une autorisation de remplir AR-01 ou AR-02 par une valeur arbitraire. Le choix d'une transaction de base, d'un contrôle optimiste ou de leur combinaison dépend de l'architecture auditée. Le résultat doit cependant être indivisible pour les consommateurs du bloc.

### Contrat de réponse utile au frontend

Retourner la version, les valeurs finales, les champs modifiés / vidés avec leur cause, les candidats / filtres, les confirmations devenues obsolètes, les situations courantes et les opérations autorisées avec leurs raisons. Une réponse ne doit pas affirmer que le bloc est vérifié parce qu'il est rempli.

<!-- PAGE -->
## 5. Ambiguïtés de propagation, TVA et adresse

### Deux tests différents, un arbitrage commun

**Cascade automatique.** A a un seul Ship-to X ; X est associé à A et B. Choisir A remplit X. Si cette affectation dérivée rejoue la sélection manuelle de X, A peut être vidé. AR-02 doit définir la priorité et l'origine des événements.

**Blocage manuel plusieurs-à-plusieurs.** A est associé à X et Y ; X est associé à A et B. Choisir A vide X ; choisir X vide A. Empêcher une récursion ne résout pas ce second cas. Le parcours doit permettre une paire stable suivant une décision métier explicite.

Propositions à soumettre : commande atomique de sélection de paire validée, maintien d'un partenaire explicitement confirmé s'il reste compatible, ou étape de finalisation distincte. **Ne pas activer une de ces options avant approbation AR-02.** Un test démontrant le blocage ne doit pas être rendu vert en assouplissant silencieusement RM-06 / RM-08.

### Contrat de recherche et unicité

Compter les partenaires distincts admissibles, pas les lignes d'une jointure ni les résultats d'une première page. Définir contexte commercial, filtres, statut et validité dans AR-03. Utiliser une version cohérente des rattachements pour une opération, et recontrôler si le contexte change avant envoi. **P**

La stratégie de TVA doit exposer valeur, provenance, filtres appliqués et motif de l'absence de résultats. Ne pas forcer le matching du lieu de livraison sur la seule TVA ; ne pas retirer le filtre en silence. Le choix "TVA absente" ne doit pas devenir un nouveau blocage autonome sans validation. **RM-03 / RM-04 ; AR-04**

### Adresse : séparer comparaison et donnée à transmettre

La correction de l'adresse extraite met à jour la transcription documentaire et relance les recherches approuvées. La sélection d'un Ship-to remplit son adresse de référentiel. Ne pas fusionner ces deux opérations ni écrire dans le référentiel à partir d'un champ de commande.

Conserver le PDF et les valeurs d'origine comme preuve. AR-05 définit l'adresse EDI, les possibilités de modification locale, la distinction des compléments de livraison et les contrôles nécessaires. Ne pas imposer une égalité textuelle stricte comme nouvelle règle de matching sans accord.

<!-- PAGE -->
## 6. Contrat frontend et espace de correction

### Informations et navigation

Conserver le PDF accessible pendant la correction. Identifier la page ou zone source lorsqu'elle est connue, sans inventer des coordonnées. Montrer les valeurs d'origine, actuelles et dérivées avec une provenance compréhensible. Faire ressortir les changements automatiques sans recharger toute la page ni perdre la position dans le PDF. **P**

La synthèse des situations renvoie au bloc ou à la ligne à traiter. Une fiche rassemble les diagnostics de même cause et de même portée. Une ambiguïté du client livré ne doit pas apparaître trois fois sous trois codes ; deux lignes différentes avec une quantité manquante restent deux cibles distinctes.

### Une mutation confirmée par le serveur

Utiliser un identifiant de requête et une version attendue. Une recherche ancienne terminant après une recherche récente ne doit pas remplacer le dernier choix. Annuler ou ignorer les réponses obsolètes selon la stack. Ne pas enregistrer de confirmation sur un état partiellement propagé.

Pendant l'enregistrement, la propagation ou une revalidation indispensable, indiquer l'opération en cours et suspendre les confirmations affectées / l'envoi. Après échec réseau, ne pas afficher "enregistré" sans preuve ; réconcilier l'état serveur au lieu de rejouer une action dangereuse.

### Outils et attestations ont des effets différents

"Rechercher", "Ajouter une ligne", "Enregistrer" et "Relancer la transmission" exécutent des opérations. "J'ai corrigé" et "J'ai vérifié" attestent le travail sur des données déjà enregistrées. Une confirmation ne doit pas appeler à nouveau la commande de sélection du même partenaire et provoquer un effacement inattendu.

Afficher une confirmation principale adaptée et les issues alternatives utiles. Ne pas présenter simultanément toutes les variantes ni un nombre fixe de boutons. Pour une valeur déjà correcte, permettre "J'ai vérifié" sans exiger une modification artificielle. Pour une valeur encore invalide, indiquer la condition manquante et ne pas déclarer l'anomalie résolue.

### Lisibilité et accès

Libellés explicites, navigation clavier, focus vers le champ concerné, états lisibles autrement que par la couleur, libellés pour les icônes et absence d'informations essentielles dans une infobulle seule. Un bouton indisponible doit avoir une raison visible. Aucune norme externe spécifique n'est revendiquée ici.

La confiance d'extraction ne remplace pas l'état de revue. Les coches de progression doivent distinguer étape exécutée et résultat validé. [S2 ; cible P]

<!-- PAGE -->
## 7. Catalogue, normalisation et regroupement

### Conserver les codes, découpler l'interface

Le moteur continue à produire les codes canoniques et leurs contextes. Une couche de présentation produit les situations UX, sans dépendre d'une comparaison de texte traduit. Normaliser les alias à l'entrée ; conserver le code d'origine dans les traces et ne pas réécrire l'historique sans migration définie.

Le catalogue source recense **17 alias pour 10 codes canoniques**. Importer leur liste depuis [S1, Règles colonne B], la tester et conserver une seule définition de référence pour les nouveaux messages / actions. Un ancien alias ne doit pas produire une seconde fiche ni perdre son blocage.

### Algorithme sémantique proposé

```text
1. Normaliser les codes et conserver leur provenance.
2. Resoudre la cible : commande, ligne, paire ou artefact.
3. Determiner les dependances et causes prouvees.
4. Produire une situation par besoin de travail et par cible.
5. Agreger les diagnostics sans supprimer leurs contraintes.
6. Calculer les actions selon etat, droits et arbitrages.
7. Exposer messages metier, champs utiles et impact sur l'envoi.
```

Les causes ne doivent pas être inférées sur le seul ordre des codes. Si le référentiel est indisponible, les recherches dépendantes sont **non exécutables**, pas "partenaire inexistant" et pas "contrôle réussi". Les conserver dans le diagnostic technique, avec une tâche principale sur l'indisponibilité.

### Cas à traiter explicitement

**PARTNER_UNRESOLVED :** utiliser comme synthèse ou secours, pas comme confirmation supplémentaire si les problèmes précis sont déjà représentés. **RESUBMISSION_DETECTED :** information seule ; ne pas créer d'acquittement obligatoire du seul fait de cette occurrence.

**NO_VALID_ARTICLE / ARTICLE_NOT_FOUND :** ne pas modifier leur sémantique ni la portée sans audit. Une occurrence de commande peut pointer plusieurs lignes ; la projection UI doit disposer de ces identifiants ou présenter un besoin de revue global honnête.

**Codes EDI :** orienter vers une fiche de donnée seulement si la donnée source est effectivement incorrecte. Si la donnée est correcte, conserver un incident de génération / version. Ne pas forcer l'ADV à aligner une bonne donnée sur un mauvais EDI.

**Code inconnu :** conserver le diagnostic et ses contraintes connues ; afficher un message de traitement / support compréhensible. Ne pas le masquer ni le traiter comme résolu par défaut. Si l'impact ne peut pas être déterminé, suspendre l'envoi jusqu'à clarification. **P**

<!-- PAGE -->
## 8. Contrat des confirmations et interfaces

### Requête logique de confirmation

Exemple de schéma, à adapter aux conventions de l'API existante. Les valeurs entre chevrons sont des paramètres, pas des données de production.

```json
{
  "commandId": "<identifiant-stable>",
  "expectedOrderVersion": 12,
  "situationId": "<instance-situation>",
  "actionId": "UX-16.CORRECT",
  "scope": {"type": "LINE", "id": "<ligne>"},
  "expectedScopeFingerprint": "<empreinte>",
  "reason": null,
  "evidenceReference": null
}
```

L'auteur et les habilitations proviennent du contexte d'authentification serveur, pas d'un champ envoyé par le navigateur. Le libellé et la version de la définition d'action sont résolus côté serveur. Le client ne transmet pas un droit `forceSend` ou `resolved=true` faisant autorité.

### Traitement serveur proposé

Vérifier la permission, la version de commande, la cible, l'existence de l'action dans le contexte courant, ses préconditions et ses preuves requises. Rejouer les contrôles affectés. Enregistrer la déclaration et le résultat effectif, puis recalculer situations et disponibilité des opérations. Une action périmée ou non autorisée doit produire une réponse explicite, pas un acquittement silencieux.

**Correction vérifiable :** le champ doit satisfaire la règle en vigueur. **Vérification humaine :** peut lever l'incertitude d'interprétation, mais pas un contrôle objectif violé. **Impossibilité / signalement :** conserver l'attente et le besoin d'intervention. **Clôture / exception :** appliquer la permission et la politique approuvées.

### Séparer déclaration et résolution

Une correction enregistrée peut faire disparaître une erreur de format avant la confirmation humaine ; le besoin de revue peut rester ouvert. Inversement, "J'ai signalé l'incident" peut être une confirmation valide tout en laissant l'incident non résolu. Les deux dimensions doivent être stockées ou dérivables séparément.

La confirmation globale peut remplacer plusieurs attestations de détail uniquement si son périmètre est explicite et ses valeurs courantes sont présentées. La durée et les conditions de validité suivent AR-14 ; aucune case cochée sur une ancienne version ne doit permettre l'envoi d'une nouvelle version.

### Interfaces à distinguer

Prévoir les responsabilités "modifier les données", "rechercher / sélectionner", "confirmer une intervention", "mettre en attente / transférer", "préparer l'EDI" et "demander l'envoi". Ne pas choisir les URL, verbes ou classes sans examiner les contrats actuels. Une reprise identique d'une même commande technique ne doit pas dupliquer la confirmation.

<!-- PAGE -->
## 9. États, revalidation et autorisation d'envoi

### Distinguer quatre dimensions

| Dimension proposée | Exemples d'états sémantiques |
|---|---|
| Contrôle automatique | Non exécuté, en cours, conforme, non conforme, impossible à exécuter. |
| Revue humaine | À vérifier, confirmée, confirmation devenue obsolète. |
| Suivi du dossier | En revue, en attente d'information, en attente technique, clôturé sans envoi. |
| Fichier / transmission | Non préparé, préparé, validé, ancien ; envoi demandé, en cours, réussi, échec certain, résultat incertain, retour SAP connu. |

Ces états ne sont pas des noms d'enums imposés. La correspondance avec REJECTED, PENDING_USER_INPUT, DUPLICATE et DELIVERY_FAILED du catalogue doit être auditée et approuvée. Ne pas migrer tous les REJECTED en attente ni en clôture automatique. **AR-13**

### Invalidations ciblées

Associer chaque confirmation aux données et dépendances qui la justifient. Le changement d'un partenaire invalide les confirmations affectées de la paire, de l'adresse effective et de l'EDI ; le changement d'une quantité n'a pas à faire perdre une vérification d'adresse indépendante. La confirmation finale, elle, doit toujours correspondre à la version à envoyer. **P / AR-14**

Définir dans une table explicite les contrôles dépendant des partenaires, de l'article, des quantités, des prix, des dates et du numéro. Les prix ou conditions dépendant du client ne sont pas supposés exister : les rechercher dans le code et documenter ceux qui sont réels.

### Prédicat serveur d'envoi proposé

```text
Envoi possible seulement si :
- acteur autorise et dossier non cloture ;
- version enregistree, aucune mutation pertinente en cours ;
- donnees obligatoires et paire partenaire valides ;
- au moins une ligne transmissible et contenu coherent ;
- tous les controles requis executes avec resultat exploitable ;
- blocages traites ou exceptions autorisees et tracees ;
- revue ADV courante du perimetre a transmettre ;
- artefact valide correspondant exactement a cette version ;
- protection contre doublon et statut de transport compatibles.
```

La préparation / validation EDI peut se faire avant le clic final ou dans une opération d'envoi en plusieurs étapes ; ne pas imposer un second clic inutile. En revanche, aucun transport ne commence avant la satisfaction du prédicat. Le boolean "Bloquante ?" du catalogue ne suffit pas à calculer seul cette autorisation.

<!-- PAGE -->
## 10. Génération EDI, transports et idempotence

### Relier le fichier à la version métier

Un fichier doit garder son identifiant, l'empreinte de son contenu, sa version de commande et les paramètres / référentiels nécessaires à son interprétation. Un changement pertinent rend l'artefact précédent non courant, sans supprimer sa preuve historique.

Valider la présence et la cohérence des informations que le catalogue contrôle : référence, date, acheteur, livraison, lignes et correspondance entre Ship-to et segment généré. Les détails de segments / mappings doivent être vérifiés dans le contrat EDI du projet, pas déduits d'une connaissance générale de SAP. [S1, Affichages L30-L36]

### Une demande d'envoi n'est pas une preuve de création SAP

Définir une intention d'envoi persistante et une identité métier / destination stable. Une clé différente à chaque clic ou un hash EDI différent après régénération ne doivent pas suffire à autoriser une deuxième commande métier. Le périmètre exact de déduplication reste AR-08.

Proposition d'implémentation à adapter : demande persistée avec contrainte d'unicité / verrouillage adapté, remise à un traitement de transport, mise à jour des tentatives et réconciliation après incident. Une table d'intentions ou un mécanisme de type outbox peut convenir si compatible avec l'architecture.

**Ne pas promettre une exécution exactement une fois entre systèmes** en l'absence d'un protocole et de preuves appropriés. Après timeout, le destinataire peut avoir reçu le fichier ; classer le résultat comme incertain et rechercher la preuve avant nouvelle transmission.

### Politique de reprise

| Situation | Traitement proposé |
|---|---|
| Donnée incorrecte | Correction, revalidation et nouvel artefact ; pas une relance identique. |
| Génération incorrecte | Reprise du générateur après correction de sa cause. |
| Échec certain du transport | Reprise autorisée de l'artefact approprié, avec traçabilité de tentative. |
| Transport de résultat incertain | Réconciliation puis décision ; pas de boucle de relance aveugle. |
| Un canal réussi, un autre en échec | Appliquer le rôle approuvé des canaux ; ne pas renvoyer automatiquement sur le canal déjà réussi. |

Les limites de tentatives, délais, canaux obligatoires et retours SAP sont AR-12. Aucun chiffre n'est imposé. La clôture d'un incident ou l'abandon d'un canal ne vaut pas transmission réussie.

<!-- PAGE -->
## 11. Droits, traces et données de référence

### Contrôles à appliquer côté serveur

Distinguer modification d'une commande, confirmation de revue, exclusion / substitution, transfert, clôture, synchronisation du référentiel, dérogation de doublon et nouvelle transmission. Les rôles nommés et leurs habilitations sont AR-10 ; ne pas attribuer des droits supplémentaires à l'ADV du seul fait qu'il peut modifier un champ.

L'interface ne doit pas rendre une opération possible en envoyant un drapeau de contournement. Vérifier les valeurs sélectionnées, le rattachement, la version et la cible sur le serveur ; un identifiant présent dans une liste ancienne n'est pas une preuve d'éligibilité actuelle.

### Traces structurées

Pour toute mutation ou confirmation : identifiant de commande technique, acteur, instant, version avant / après, origine manuelle ou dérivée, données concernées, code / situation / action, justification, contrôles réexécutés et effet sur l'envoi. Pour les exclusions, conserver l'identité et les valeurs de la ligne ; pour les dérogations, le décideur et le fondement.

Éviter les secrets, fichiers complets et données inutiles dans les journaux techniques. Les traces métier et les documents doivent suivre les droits et durées approuvés AR-15. Un commentaire libre ne suffit pas à représenter une décision structurée.

### Référentiels : indisponibilité et changement

Vérifier la disponibilité, la structure et le périmètre chargé avant de conclure qu'un partenaire ou un article est absent. La confirmation "J'ai été informé que les données ont été mises à jour" ne remplace pas cette vérification serveur.

Une mise à jour peut changer les rattachements. Recontrôler les confirmations dépendantes et signaler les incompatibilités ; ne pas remplacer silencieusement les partenaires choisis. La politique de gel / actualisation des référentiels et la fraîcheur requise avant envoi sont à définir dans AR-03 / AR-14.

### Concurrence et reprise de session

Si deux ADV modifient le même dossier, rejeter ou réconcilier explicitement une écriture obsolète ; ne pas confirmer des données qui viennent d'être remplacées par un autre utilisateur. Une nouvelle session doit recharger les valeurs et confirmations courantes, pas restaurer un bouton "envoyable" depuis un cache ancien. **P**

<!-- PAGE -->
## 12. Plan de réalisation et migration

### Lots recommandés

| Lot | Livrable et garde de passage |
|---|---|
| L0 - Audit | Cartographie code / RM / UX / tests, comportements observés, captures avant, liste des écarts. Aucune mutation métier risquée. |
| L1 - Arbitrages et contrats | Politiques approuvées de partenaires, effacements, unicité, TVA, droits et états. Distinguer les éléments encore en attente. |
| L2 - Noyau partenaires | Transformations testables, effets atomiques, provenance, gestion des réponses obsolètes et tests de propagation. |
| L3 - Situations et confirmations | Registre versionné, regroupement, options conditionnelles, états de revue, attente et audit. |
| L4 - EDI et transmission | Contrôles de version, invalidation, prédicat d'envoi, reprises ciblées et protection anti-duplication. |
| L5 - Migration et recette | Compatibilité des anciens dossiers, tests de bout en bout sans envoi réel, approbation métier, déploiement progressif. |

### Compatibilité à expliciter

Conserver les codes / alias et les historiques ; la nouvelle couche UI peut être ajoutée sans renommer immédiatement les codes du moteur. Ne pas supprimer une anomalie ancienne parce qu'aucune nouvelle carte ne la reconnaît. Documenter toute migration de statut, de payload et de validation.

Ne pas fabriquer des confirmations humaines pour les anciens dossiers à partir d'une coche verte, d'un score de confiance ou d'un ancien bouton. Conserver les preuves existantes ; lorsqu'elles ne permettent pas d'établir la revue courante, prévoir une remise en revue explicitement approuvée.

Si des commandes sont déjà transmises, leur migration n'autorise ni la réémission ni le retraitement destructif. Un retour arrière applicatif ne doit pas effacer les preuves des envois effectués pendant le déploiement. Éviter de lancer les anciens et nouveaux chemins de transport en parallèle.

### Preuves exigées dans le compte rendu de l'agent

Fichiers modifiés et raison ; RM / UX / AR concernés ; tests ajoutés ; commandes de test réellement exécutées et résultats ; limites restantes ; preuves visuelles des principaux parcours ; plan de migration et retour arrière. Une fonctionnalité non exécutée en test doit être annoncée comme telle.

Un arbitrage ouvert bloque l'activation des comportements qui en dépendent, pas tout travail sur le projet. L'audit, les tests de caractérisation, le regroupement de lecture et la préparation des contrats peuvent avancer sans inventer la décision manquante.

<!-- PAGE -->
## 13. Tests d'acceptation - partenaires

Les attendus ci-dessous sont des cibles P, ou la transcription des RM citées. Les tests AR doivent être complétés par l'attendu approuvé avant activation ; ne pas les marquer comme satisfaits par une hypothèse.

| ID | Cas et attendu vérifiable |
|---|---|
| T-P01 | Sold-to S avec un Ship-to T : T et ses données sont renseignés selon RM-05 ; un changement expliqué est retourné. |
| T-P02 | Sold-to avec plusieurs Ship-to : seul le périmètre AR-01 est effacé ; aucun champ non approuvé n'est perdu. |
| T-P03 | Sold-to avec zéro Ship-to connu : même politique d'effacement, motif "aucun" distinct de "plusieurs". |
| T-P04 | Ship-to avec un Sold-to : adresse et informations de T, puis S renseignés selon RM-07 / RM-08. |
| T-P05 | Ship-to avec plusieurs Sold-to : adresse renseignée et Sold-to vide, sans fausse confirmation globale. |
| T-P06 | Ship-to sans Sold-to : adresse conservée, donneur d'ordre vide et absence de rattachement expliquée. |
| T-P07 | Cascade A > X > plusieurs Sold-to : aucun effacement récursif non approuvé ; résultat conforme à AR-02. |
| T-P08 | Plusieurs-à-plusieurs A / X : paire finalisable selon AR-02 ; pas d'alternance insoluble de champs vides. |
| T-P09 | Référentiel indisponible : aucune cardinalité déduite, aucune mutation fondée sur une liste vide artificielle. |
| T-P10 | Jointure retournant deux fois le même partenaire : cardinalité sur identifiants distincts ; pagination non interprétée comme unicité. |
| T-P11 | TVA absente : comportement AR-04, sans nouveau blocage autonome inventé. |
| T-P12 | TVA erronée puis corrigée : filtres visibles, candidats recalculés, choix confirmé non remplacé en silence. |
| T-P13 | TVA confirmée contredit les candidats : conflit explicite ; pas de suppression silencieuse du filtre. |
| T-P14 | Adresse documentaire corrigée : original conservé, transcription changée, recherches / confirmations concernées réévaluées. |
| T-P15 | Ship-to changé : adresse partenaire mise à jour sans écraser la preuve documentaire. |
| T-P16 | Couple incompatible forgé directement dans l'API : validation serveur refuse le contournement. |
| T-P17 | Ancienne recherche termine après la nouvelle : elle ne remplace pas le dernier état. |
| T-P18 | Rattachement modifié entre revue et envoi : recontrôle / expiration selon AR-14 ; pas de confirmation obsolète acceptée. |

### Jeu de données de test

Prévoir des partenaires fictifs A, B, X, Y et des relations explicites pour 0, 1 et plusieurs résultats dans les deux sens. Inclure un doublon de ligne de référentiel, un chargement incomplet, une TVA filtrante et une contradiction. Ne pas utiliser un client réel ni appeler SAP pour prouver ces unités de comportement.

<!-- PAGE -->
## 14. Tests d'acceptation - interface et confirmations

| ID | Cas et attendu vérifiable |
|---|---|
| T-U01 | Deux codes d'ambiguïté Ship-to même cible : une seule fiche compréhensible, tous les diagnostics conservés. |
| T-U02 | Deux quantités manquantes sur deux lignes : deux cibles distinctes ; aucune confirmation globale implicite. |
| T-U03 | Valeur valide mais incorrecte au regard du PDF : modification autorisée dans les champs habilités. |
| T-U04 | "J'ai corrigé la quantité" avec valeur encore invalide : pas de résolution ; raison affichée. |
| T-U05 | Quantité correcte enregistrée puis confirmée : trace sur la bonne ligne et les bonnes valeurs. |
| T-U06 | Sélection déjà correcte : "J'ai vérifié" disponible sans modification artificielle. |
| T-U07 | Confirmation du partenaire : ne réexécute pas la commande de sélection et ne vide pas l'en-tête. |
| T-U08 | Nouvelle modification pertinente : confirmation affectée à revoir ; confirmation finale obsolète. |
| T-U09 | Ambiguïté humainement confirmée, revalidation sans changement : ne pas demander la même confirmation en boucle. |
| T-U10 | "Je n'ai pas pu résoudre" : motif / responsable / information attendue ; dossier non envoyable. |
| T-U11 | "J'ai demandé une clarification" : enregistre une démarche ; ne déclenche pas silencieusement un email. |
| T-U12 | Signalement technique : confirmation tracée mais incident non résolu ; aucune fausse réussite. |
| T-U13 | Un utilisateur envoie une action cachée ou interdite via API : refus serveur avec raison. |
| T-U14 | Deux ADV, version obsolète : pas d'écrasement ni de confirmation sur de mauvaises valeurs. |
| T-U15 | Réessai de la même commande de confirmation : une seule décision logique, pas de doublon d'effet. |
| T-U16 | Information de resoumission seule : pas de confirmation obligatoire ajoutée. |
| T-U17 | Code inconnu : diagnostic conservé, comportement prudent et support ; pas de disparition silencieuse. |
| T-U18 | Navigation clavier, focus, libellés et états sans couleur : parcours utilisable ; raison du bouton indisponible visible. |

### Tests de projection du catalogue

Vérifier l'égalité entre les 38 codes canoniques affichés et la table de correspondance ; l'absence de collision d'alias ; la couverture des 23 situations ; la stabilité des identifiants d'action ; la disponibilité conditionnelle des options ; l'absence de libellé exigeant une intervention technique de l'ADV qu'il ne peut pas attester.

Les assertions doivent porter sur l'effet serveur et l'état final, pas seulement sur le texte du bouton. Un clic visible en test navigateur ne prouve pas la revalidation, l'habilitation ou la traçabilité.

<!-- PAGE -->
## 15. Tests d'acceptation - contenu, EDI et transport

| ID | Cas et attendu vérifiable |
|---|---|
| T-I01 | Référence corrigée : existence et statut réévalués ; pas de simple acquittement. |
| T-I02 | Exclusion / substitution non autorisée : action indisponible et API protégée. |
| T-I03 | Dernier article exclu : aucune commande sans ligne transmise ; historique conservé. |
| T-I04 | Prix absent, prix nul, quantité décimale, date de ligne : attendus conformes aux règles AR-06, sans valeurs par défaut inventées. |
| T-I05 | Numéro de commande avec zéro initial : préservé ; doublon rejoué après correction. |
| T-I06 | Donnée métier absente et erreur EDI correspondante : une intervention principale sur la cause, diagnostics conservés. |
| T-I07 | Donnée correcte et EDI incohérent : incident de génération ; aucune correction métier forcée. |
| T-I08 | Modification après génération : l'ancien fichier ne peut pas être envoyé comme version courante. |
| T-I09 | Données non enregistrées / propagation en cours : envoi refusé côté serveur. |
| T-I10 | Doublon potentiel : la confirmation de commande distincte suit AR-08 et ne supprime pas les autres blocages. |
| T-I11 | Commande déjà envoyée : aucune réémission par simple bouton de revue ou nouveau hash de fichier. |
| T-I12 | Double clic / appels concurrents d'envoi : une seule intention autorisée selon la clé métier approuvée. |
| T-I13 | Timeout après remise possible du fichier : résultat incertain, réconciliation avant nouvelle tentative. |
| T-I14 | SFTP réussi, email en échec : pas de nouvel upload automatique ; comportement conforme au rôle des canaux. |
| T-I15 | Transport réussi sans retour SAP : interface ne prétend pas qu'une commande SAP a été créée. |
| T-I16 | Données maîtres absentes ou mauvais schéma : recherches impossibles, pas de faux clients / articles introuvables en cascade. |
| T-I17 | Resoumission / nouveau PDF après correction : appliquer AR-11, conserver preuves, pas de perte silencieuse. |
| T-I18 | Migration d'un ancien dossier envoyé : historique conservé, aucun renvoi ; retour arrière sans perte des preuves. |

### Niveaux de preuve

Tests unitaires des transformations ; tests d'intégration des contrats, persistance et génération ; tests de bout en bout des parcours ADV ; simulation des échecs / concurrences ; recette métier sur cas approuvés. Les transports doivent être simulés ou dirigés vers un environnement de test explicitement autorisé.

Les 54 scénarios T-P, T-U et T-I forment une base de recette proposée. Ils ne constituent pas des tests déjà exécutés.

<!-- PAGE -->
## 16. Registre d'actions - document et extraction

Chaque identifiant ci-dessous désigne une définition d'action proposée, non une permission implicite. Le libellé peut être contextualisé sans changer son effet. Les conditions générales de version, droit, cible, revalidation et audit s'appliquent à toutes les entrées.

### UX-01 - Fichier utilisable

**Message proposé :** Le fichier ne permet pas de préparer la commande.

Distinguer format non PDF, fichier illisible et échec de lecture par le moteur. Afficher la version du document et donner accès à son aperçu.

*Origine des situations : [S1], Affichages L3, L4. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-01.REPLACE`<br>J'ai remplacé le fichier par un PDF exploitable | **Condition :** Une nouvelle version a effectivement été déposée et enregistrée.<br>**Suite :** Contrôler le nouveau fichier ; reprendre l'extraction selon AR-11, sans effacer silencieusement les corrections. |
| `UX-01.READABLE`<br>J'ai vérifié : le PDF est lisible | **Condition :** Le document est un PDF ; l'ADV a consulté son contenu.<br>**Suite :** Enregistrer le constat, pas une réparation ; proposer une reprise ciblée ou orienter au support si la lecture échoue encore. |
| `UX-01.UNRESOLVED`<br>Je n'ai pas pu obtenir un document exploitable | **Condition :** Motif et information attendue renseignés.<br>**Suite :** Dossier en attente ; aucune génération ni transmission sur des données non vérifiables. |



### UX-02 - Nature du document

**Message proposé :** La nature du document doit être confirmée.

Montrer le PDF et le motif de suspicion sans affirmer qu'un mot-clé suffit à prouver que ce n'est pas une commande.

*Origine des situations : [S1], Affichages L5, L6. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-02.IS_ORDER`<br>J'ai vérifié : il s'agit bien d'un bon de commande | **Condition :** Document consulté ; confirmation liée à cette version.<br>**Suite :** Confirmer la classification ; poursuivre les autres contrôles, sans envoyer. |
| `UX-02.NOT_ORDER`<br>J'ai vérifié : ce document n'est pas un bon de commande | **Condition :** Nature constatée et motif enregistrés.<br>**Suite :** Clôturer comme document non commande, selon les droits validés. |
| `UX-02.UNRESOLVED`<br>Je n'ai pas pu déterminer la nature du document | **Condition :** Motif enregistré.<br>**Suite :** Attente de clarification ; ne pas convertir automatiquement en commande. |



### UX-03 - Modification de commande

**Message proposé :** Ce document semble modifier une commande existante.

Permettre de retrouver la commande initiale, sans confondre correction d'une classification et création d'une nouvelle commande.

*Origine des situations : [S1], Affichages L7. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-03.INITIAL`<br>J'ai vérifié : c'est une commande initiale | **Condition :** Conclusion justifiée sur le PDF ; contrôle de doublon maintenu.<br>**Suite :** Corriger la classification et poursuivre la revue. |
| `UX-03.CHANGE`<br>J'ai identifié une modification de commande existante | **Condition :** Référence de la commande initiale si disponible.<br>**Suite :** Orienter vers le circuit approuvé AR-09 ; ne pas envoyer comme une nouvelle commande. |
| `UX-03.UNRESOLVED`<br>Je n'ai pas pu distinguer une nouvelle commande d'une modification | **Condition :** Motif enregistré.<br>**Suite :** Attente de clarification. |



### UX-04 - Revue des informations préremplies

**Message proposé :** Les informations préremplies doivent être vérifiées sur le document.

La revue concerne aussi les valeurs qui passent les contrôles automatiques. Conserver les bonnes données et corriger seulement celles qui l'exigent.

*Origine des situations : [S1], Affichages L8. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-04.REVIEWED`<br>J'ai vérifié les informations préremplies et effectué les corrections nécessaires | **Condition :** Périmètre explicitement présenté ; valeurs enregistrées et contrôlées.<br>**Suite :** Enregistrer la revue de ce périmètre ; laisser ouverts les autres problèmes. |
| `UX-04.INCOMPLETE`<br>J'ai constaté des informations ou des lignes manquantes | **Condition :** Éléments concernés identifiés.<br>**Suite :** Orienter vers leur saisie dans l'espace existant ; ne pas imposer une nouvelle extraction complète. |
| `UX-04.UNRESOLVED`<br>Je n'ai pas pu vérifier toutes les informations | **Condition :** Champs ou lignes non vérifiés identifiés.<br>**Suite :** Revue incomplète / attente ; pas de confirmation globale. |



## 17. Registre d'actions - partenaires

RM-05 à RM-08 s'appliquent aux sélections ; les confirmations portent sur le résultat stabilisé. Le regroupement UX ne change pas les règles de remplissage ni le périmètre d'effacement AR-01.

### UX-05 - Adresse de livraison à vérifier

**Message proposé :** L'adresse de livraison n'a pas pu être identifiée dans le document.

Présenter l'adresse documentaire, sa provenance et le PDF. Ne pas confondre absence d'extraction et absence réelle d'adresse.

*Origine des situations : [S1], Affichages L9. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-05.CORRECT`<br>J'ai renseigné ou corrigé l'adresse de livraison | **Condition :** Les champs documentaires concernés sont enregistrés.<br>**Suite :** Contrôler et rechercher le Ship-to ; remettre en revue les partenaires affectés. La paire n'est pas encore confirmée. |
| `UX-05.ABSENT`<br>J'ai vérifié : l'adresse de livraison n'est pas indiquée | **Condition :** Constat sur la bonne zone du document.<br>**Suite :** Attente d'une adresse ; ne pas utiliser l'adresse de facturation par défaut. |
| `UX-05.UNREADABLE`<br>Je n'ai pas pu lire l'adresse de livraison | **Condition :** Motif et document concerné renseignés.<br>**Suite :** Attente d'un document lisible ou de clarification. |



### UX-06 - Client livré à confirmer

**Message proposé :** Le client livré correspondant à l'adresse doit être confirmé.

Une même fiche couvre les candidats ambigus ou peu probants. Montrer aucun / plusieurs résultats, adresse documentaire, partenaires proposés et filtres actifs.

*Origine des situations : [S1], Affichages L10, L11, L12. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-06.CORRECT`<br>J'ai corrigé le client livré et vérifié son adresse | **Condition :** Ship-to sélectionné, données propagées stabilisées, adresse comparée au PDF.<br>**Suite :** Valider ce périmètre ; réévaluer le Sold-to selon RM-07 / RM-08 et AR-02. |
| `UX-06.VERIFY`<br>J'ai vérifié : le client livré et son adresse sont corrects | **Condition :** Une sélection existe ; aucune modification artificielle requise.<br>**Suite :** Enregistrer la confirmation humaine ; ne pas neutraliser les contrôles de rattachement. |
| `UX-06.NO_MATCH`<br>J'ai vérifié l'adresse, mais aucun lieu proposé ne correspond | **Condition :** Adresse connue ; recherche et filtres présentés.<br>**Suite :** Conserver l'adresse recherchée ; vérifier les filtres puis orienter vers le référentiel si nécessaire. |
| `UX-06.BAD_SOLDTO`<br>J'ai confirmé le client livré, mais le donneur d'ordre proposé est incorrect | **Condition :** Ship-to effectivement vérifié.<br>**Suite :** Ouvrir UX-07 / UX-08 sans déclarer la paire valide ; toute modification ultérieure reste soumise aux automatismes. |
| `UX-06.UNRESOLVED`<br>Je n'ai pas pu confirmer le lieu de livraison | **Condition :** Motif enregistré.<br>**Suite :** Attente ; pas d'envoi. |



### UX-07 - Donneur d'ordre à confirmer

**Message proposé :** Le donneur d'ordre de cette commande reste à confirmer.

Afficher le Ship-to retenu, ses rattachements, les informations du document et la TVA utilisée. Distinguer aucun candidat et plusieurs candidats.

*Origine des situations : [S1], Affichages L14, L15. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-07.CONFIRM`<br>J'ai sélectionné et vérifié le bon donneur d'ordre | **Condition :** Sold-to sélectionné ; propagation terminée.<br>**Suite :** Contrôler l'état final. Si la livraison a été vidée ou changée, elle reste à revoir. |
| `UX-07.NOT_LISTED`<br>J'ai identifié le donneur d'ordre, mais il n'est pas proposé | **Condition :** Identifiant ou informations du client recherché enregistrés.<br>**Suite :** Vérifier TVA, filtres et rattachements ; ne pas créer automatiquement un partenaire. |
| `UX-07.VAT_CORRECT`<br>J'ai corrigé le numéro de TVA utilisé pour la recherche | **Condition :** Valeur modifiée et source identifiée.<br>**Suite :** Recalculer les candidats selon AR-04 ; la TVA seule ne confirme pas la paire. |
| `UX-07.UNRESOLVED`<br>Je n'ai pas pu identifier le donneur d'ordre | **Condition :** Motif renseigné.<br>**Suite :** Attente, avec conservation des informations déjà acquises et de leur historique. |



### UX-08 - Rattachement des partenaires à vérifier

**Message proposé :** Le client livré et le donneur d'ordre ne forment pas un rattachement valide.

Montrer la paire et la livraison attendue. Ne pas imposer de changer une livraison correcte pour conserver un Sold-to erroné.

*Origine des situations : [S1], Affichages L13. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-08.PAIR`<br>J'ai vérifié le donneur d'ordre, le client livré et l'adresse | **Condition :** Paire complète, relation valide, propagations terminées et comparaison au PDF.<br>**Suite :** Confirmer le bloc partenaires ; pas d'envoi automatique. |
| `UX-08.REFERENCE`<br>J'ai identifié les deux partenaires, mais leur rattachement n'est pas proposé | **Condition :** Identifiants et éléments de justification renseignés.<br>**Suite :** Transmettre au responsable du référentiel ; maintenir le blocage sans créer de relation. |
| `UX-08.UNRESOLVED`<br>Je n'ai pas pu confirmer le bon rattachement | **Condition :** Motif renseigné.<br>**Suite :** Attente de clarification ; AR-02 s'applique aux cas plusieurs-à-plusieurs. |



### UX-09 - Vérification du bloc partenaires

**Message proposé :** Les partenaires de la commande doivent être vérifiés.

Fiche de synthèse ou de secours seulement. Ne pas la doubler si UX-05 à UX-08 décrivent déjà l'intervention.

*Origine des situations : [S1], Affichages L16. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-09.PAIR`<br>J'ai vérifié le donneur d'ordre, le client livré et l'adresse | **Condition :** Paire complète et contrôlée ; périmètre de revue affiché.<br>**Suite :** Confirmer le bloc sur sa version courante ; conserver les autres situations. |
| `UX-09.UNRESOLVED`<br>Je n'ai pas pu confirmer tous les partenaires | **Condition :** Partie non résolue et motif identifiés.<br>**Suite :** Orienter vers le point restant ou l'attente ; ne pas clôturer faute de partenaires par défaut. |



## 18. Registre d'actions - doublons

### UX-10 - Doublon possible

**Message proposé :** Une commande avec ce numéro a déjà été trouvée.

Comparer le dossier et l'historique disponible ; afficher sa provenance et sa date. Un numéro identique ne prouve pas seul que la commande a été envoyée.

*Origine des situations : [S1], Affichages L18. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-10.NUMBER`<br>J'ai corrigé le numéro de commande extrait | **Condition :** Nouvelle valeur enregistrée et comparée au document.<br>**Suite :** Rejouer le contrôle de doublon et invalider le fichier EDI ancien. |
| `UX-10.SAME`<br>J'ai vérifié : il s'agit de la même commande | **Condition :** Dossier de comparaison identifié.<br>**Suite :** Clôturer comme doublon selon les droits, sans nouvel envoi. |
| `UX-10.DISTINCT`<br>J'ai vérifié : il s'agit d'une commande distincte | **Condition :** Justification et habilitation / approbation définies par AR-08.<br>**Suite :** Enregistrer la décision autorisée ; conserver tous les autres contrôles d'envoi. |
| `UX-10.UNRESOLVED`<br>Je n'ai pas pu déterminer s'il s'agit d'un doublon | **Condition :** Motif renseigné.<br>**Suite :** Attente de comparaison complémentaire. |



### UX-11 - Commande déjà transmise

**Message proposé :** Cette commande est indiquée comme déjà transmise.

Afficher la preuve disponible : tentative, fichier, horodatage et retour, sans inventer de confirmation SAP.

*Origine des situations : [S1], Affichages L17. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-11.SAME`<br>J'ai vérifié : cette commande a déjà été traitée | **Condition :** Historique consulté.<br>**Suite :** Clôturer comme doublon, sans nouvel envoi. |
| `UX-11.DISPUTE`<br>J'ai constaté que le rapprochement avec la commande transmise est incorrect | **Condition :** Dossier comparé et justification.<br>**Suite :** Soumettre au circuit AR-08 ; cette déclaration n'autorise pas la réémission. |
| `UX-11.UNRESOLVED`<br>Je n'ai pas pu confirmer le résultat de l'envoi précédent | **Condition :** Preuve manquante ou incohérente identifiée.<br>**Suite :** Réconcilier le transport / SAP avant toute nouvelle tentative. |



### UX-12 - Nouveau dépôt du document

**Message proposé :** Ce document a déjà été déposé.

Information d'historique, sans acquittement obligatoire supplémentaire. Montrer le lien entre versions et le devenir des corrections selon AR-11.

*Origine des situations : [S1], Affichages L19. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-12.INFO`<br>Aucune confirmation obligatoire pour cette seule information | **Condition :** Aucun doublon envoyé ni autre blocage déduit de cette seule occurrence.<br>**Suite :** Conserver la trace ; une nouvelle extraction ne vaut ni nouvelle commande ni autorisation de renvoi. |



## 19. Registre d'actions - lignes

Les variantes de libellé, par exemple "renseigné" au lieu de "corrigé", doivent refléter l'intervention possible sans changer silencieusement la portée de confirmation.

### UX-13 - Référence article à vérifier

**Message proposé :** La référence de cette ligne n'a pas pu être validée.

Montrer la référence extraite, celle retenue, la désignation et la ligne du PDF. Ne pas déduire de NO_VALID_ARTICLE qu'aucun article n'est valide sans vérifier sa condition réelle.

*Origine des situations : [S1], Affichages L20, L24. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-13.CORRECT`<br>J'ai corrigé la référence article | **Condition :** Référence enregistrée.<br>**Suite :** Vérifier existence, statut et dépendances ; confirmer cette ligne seulement. |
| `UX-13.UNRESOLVED`<br>Je n'ai pas pu identifier la référence à commander | **Condition :** Motif et ligne identifiés.<br>**Suite :** Attente de clarification. |
| `UX-13.EXCLUDE`<br>J'ai exclu cette ligne de la commande à transmettre | **Condition :** Exclusion déjà effectuée et autorisée selon AR-07 ; motif.<br>**Suite :** Conserver la ligne exclue dans l'historique ; recalculer le contenu restant ; jamais transmettre zéro ligne. |



### UX-14 - Article non vendable ou remplacé

**Message proposé :** Le statut de l'article empêche la vente ou indique un remplacement.

Présenter le motif, la date et la référence de remplacement uniquement lorsqu'ils sont disponibles. Ne pas importer des règles FAB-DIS non approuvées.

*Origine des situations : [S1], Affichages L22. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-14.CORRECT`<br>J'ai corrigé la référence article | **Condition :** La référence initiale était mal saisie ou extraite.<br>**Suite :** Rejouer les contrôles de la nouvelle référence. |
| `UX-14.REPLACE`<br>J'ai renseigné la référence de remplacement autorisée | **Condition :** Substitution approuvée selon AR-07 et nouvelle référence enregistrée.<br>**Suite :** Contrôler la nouvelle ligne et les données dépendantes. |
| `UX-14.EXCLUDE`<br>J'ai exclu cette ligne de la commande à transmettre | **Condition :** Exclusion autorisée et motivée.<br>**Suite :** Recontrôler les lignes restantes ; ne pas masquer une commande partielle. |
| `UX-14.UNRESOLVED`<br>Je n'ai pas pu déterminer une solution pour cet article | **Condition :** Motif renseigné.<br>**Suite :** Attente ou transfert au responsable compétent. |



### UX-15 - Lignes de commande à compléter

**Message proposé :** Les lignes de commande doivent être renseignées.

Comparer toutes les pages pertinentes du PDF. L'absence de lignes extraites ne prouve pas l'absence d'articles dans le document.

*Origine des situations : [S1], Affichages L23. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-15.ADD`<br>J'ai ajouté les lignes articles du bon de commande | **Condition :** Au moins une ligne effective a été enregistrée.<br>**Suite :** Contrôler chaque ligne et sa complétude ; ne pas simplement vérifier le nombre. |
| `UX-15.NONE`<br>J'ai vérifié : le document ne contient aucune ligne à commander | **Condition :** Constat sur le document ; motif de clôture approuvé.<br>**Suite :** Clôturer sans transmission ou orienter vers clarification selon le motif. |
| `UX-15.UNRESOLVED`<br>Je n'ai pas pu reconstituer les lignes de la commande | **Condition :** Lignes ou pages concernées indiquées.<br>**Suite :** Attente d'informations ; pas de fichier envoyable sans ligne. |



### UX-16 - Quantité à vérifier

**Message proposé :** La quantité de cette ligne est manquante ou invalide.

Afficher la ligne, la valeur actuelle et la règle de validité effectivement configurée. Pas de seuil inventé.

*Origine des situations : [S1], Affichages L21, L25. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-16.CORRECT`<br>J'ai corrigé la quantité | **Condition :** Valeur enregistrée ; variante "J'ai renseigné la quantité" si elle était absente.<br>**Suite :** Recontrôler la valeur, les dépendances et le contenu de la ligne ; confirmer ce périmètre. |
| `UX-16.ABSENT`<br>J'ai vérifié : la quantité n'est pas indiquée | **Condition :** Constat sur la ligne du document.<br>**Suite :** Attente d'une quantité ; ne pas inventer une valeur pour débloquer. |
| `UX-16.UNREADABLE`<br>Je n'ai pas pu lire la quantité | **Condition :** Motif et ligne renseignés.<br>**Suite :** Attente d'un document lisible ou d'une clarification. |



### UX-17 - Prix unitaire à renseigner

**Message proposé :** Le prix unitaire de cette ligne doit être renseigné.

Montrer le prix extrait / retenu et, si disponibles, l'unité et la devise. Prix absent et prix nul ne sont pas automatiquement équivalents : AR-06.

*Origine des situations : [S1], Affichages L26. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-17.FILL`<br>J'ai renseigné le prix unitaire | **Condition :** Valeur enregistrée avec le contexte autorisé.<br>**Suite :** Contrôler la ligne et recalculer les valeurs dépendantes. |
| `UX-17.ABSENT`<br>J'ai vérifié : le prix n'est pas indiqué sur le document | **Condition :** Constat enregistré.<br>**Suite :** Attente de l'information ou circuit tarifaire approuvé, sans prix fabriqué. |
| `UX-17.UNRESOLVED`<br>Je n'ai pas pu déterminer le prix unitaire | **Condition :** Motif enregistré.<br>**Suite :** Attente ou transfert selon l'organisation retenue. |



## 20. Registre d'actions - commande

### UX-18 - Numéro de commande à renseigner

**Message proposé :** Le numéro de commande client doit être renseigné.

Comparer au PDF ; conserver les zéros initiaux et autres caractères selon la règle validée. Ne pas fabriquer un numéro.

*Origine des situations : [S1], Affichages L28. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-18.FILL`<br>J'ai renseigné le numéro de commande client | **Condition :** Valeur enregistrée et comparée au document.<br>**Suite :** Vérifier la validité, rejouer les doublons et actualiser la référence EDI. |
| `UX-18.ABSENT`<br>J'ai vérifié : le numéro n'est pas indiqué | **Condition :** Constat documenté.<br>**Suite :** Attente de clarification. |
| `UX-18.UNRESOLVED`<br>Je n'ai pas pu identifier le numéro de commande | **Condition :** Motif indiqué.<br>**Suite :** Attente ; ne pas réutiliser un autre identifiant sans règle approuvée. |



### UX-19 - Date de commande à vérifier

**Message proposé :** La date de commande doit être vérifiée.

Afficher la date du document et la valeur saisie ; le catalogue conseille JJ/MM/AAAA mais ne définit pas toutes les règles de validité.

*Origine des situations : [S1], Affichages L27. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-19.CORRECT`<br>J'ai renseigné ou corrigé la date de commande | **Condition :** Valeur enregistrée.<br>**Suite :** Contrôler la date puis actualiser les données EDI concernées. |
| `UX-19.ABSENT`<br>J'ai vérifié : la date de commande n'est pas indiquée | **Condition :** Constat documenté.<br>**Suite :** Attente ; pas de remplacement automatique par la date du jour. |
| `UX-19.UNRESOLVED`<br>Je n'ai pas pu déterminer la date de commande | **Condition :** Motif renseigné.<br>**Suite :** Attente de clarification. |



### UX-20 - Date de livraison de ligne à vérifier

**Message proposé :** La date de livraison de cette ligne doit être vérifiée.

Pointer la ligne concernée ; distinguer date d'en-tête et date propre à la ligne. L'héritage entre les deux reste AR-06.

*Origine des situations : [S1], Affichages L29. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-20.CORRECT`<br>J'ai renseigné ou corrigé la date de livraison de cette ligne | **Condition :** Valeur de la ligne enregistrée.<br>**Suite :** Contrôler cette date et actualiser l'EDI concerné. |
| `UX-20.ABSENT`<br>J'ai vérifié : la date de livraison n'est pas précisée | **Condition :** Document et ligne vérifiés.<br>**Suite :** Attente ou application d'une règle de date approuvée, sans en inventer une. |
| `UX-20.UNRESOLVED`<br>Je n'ai pas pu confirmer la date de livraison | **Condition :** Motif renseigné.<br>**Suite :** Attente de clarification. |



## 21. Registre d'actions - technique

Ne pas enregistrer une réussite de transport, de génération ou de synchronisation sur la seule base d'une confirmation humaine.

### UX-21 - Préparation du fichier de transmission

**Message proposé :** Le fichier de transmission ne reproduit pas correctement la commande.

Si une donnée source est réellement manquante, orienter vers sa fiche métier. Si la donnée est correcte, montrer l'échec de préparation, pas un segment EDI à modifier.

*Origine des situations : [S1], Affichages L30, L31, L32, L33, L34, L35, L36. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-21.SOURCE`<br>J'ai corrigé les informations de la commande concernées | **Condition :** Données enregistrées et contrôlées.<br>**Suite :** Régénérer puis valider le fichier de la version courante ; ne pas envoyer l'ancienne version. |
| `UX-21.BUSINESS_OK`<br>J'ai vérifié : les informations de la commande sont correctes | **Condition :** Périmètre concerné comparé au document.<br>**Suite :** Enregistrer la vérification et orienter au support ; l'incident EDI reste ouvert tant que le fichier est incorrect. |
| `UX-21.UNRESOLVED`<br>Je n'ai pas pu vérifier les informations concernées | **Condition :** Motif et champs indiqués.<br>**Suite :** Attente ; ne pas modifier une bonne donnée pour la faire correspondre à un mauvais fichier. |



### UX-22 - Transmission à reprendre

**Message proposé :** La transmission n'a pas abouti ou son résultat doit être vérifié.

Distinguer échec certain et résultat incertain. Afficher le canal, la dernière tentative et la preuve disponible. Le rôle de chaque canal reste AR-12.

*Origine des situations : [S1], Affichages L37, L38. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-22.REVIEW`<br>J'ai vérifié le dossier et les informations à transmettre | **Condition :** Revue enregistrée sur la version courante.<br>**Suite :** Ne pas marquer l'envoi réussi ; proposer la commande technique "Relancer la transmission" uniquement si autorisée et sûre. |
| `UX-22.REPORTED`<br>J'ai signalé l'incident à l'équipe concernée | **Condition :** Signalement réel et destinataire / référence renseignés.<br>**Suite :** Attente d'intervention ; conserver l'échec et le droit de reprise approprié. |
| `UX-22.UNKNOWN`<br>Je n'ai pas pu confirmer si la commande a été reçue | **Condition :** Preuve de réception absente ou incertaine.<br>**Suite :** Réconciliation avant relance ; pas de nouvel envoi aveugle. |



### UX-23 - Données de référence indisponibles

**Message proposé :** Les données de référence nécessaires ne sont pas disponibles.

Distinguer référentiel absent / vide et structure invalide. Les recherches non exécutables ne doivent pas conclure que les clients ou articles n'existent pas.

*Origine des situations : [S1], Affichages L39, L40. Libellés et parcours : propositions P.*
| Confirmation / identifiant proposé | Condition et traitement attendu |
|---|---|
| `UX-23.REPORTED`<br>J'ai signalé le problème de données de référence | **Condition :** Signalement réel, responsable et motif enregistrés.<br>**Suite :** Conserver le dossier en attente technique ; ne pas demander à l'ADV de corriger un schéma. |
| `UX-23.READY`<br>J'ai été informé que les données ont été mises à jour | **Condition :** Information de reprise reçue ; référence de mise à jour si disponible.<br>**Suite :** Le système vérifie lui-même disponibilité et structure avant de relancer les contrôles ; le clic ne prouve pas la réparation. |
| `UX-23.UNRESOLVED`<br>Je n'ai pas pu obtenir la correction du référentiel | **Condition :** Motif et prochain responsable renseignés.<br>**Suite :** Maintenir l'attente technique ; ne pas clôturer la commande comme traitée. |



<!-- PAGE -->
## Annexe A. Correspondance des codes - partie 1

Cette projection couvre tous les codes d'Affichages. Les contraintes source ne sont pas supprimées par la fusion des cartes. Les alias sont importés de Règles colonne B ; la liste canonique de référence est conservée.

| Code existant | Situation cible | Source et précision |
|---|---|---|
| `NOT_A_PDF` | UX-01 | Affichages L3 ; Règles L6 |
| `PDF_PARSE_FAILURE` | UX-01 | Affichages L4 ; Règles L3 |
| `CONTRACT_KEYWORD` | UX-02 | Affichages L5 ; Règles L16 |
| `NOT_AN_ORDER` | UX-02 | Affichages L6 ; Règles L36 |
| `ORDER_CHANGE` | UX-03 | Affichages L7 ; Règles L10 |
| `EXTRACTION_LLM_SALVAGE` | UX-04 | Affichages L8 ; Règles L4 |
| `NO_DELIVERY_ADDRESS` | UX-05 | Affichages L9 ; Règles L33 |
| `SHIPTO_AMBIGUOUS_MATCH` | UX-06 | Affichages L10 ; Règles L21 |
| `SHIPTO_CANDIDATES_MISSING` | UX-06 | Affichages L11 ; Règles L19 |
| `SHIPTO_NO_STRONG_MATCH` | UX-06 | Affichages L12 ; Règles L20 |
| `SHIPTO_SOLDTO_MISMATCH` | UX-08 | Affichages L13 ; Règles L22 |
| `SOLDTO_AMBIGUOUS_MATCH` | UX-07 | Affichages L14 ; Règles L18 |
| `SOLDTO_NOT_FOUND` | UX-07 | Affichages L15 ; Règles L17 |
| `PARTNER_UNRESOLVED` | UX-09 | Affichages L16 ; synthèse, pas de double tâche ; Règles L5 |
| `DUPLICATE_ALREADY_SENT` | UX-11 | Affichages L17 ; Règles L32 |
| `PO_NUMBER_DUPLICATE` | UX-10 | Affichages L18 ; Règles L35 |
| `RESUBMISSION_DETECTED` | UX-12 | Affichages L19 ; information, pas d’acquittement obligatoire ; Règles L14 |
| `ARTICLE_NOT_FOUND` | UX-13 | Affichages L20 ; Règles L34 |
| `ARTICLE_QUANTITY_INVALID` | UX-16 | Affichages L21 ; Règles L28 |
| `MATERIAL_STATUS_INVALID` | UX-14 | Affichages L22 ; Règles L13 |

<!-- PAGE -->
## Annexe A. Correspondance des codes - partie 2

| Code existant | Situation cible | Source et précision |
|---|---|---|
| `NO_LINE_ITEMS` | UX-15 | Affichages L23 ; Règles L37 |
| `NO_VALID_ARTICLE` | UX-13 | Affichages L24 ; condition agrégée à clarifier ; Règles L15 |
| `QUANTITY_MISSING` | UX-16 | Affichages L25 ; Règles L38 |
| `UNIT_PRICE_MISSING` | UX-17 | Affichages L26 ; Règles L29 |
| `ORDER_DATE_INVALID` | UX-19 | Affichages L27 ; Règles L8 |
| `ORDER_KEY_MISSING` | UX-18 | Affichages L28 ; Règles L7 |
| `DELIVERY_DATE_INVALID` | UX-20 | Affichages L29 ; Règles L9 |
| `EDIFACT_LINE_INTEGRITY_MISMATCH` | UX-21 | Affichages L30 ; correction source si cause prouvée, sinon incident ; Règles L30 |
| `EDIFACT_MISSING_BGM` | UX-21 | Affichages L31 ; correction source si cause prouvée, sinon incident ; Règles L23 |
| `EDIFACT_MISSING_DTM_137` | UX-21 | Affichages L32 ; correction source si cause prouvée, sinon incident ; Règles L24 |
| `EDIFACT_MISSING_LIN` | UX-21 | Affichages L33 ; correction source si cause prouvée, sinon incident ; Règles L27 |
| `EDIFACT_MISSING_NAD_BY` | UX-21 | Affichages L34 ; correction source si cause prouvée, sinon incident ; Règles L25 |
| `EDIFACT_MISSING_NAD_DP` | UX-21 | Affichages L35 ; correction source si cause prouvée, sinon incident ; Règles L26 |
| `EDIFACT_NAD_DP_MISMATCH` | UX-21 | Affichages L36 ; correction source si cause prouvée, sinon incident ; Règles L31 |
| `DELIVERY_EMAIL_FAILED` | UX-22 | Affichages L37 ; Règles L40 |
| `DELIVERY_SFTP_FAILED` | UX-22 | Affichages L38 ; Règles L39 |
| `MASTERDATA_MISSING` | UX-23 | Affichages L39 ; Règles L11 |
| `MASTERDATA_SCHEMA_INVALID` | UX-23 | Affichages L40 ; Règles L12 |

Les sept diagnostics EDI restent conservés. UX-21 peut orienter vers UX-18 pour une référence absente, UX-19 pour une date document, UX-07 pour l'acheteur, UX-05 / UX-06 / UX-08 pour la livraison et UX-13 à UX-17 pour les lignes, **uniquement lorsque cette cause est prouvée**. Sinon, ne pas inventer une correction source.

SOLDTO_CONFIDENCE_MIN et SHIPTO_CONFIDENCE_MIN sont documentés comme critères non canoniques. Les valeurs de seuil, l'algorithme de score et les unités ne sont pas fixés par ce document. [S1, Règles L41-L42]

<!-- PAGE -->
## Annexe B. Arbitrages à obtenir - partie 1

Pour chaque AR : consigner la question, l'existant prouvé, les options, la décision du responsable, les RM / UX affectés, les tests et le jalon d'activation. Une option proposée par l'agent n'est pas une approbation.

### AR-01 - Effacement de l'en-tête

Lister chaque champ vidé après changement du Sold-to sans Ship-to unique. Confirmer le maintien du Sold-to choisi, le sort du numéro de commande, des dates, de la TVA et de l'adresse documentaire.

**Pilote proposé :** Métier + responsable technique. **Jalon :** Avant modification des automatismes.

### AR-02 - Propagation et relations multiples

Distinguer choix manuel et remplissage dérivé. Décider comment finaliser un couple lorsque chaque partenaire a plusieurs rattachements : sélection conjointe, conservation d'un choix compatible ou autre règle.

**Pilote proposé :** Métier + responsable technique. **Jalon :** Avant modification des automatismes.

### AR-03 - Périmètre de l'unicité

Définir les rattachements admissibles : contexte commercial, validité, statut, référentiel complet, filtres et dédoublonnage. Dire si l'unicité se mesure avant ou après filtrage TVA.

**Pilote proposé :** Métier + référentiels. **Jalon :** Avant recherche et remplissage.

### AR-04 - Usage de la TVA

Définir le numéro à retenir, son origine, le filtre strict ou indicatif, le traitement de l'absence et d'une contradiction, et le droit d'élargir la recherche.

**Pilote proposé :** Métier + référentiels. **Jalon :** Avant recherche filtrée.

### AR-05 - Adresse documentaire et adresse transmise

Préciser quelle adresse est corrigée dans chaque champ, la source de l'adresse EDI et l'autorisation éventuelle d'une dérogation locale. Ne pas confondre correction de commande et modification du référentiel.

**Pilote proposé :** Métier + intégration SAP. **Jalon :** Avant modification adresse / EDI.

### AR-06 - Validité des champs

Documenter quantités, décimales, unités, prix nuls, devise, numéros et dates, ainsi que l'héritage des dates entre en-tête et lignes. Aucun seuil supplémentaire n'est fixé ici.

**Pilote proposé :** Métier. **Jalon :** Avant nouveaux contrôles.

### AR-07 - Lignes partielles et substitutions

Définir les exclusions et substitutions autorisées, leurs approbateurs, leurs motifs et l'information du client.

**Pilote proposé :** Métier + responsable ADV. **Jalon :** Avant activation de ces issues.

### AR-08 - Doublons et réémission

Définir l'identité métier du doublon, les preuves d'une commande distincte, les droits de dérogation et la procédure de réémission exceptionnelle.

**Pilote proposé :** Métier + intégration SAP. **Jalon :** Avant toute dérogation d'envoi.


<!-- PAGE -->
## Annexe B. Arbitrages à obtenir - partie 2

### AR-09 - Vraie modification de commande

Définir le processus d'une modification réelle : circuit distinct, traitement hors outil ou fonctionnalité dédiée.

**Pilote proposé :** Métier + intégration SAP. **Jalon :** Avant conversion ou transmission.

### AR-10 - Droits et interventions référentiel

Attribuer sélection locale, modification du référentiel, transfert, clôture, relance et validation exceptionnelle.

**Pilote proposé :** Responsable ADV + référentiels + technique. **Jalon :** Avant ouverture aux utilisateurs.

### AR-11 - Retraitement et remplacement du PDF

Définir la conservation, la comparaison ou l'abandon des corrections manuelles lors d'une nouvelle extraction ou d'un nouveau document.

**Pilote proposé :** Métier + technique. **Jalon :** Avant reprise destructive.

### AR-12 - Canaux et preuve SAP

Définir le rôle obligatoire ou informatif de SFTP / email, les preuves de réception, le retour SAP disponible et le traitement d'un résultat d'envoi incertain.

**Pilote proposé :** Intégration SAP + exploitation. **Jalon :** Avant automatisation des reprises.

### AR-13 - Statuts et autorisation d'envoi

Valider les états cible et leur correspondance avec REJECTED, PENDING_USER_INPUT, DUPLICATE et DELIVERY_FAILED ; préciser les blocages par opération.

**Pilote proposé :** Métier + technique. **Jalon :** Avant migration des statuts.

### AR-14 - Périmètre des confirmations

Valider les confirmations par champ, ligne ou bloc, les dépendances à rejouer et les conditions d'expiration après correction ou changement du référentiel.

**Pilote proposé :** Métier + qualité + technique. **Jalon :** Avant nouvelle revue.

### AR-15 - Traçabilité et conservation

Définir les durées, les accès aux documents / journaux, les informations de preuve et les modalités d'export.

**Pilote proposé :** Responsable projet + sécurité. **Jalon :** Avant mise en production.

### AR-16 - Cas non explicitement catalogués

Décider du traitement d'une extraction partielle, d'une ligne extraite deux fois, de plusieurs commandes dans un PDF et d'une ambiguïté article.

**Pilote proposé :** Métier + qualité. **Jalon :** Avant nouveaux diagnostics.


<!-- PAGE -->
## Annexe C. Sources et consigne de démarrage

**[U1] Finalité et responsabilité ADV.** Messages du porteur du projet : dépôt, extraction, traitement métier, EDI, envoi ; outil de préremplissage ; vérification et correction par l'ADV avant envoi.

**[U2] Affichage et confirmations.** Messages du porteur du projet : préférence pour "J'ai corrigé la quantité" ; sortie du couple accepter / refuser ; plusieurs issues contextuelles ; masquage des distinctions techniques inutiles. Les exemples de boutons ne sont pas des libellés imposés.

**[U3] Identification des partenaires.** Message accompagnant les captures : adresse de livraison prioritaire, Ship-to puis Sold-to ; TVA secondaire pour réduire le domaine de recherche ; correction directe à côté du PDF.

**[U4] Dépendances entre partenaires.** Dernier message métier : Sold-to changé et Ship-to unique = remplissage du Ship-to, de son adresse et autres données ; sinon "tout se vide dans l'en-tête". Ship-to renseigné = adresse / autres données remplies et Sold-to unique renseigné, sinon Sold-to vide.

**[S1] Catalogue transmis.** validation_rules_inventory_updated.xlsx, onglets Affichages, Règles, Incohérences, Synthèse. Les références L indiquent les lignes physiques Excel.

**[S2] Captures de l'espace de travail.** 466be915-7aae-4a1b-80ed-c5500ffd10e7.png : en-tête et partenaires ; 026e5fa8-7cf8-4196-8c01-aeada2583398.png : PDF et lignes ; 30bd4f51-91b7-4a57-84f2-1c3f041dc3d5.png : anomalies, traçabilité et actions.

Les règles produits FAB-DIS et les Notes de Mission BI ne sont pas incorporées à ce contrat de revue des commandes. Elles ne suffisent pas à fixer les règles de vente, de rattachement ou d'envoi de cette application.

### Consigne à utiliser avec le dépôt

"Analyse le dépôt et le catalogue de validations à la lumière de ce contrat. Commence par une cartographie des comportements existants et des écarts RM / UX / AR. Montre les automatismes Sold-to / Ship-to, leurs effets sur l'en-tête et leurs tests. Présente les arbitrages bloquants sans les inventer. Propose ensuite un plan de modifications incrémentales, conserve les codes et les preuves historiques, implémente les éléments autorisés, exécute les tests disponibles et livre les preuves. N'effectue aucun envoi réel vers SAP sans autorisation explicite."

### Définition de terminé pour le lot livré

Toutes les règles du lot ont une correspondance avec le code et les tests ; les AR dont il dépend sont approuvés ou les fonctionnalités correspondantes restent non activées ; les confirmations ne contournent pas les validations ; les modifications automatiques sont expliquées ; aucune transmission d'une ancienne version ou d'un doublon non autorisé n'est rendue possible ; la migration et les limites restantes sont documentées.
