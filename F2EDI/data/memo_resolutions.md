# FILE2EDI — Memo de résolutions
> Maintenu par LLM | Utilisé comme fallback dans le pipeline de scoring SHIPTO
> Dernière MAJ: 2025-01-15 | Cas mémorisés: 8

---

## 1. Clients non identifiables par TVA/SIREN

### WENDEL DISTRIBUTION
- **Signal**: Nom "WENDEL" dans le texte, pas de TVA/SIREN dans le PDF
- **Code interne**: "01853P" (code WENDEL, pas un code agence standard)
- **SOLDTO**: 15015709 (multi-agences, 11 SHIPTOs)
- **Résolution**: Identifier par nom + postal dans le texte
- **Mapping agences connues**:
  - 47250 SAMAZAN → SHIPTO 15017967 (Z.A.C. PARC ACTIVITE MARMANDE SUD)
  - 47200 MARMANDE → SHIPTO 15012664 (11 AVENUE FRANCOIS MITTERRAND)
  - 47550 BOE → SHIPTO 15017963 (ROUTE D'AUCH)
  - 33210 LANGON → SHIPTO 15017964 (ROUTE DE BAZAS)
  - 47300 BIAS → SHIPTO 15017965 (ROUTE DE BORDEAUX)
  - 33700 MERIGNAC → SHIPTO 15017966 (ESPACE MERISUD)
  - 31830 PLAISANCE-DU-TOUCH → SHIPTO 15017968 (2 BIS RUE SADI CARNOT)
  - 24100 BERGERAC → SHIPTO 15017969 (Z.A.E. DES SARDINES)
  - 33260 LA TESTE-DE-BUCH → SHIPTO 15019409 (520 AVENUE GUSTAVE EIFFEL)
  - 33370 YVRAC → SHIPTO 15021379 (4 ZONE ARTISANALE DU GRAND CHEMIN)
  - 47500 SAINT-VITE → SHIPTO 15021658 (120 AVENUE DE TOURNON)

---

## 2. Codes agence non-standards

### ISERBA / GAZ SERVICE RAPIDE — Cross-SOLDTO
- **Cas**: Commande émise par GAZ SERVICE RAPIDE (SOLDTO 15016199) mais livrée à une agence ISERBA
- **Signal**: Le code après "/" dans le N° de commande (ex: "CAC2401CFL00018 / NTE") est un code ISERBA, pas GAZ SERVICE
- **Piège**: Le code dans le CAC (ex: "CFL") appartient au SOLDTO courant → ne PAS l'utiliser aveuglément
- **Règle**: Si le postal du candidat AGENCY n'est PAS dans la section livraison du PDF → REJETER
- **Exemple résolu**:
  - PDF dit "78300 POISSY, 3 RUE DU PALATINAT" dans la section livraison
  - Code CFL → SHIPTO 15018209 (78700 CONFLANS) = FAUX
  - Code NTE → SHIPTO 15019875 (78300 POISSY) = mais sous SOLDTO 15015760 (ISERBA)
  - Le scoring post-validation détecte 78700 absent du PDF → rejeté correctement

### ISERBA — Codes agence connus (SOLDTO 15015760)
| Code | SHIPTO | Nom | Ville |
|------|--------|-----|-------|
| STQ | 15018063 | .ISERBA (STQ) | SAINT-QUENTIN-FALLAVIER |
| NTE | 15019875 | .ISERBA (NTE) | POISSY |
| HAU | 15020362 | .UNICIA (HAU) | OUDALLE |
| VMC | 15020371 | .ISERBA (VMC) | CHAMPIGNY-SUR-MARNE |
| HAR | 15900966 | .ISERBA (HAR) | OUDALLE |

### GAZ SERVICE RAPIDE — Codes agence (SOLDTO 15016199)
| Code | SHIPTO | Nom | Ville |
|------|--------|-----|-------|
| CFL | 15018209 | .GAZ SERVICE RAPIDE (CFL) | CONFLANS-SAINTE-HONORINE |

---

## 3. SHIPTOs dupliqués (même adresse physique)

### OUDALLE — 1 CHEMIN DES PLANS D'EAU, 76430
- SHIPTO 15020362 (.UNICIA HAU) et SHIPTO 15900966 (.ISERBA HAR)
- **Même bâtiment**, codes agence différents
- Priorité: utiliser le code agence pour départager (HAU vs HAR)

### CHAMPIGNY-SUR-MARNE — 1075 RUE MARCEL PAUL, 94500
- SHIPTO 15020371 et SHIPTO 15020372
- **Même adresse exacte**
- Prendre le premier (15020371) si pas d'autre signal

### SAINT-QUENTIN-FALLAVIER — 343 RUE DU MORELLON, 38070
- SHIPTO 15018063 (.ISERBA STQ) et SHIPTO 15021854
- Code agence STQ → 15018063

---

## 4. Scans / PDF-images (texte non extractible)

### Détection automatique
- Si pdfplumber extrait < 50 caractères sur la page 1 → c'est un scan
- Comportement attendu: appeler OCR externe (Tesseract / Azure Document Intelligence)
- Si OCR indisponible: REJECTED avec raison "SCAN_NO_OCR"

### Cas connus
- **SALICA ANCONETTI 670060413**: scan image, SOLDTO=15018938, 15 SHIPTOs possibles
  - Résolution manuelle nécessaire tant que l'OCR n'est pas branché

---

## 5. Mappings articles / références internes

### ANDRETY S.A.S. (SOLDTO 15015717 → SHIPTO 15018108 AVIGNON)
- Les PDFs ANDRETY contiennent des refs internes (colonne "Code art") + refs Bosch (ligne "V/réf:")
- **Pattern**: `V/réf: XXXXXXXXXXX` sur la ligne suivante = référence Bosch officielle
- Exemple:
  - Code art "1064479" → V/réf: 7733701566 (UI CL3000IU W 35 E)
  - Code art "1282373" → V/réf: 7733701997 (CLIMATE 3000IM)
  - Code art "1281966" → V/réf: 7733701806 (UI CL6000IU W 26 E)

### Règle générale
- Si la ligne article contient "V/réf:" ou "Réf fournisseur:" → extraire cette ref comme ref Bosch
- Si seul un code interne client est présent → chercher dans DB_Salesorder par historique

---

## 6. Formats de N° commande par client

| Client | Format PO | Exemple | Notes |
|--------|-----------|---------|-------|
| ISERBA/UNICIA | CACddddCODEddddd | CAC2402STQ00137 | Code agence dans le CAC |
| GAZ SERVICE | CACddddCODEddddd / CODE | CAC2401CFL00018 / NTE | Code réel après slash |
| WENDEL | CF + 6 chiffres | CF329290 | Pas de code agence |
| C.C.L | XX-XXXXXXXXXX | 04-9240202813 | Préfixe "04-" |
| ANDRETY | 7 chiffres | 0853058 | Simple numérique |
| SALICA | 9 chiffres | 670060413 | Simple numérique |

---

## 7. Problèmes OCR connus

### Apostrophes Unicode
- PDF contient U+2019 (RIGHT SINGLE QUOTATION MARK: ') 
- Masterdata contient ASCII 0x27 (APOSTROPHE: ')
- **Fix**: `_normalize_for_compare()` remplace U+2019 → ASCII avant comparaison
- Exemple: "1 CHEMIN DES PLANS D'EAU" vs "D'EAU" dans masterdata

### Colonnes mélangées (layout 2-colonnes)
- Certains PDFs ont "Facturé à" et "Livré à" en colonnes côte à côte
- pdfplumber mélange les colonnes → adresse de livraison non détectable
- **Workaround**: le scoring engine cherche le postal + ville individuellement dans tout le texte
- Le code agence (CAC) reste le signal le plus fiable dans ce cas

---

## 8. Règles métier spécifiques

### Confiance 100% requiert TOUTES ces conditions:
1. Adresse trouvée PROCHE des mots de livraison ("livrer à", "ship to", etc.)
2. Code postal ET commune vérifiés (concordance)
3. SHIPTO trouvé sans ambiguïté (1 seul candidat ou gap > 15pts)

### En cas de doute → LLM tranche (top 3 candidats max)
### Si LLM incertain → ERREUR avec raison (jamais de faux positif)
### SOLDTO ne peut JAMAIS être candidat SHIPTO dans le scoring

---

*Ce memo est lu par le pipeline comme contexte additionnel lors des résolutions ambiguës.*
*Il est mis à jour après chaque cas spécial détecté ou résolu manuellement.*
