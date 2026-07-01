# Databricks

Cette partie explique comment utiliser le meme moteur que Docker dans Databricks.

## Principe

| Composant | Source | Mise a jour |
|-----------|--------|-------------|
| Code Python `app/`, `config/`, notebooks | Repo Git Bosch DevCloud | `git push`, puis `Pull` dans Databricks Repos |
| Masterdata SAP | DBFS assets | `scripts/sync_databricks_assets.ps1` |
| Referentiel postal France | DBFS assets | `scripts/download_postal_reference.ps1`, puis sync |
| Modele MiniLM embeddings | DBFS assets | `scripts/sync_databricks_assets.ps1` |
| PDF samples | DBFS assets | `scripts/sync_databricks_assets.ps1` |

Le moteur principal reste :

```python
from app.engine import get_engine

engine = get_engine()
```

## Setup initial

Depuis le poste local :

```powershell
cd C:\Users\DIK1DY\Desktop\projet\locateanything-local
.\scripts\download_postal_reference.ps1
.\scripts\sync_databricks_assets.ps1
```

Le script envoie les assets vers :

```text
dbfs:/FileStore/users/dik1dy/locateanything
```

Ensuite, dans Databricks Repos :

1. Ouvrir le repo `findshiptoboschengine`.
2. Pull la derniere version.
3. Ouvrir `databricks/notebooks/00_setup.py`.
4. Lancer le notebook.

## Notebooks

| Notebook | Role |
|----------|------|
| `00_setup.py` | Installe les dependances et verifie le runtime |
| `01_extract_pdf.py` | Teste l'extraction d'un PDF |

## Verification runtime

Dans Databricks :

```python
from app.engine import get_engine

engine = get_engine()
engine.health()
```

Points attendus :

```python
{
  "runtime": "databricks",
  "master_data_loaded": True,
  "postal_reference_loaded": True,
  "embeddings_available": True
}
```

## Variables runtime

`app.runtime.configure_runtime()` configure automatiquement les chemins.

| Variable | Docker | Databricks |
|----------|--------|------------|
| `LOCATEANYTHING_PROJECT_ROOT` | `/app` | Repo Databricks |
| `LOCATEANYTHING_ASSETS_DIR` | `/app` ou `/data` selon usage | `/dbfs/FileStore/users/dik1dy/locateanything` |
| `MASTER_DATA_DIR` | `/data/masterdata` | `{assets}/data/masterdata` |
| `POSTAL_REFERENCE_PATH` | `/data/reference/fr_communes.json` | `{assets}/data/reference/fr_communes.json` |
| `EMBEDDING_MODEL_DIR` | `/app/all-MiniLM-L6-v2` | `{assets}/all-MiniLM-L6-v2` |

## Extraction PDF

```python
from app.engine import get_engine

engine = get_engine()

pdf_path = "/dbfs/FileStore/users/dik1dy/locateanything/samples/psp571536_prolians.pdf"
with open(pdf_path, "rb") as handle:
    payload = handle.read()

response = engine.extract_pdf(
    payload,
    filename="psp571536_prolians.pdf",
    pages="1",
    instruction="Extraire bon de commande B2B",
    include_debug=True,
)

structured = response["results"][0]["fields"]["structured"]
detected = structured["adresses"]["Adresse de livraison detectee"]
validated = structured["adresses"]["Adresse de livraison validee"]
line_items = structured["line_items"]

display(detected)
display(validated)
display(line_items)
```

## Engines specialises

Pour tester une brique seule :

```python
from app.engines import DeliveryAddressEngine, ShipToMatchingEngine, OrderLinesEngine
```

Exemple detection adresse :

```python
delivery = DeliveryAddressEngine().detect(text, filename="commande.pdf", layout=layout)
display(delivery["address"])
display(delivery["layout_analysis"]["candidate_summaries"])
```

## Workflow quotidien

```text
Modifier le code local
  -> git add / commit / push
  -> Databricks Repos : Pull
  -> Run notebook
```

Les assets DBFS ne doivent etre resynchronises que si :

- masterdata change ;
- referentiel postal est regenere ;
- modele MiniLM change ;
- nouveaux PDF samples a envoyer.

## Depannage

### `master_data_loaded = False`

Relancer depuis le poste local :

```powershell
.\scripts\sync_databricks_assets.ps1
```

### `postal_reference_loaded = False`

Relancer :

```powershell
.\scripts\download_postal_reference.ps1
.\scripts\sync_databricks_assets.ps1
```

### `embeddings_available = False`

Verifier que le dossier suivant existe dans DBFS :

```text
dbfs:/FileStore/users/dik1dy/locateanything/all-MiniLM-L6-v2
```

Puis relancer `sync_databricks_assets.ps1` si besoin.
