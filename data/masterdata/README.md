# Données maîtres (non versionnées)

Les fichiers CSV volumineux ne sont pas dans Git. Placez-les ici avant le premier lancement :

| Fichier | Description |
|---------|-------------|
| `10564_Customers.csv` | Sold-to |
| `10564_Partners.csv` | Ship-to |
| `10564_Materials.csv` | Articles Bosch |
| `DB_Salesorder.csv` | Historique commandes (référence) |

Au démarrage, `server.py` tente de les charger depuis ce dossier ou de les synchroniser si configuré (voir `.env.example`).
