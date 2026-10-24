# yamcps-demo-rag

Connecteur autonome de démonstration du contrat RAG extensible de yamcps.
Il fournit sa factory de backend dans son propre package et utilise le backend
SQLite lexical du moteur. Aucun modèle, accès réseau ou secret n’est nécessaire.

Depuis la racine du dépôt yamcps :

```sh
python -m pip install -e . -e plugins/yamcps-demo-rag
yamcps serve --connector demo-rag
```

Dans un client MCP :

1. Appeler `demo_rag_ingest` pour indexer deux documents fictifs sur une bibliothèque :
   ses horaires d’ouverture et les modalités d’emprunt des livres.
2. Appeler `demo_rag_search` avec `{"query": "horaires"}`.
3. Lire l’URI `demo-rag://source/examples/horaires-bibliotheque/1` retournée dans les résultats.

Le démarrage ne crée aucun index. L’ingestion remplace explicitement le corpus
`examples` complet ; elle ne lit aucun fichier utilisateur. La base par défaut est
`~/.local/share/yamcps/rag/demo-rag.sqlite3`, ou sous `YAMCPS_RAG_DIR` si défini.
Les traitements bloquants sont exécutés dans des threads.

`create_index(path)` illustre le point d’extension : un autre plugin peut retourner
sa propre implémentation de `RetrievalIndex` sans modifier le chargeur ni le moteur.
La démo réutilise volontairement SQLite ; elle n’implémente pas de moteur alternatif.
Le backend est partagé entre les handlers du connecteur : toute implémentation
personnalisée doit supporter leurs appels concurrents. Le contrat actuel vise les
backends synchrones sans ressource persistante à fermer ; un backend réseau peut
ouvrir et fermer ses ressources à chaque opération.
