# yamcps — Yet Another Model Context Protocole Server

**yamcps** est un serveur MCP Python extensible qui expose les fonctionnalités de
connecteurs à des assistants compatibles avec le Model Context Protocol.
Python 3.12 ou supérieur est requis.

## Fonctionnalités

- Connecteurs indépendants distribuables sur PyPI sous le nom `yamcps-<nom>`.
- Chargement de tous les plugins installés par défaut, ou sélection avec `--connector`.
- Outils, ressources et prompts MCP fournis par les connecteurs.
- Plugins `yamcps-sonarr` et `yamcps-radarr` : bibliothèques de séries/films, calendriers,
  téléchargements, recherche et ajout.
- Plugin `yamcps-prowlarr` : indexeurs, recherche de releases et diagnostics en lecture seule.
- Skills `SKILL.md` et fichiers associés consultables via MCP.
- Coffre local chiffré et configuration interactive des secrets requis par les connecteurs.
- Transports stdio et Streamable HTTP local.
- Plugins `yamcps-demo` et `yamcps-demo-secrets` pour tester les outils et la configuration des secrets.

## Démarrage depuis le dépôt

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e . -e plugins/yamcps-demo
yamcps connectors list
yamcps serve --connector demo
```

Pour charger tous les plugins installés : `yamcps serve`. Pour en sélectionner plusieurs :
`yamcps serve --connector demo --connector demo-secrets`.

Pour HTTP : `yamcps serve --connector demo --transport http --port 8000`.
Le serveur écoute sur `http://127.0.0.1:8000/mcp`.

## Documentation

- [Manuel utilisateur](docs/user-manual.md) : installation, clients et utilisation.
- [Architecture](docs/design.md) : contrats des connecteurs et gestion des skills.
- [Contribution](contributing.md) : conventions, tests et contrôles qualité.
- [Consignes pour les agents](AGENTS.md) : règles de travail dans le dépôt.

Le nom PyPI `yamcps` est réservé pour ce projet. Seule la distribution de base
est publiée par le [workflow de release](.github/workflows/workflow.yaml).
Les plugins restent installables depuis le dépôt. Voir le guide de contribution
pour configurer Trusted Publishing et publier une version.
