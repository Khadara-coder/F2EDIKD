-- =============================================================================
-- Databricks SQL Script: Création de la vue 10564_Partners dans la couche Bronze
-- Catalogue : hcdap_prod
-- Schéma    : bronze_hcfrdashlog
-- Objet     : hcdap_prod.bronze_hcfrdashlog.v_10564_partners
-- =============================================================================

CREATE OR REPLACE VIEW hcdap_prod.bronze_hcfrdashlog.v_10564_partners AS
SELECT DISTINCT
    -- 1. Identifiants Partenaires SAP
    TRIM(knvp.KUNNR)                      AS `SOLDTO`,
    TRIM(knvp.KUNN2)                      AS `SHIPTO`,
    
    -- 2. Données géographiques de livraison (jointure KNA1 sur SHIPTO)
    COALESCE(TRIM(kna1.LAND1), 'FR')      AS `LAND1`,
    TRIM(kna1.NAME1)                      AS `NAME`,
    TRIM(kna1.ORT01)                      AS `ORT01`,
    TRIM(kna1.PSTLZ)                      AS `PSTLZ`,
    TRIM(kna1.STRAS)                      AS `STRAS`,
    
    -- 3. Rôle Partenaire (Constante 'SH' pour Ship-To / Warenempfänger)
    'SH'                                  AS `PARVW`,
    
    -- 4. Informations Gestionnaire ADV (jointure Annuaire RH sur PERNR)
    TRIM(knvp.PERNR)                      AS `Fonction-Partenaire`,
    UPPER(TRIM(hr.display_name))          AS `Gestionaire-ADV`,
    UPPER(TRIM(hr.email))                 AS `Email-I.D`,
    UPPER(TRIM(hr.nt_user_id))            AS `User-I.D`,
    TRIM(hr.person_number)                AS `numero-personne`

FROM 
    hcdap_prod.bronze_hcfrdashlog.sap_knvp knvp

-- Jointure A : Récupérer l'adresse du site de livraison (KNA1 sur SHIPTO)
INNER JOIN 
    hcdap_prod.bronze_hcfrdashlog.sap_kna1 kna1
    ON TRIM(knvp.KUNN2) = TRIM(kna1.KUNNR)

-- Jointure B : Récupérer l'identité de l'ADV responsable via le matricule PERNR
LEFT JOIN 
    hcdap_prod.bronze_hcfrdashlog.hr_employees hr
    ON TRIM(knvp.PERNR) = TRIM(hr.pernr)

WHERE 
    knvp.VKORG = '10564'                  -- Périmètre France (Organisation 10564)
    AND TRIM(knvp.PARVW) = 'SH'           -- Ship-To uniquement
    AND knvp.KUNNR IS NOT NULL 
    AND knvp.KUNN2 IS NOT NULL;

-- octroyer les droits de lecture au groupe / principal si nécessaire
-- GRANT SELECT ON VIEW hcdap_prod.bronze_hcfrdashlog.v_10564_partners TO `account users`;
