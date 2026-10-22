# hmcp — Home MCP

**hmcp** est un serveur MCP Python extensible qui expose les fonctionnalités de
connecteurs à des assistants compatibles avec le Model Context Protocol.
Python 3.12 ou supérieur est requis.

## Fonctionnalités

- Connecteurs indépendants distribuables sur PyPI sous le nom `hmcp-<nom>`.
- Chargement de tous les plugins installés par défaut, ou sélection avec `--connector`.
- Outils, ressources et prompts MCP fournis par les connecteurs.
- Plugins `hmcp-sonarr` et `hmcp-radarr` : bibliothèques de séries/films, calendriers,
  téléchargements, recherche et ajout.
- Plugin `hmcp-prowlarr` : indexeurs, recherche de releases et diagnostics en lecture seule.
- Plugin `hmcp-docs` : corpus documentaires locaux, citations et recherche lexicale
  ou hybride avec un modèle local optionnel ; bibliothèque partagée `hmcp-rag-core`.
- Skills `SKILL.md` et fichiers associés consultables via MCP.
- Coffre local chiffré et configuration interactive des secrets requis par les connecteurs.
- Transports stdio et Streamable HTTP local.
- Plugins `hmcp-demo` et `hmcp-demo-secrets` pour tester les outils et la configuration des secrets.

## Démarrage depuis le dépôt

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e . -e plugins/hmcp-demo
hmcp connectors list
hmcp serve --connector demo
```

Pour charger tous les plugins installés : `hmcp serve`. Pour en sélectionner plusieurs :
`hmcp serve --connector demo --connector demo-secrets`.

Pour HTTP : `hmcp serve --connector demo --transport http --port 8000`.
Le serveur écoute sur `http://127.0.0.1:8000/mcp`.

## Documentation

- [Manuel utilisateur](docs/user-manual.md) : installation, clients et utilisation.
- [Architecture](docs/design.md) : contrats des connecteurs et gestion des skills.
- [Contribution](contributing.md) : conventions, tests et contrôles qualité.
- [Consignes pour les agents](AGENTS.md) : règles de travail dans le dépôt.

Les packages de ce dépôt ne sont pas encore publiés. Le nom `hmcp` existe déjà
sur PyPI ; les conditions de publication sont décrites dans le guide de contribution.
