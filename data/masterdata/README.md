# Données maîtres (non versionnées dans ce repo app)

Placez ici les exports Databricks (préféré : **Parquet**) ou CSV `;` UTF-8 :

| Fichier Parquet (recommandé) | CSV legacy | Description |
|------------------------------|------------|-------------|
| `10564_Customers.parquet` | `10564_Customers.csv` | Sold-to |
| `10564_Partners.parquet` | `10564_Partners.csv` | Ship-to |
| `10564_Materials.parquet` | `10564_Materials.csv` | Articles Bosch |
| `DB_Salesorder.parquet` | `DB_Salesorder.csv` | Historique commandes |

Colonnes minimales inchangées. L’API `/api/masterdata/import` et le cache acceptent Parquet et CSV.
