# yamcps-docs

Plugin documentaire local, lecture seule en MCP. TXT/Markdown UTF-8 de base ;
PDF texte et DOCX avec l'extra `formats`. Pas d'OCR, extraction de figures ni
reconstruction de la mise en page. Les citations utilisent les offsets de caractères
(start inclus, end exclu) du texte extrait ; pas de pagination garantie.

Depuis la racine du dépôt :

```sh
python -m pip install -e . -e packages/yamcps-rag-core -e 'plugins/yamcps-docs[formats]'
export YAMCPS_DOCS_INDEX="$HOME/.local/share/yamcps/docs.sqlite3"
yamcps-docs ingest /chemin/vers/manifest.json
yamcps serve --connector docs
```

Essai immédiat avec le corpus fictif fourni :

```sh
yamcps-docs ingest plugins/yamcps-docs/examples/manifest.json
```

Puis demander au client de rechercher `SSS-REQ-0042` dans `demo/specifications`.

Exemple `manifest.json`, placé à côté de `SSS.md` :

```json
{
  "corpus": "project-a/specifications",
  "sources": [
    {
      "path": "SSS.md",
      "document_id": "SSS",
      "revision": "1.2",
      "metadata": {"baseline": "v1", "status": "approved", "type": "SSS"}
    }
  ]
}
```

Le manifeste est un **snapshot complet** : retirer une source supprime cette
révision de l'index. Garder explicitement les anciennes révisions souhaitées.
L'extraction est terminée avant toute synchronisation. Les chemins absolus,
traversées `..` et symlinks sont refusés. Limites par source : 20 MiB et
4 millions de caractères extraits. N'ingérer que des fichiers de confiance.
Les contenus sont stockés en clair dans SQLite : protéger le dossier avec les
droits du système et sauvegarder l'index si nécessaire.

Le découpage V1 utilise au plus 1200 caractères par passage, sans chevauchement
(`--chunk-size`, 64 à 16000). Il peut couper une phrase ou un tableau.
Une deuxième ingestion identique réutilise les passages. Pas d'indexation au
chargement du plugin, ni de mutation exposée au modèle.

## Outils

- `docs_search(query, corpus, filters=None, limit=5)` : passages sourcés, limite 1–20.
- `docs_get_document(corpus, document_id, revision)` : texte extrait d'une version.
- `docs_get_passage(passage_id)` : passage et référence exacte.
- `docs_index_status(corpus)` : compteurs, mode et date du dernier passage modifié
  (ce n'est pas une preuve de fraîcheur de la source).

Ressources : `docs://source/{corpus}/{document_id}/{revision}` (segments encodés)
et `docs://passage/{passage_id}`. Skill embarqué `docs-research`.
Les filtres portent sur les métadonnées, pas sur des droits d'accès.
Un index absent produit une erreur explicative lors du premier appel, sans
empêcher les autres plugins de démarrer.

## Recherche sémantique locale optionnelle

```sh
python -m pip install -e 'packages/yamcps-rag-core[semantic]'
export YAMCPS_DOCS_MODEL=/chemin/absolu/vers/modele-local
export YAMCPS_DOCS_INDEX="$HOME/.local/share/yamcps/docs-hybrid.sqlite3"
yamcps-docs ingest /chemin/vers/manifest.json
yamcps serve --connector docs
```

Utiliser le même modèle pour ingestion et recherche. Il est chargé au premier
appel MCP, dans un thread, jamais à l'import ou à l'enregistrement. Aucun modèle
n'est fourni ni téléchargé. Pas de code distant autorisé. Sans modèle, le mode
est lexical et ne comprend pas les synonymes. La qualité d'un modèle réel doit
être évaluée sur vos questions métier ; aucune qualification IVVQ n'est revendiquée.
