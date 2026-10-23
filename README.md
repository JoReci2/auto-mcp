# yamcps — Yet Another Model Context Protocole Server

**yamcps** est un serveur MCP Python extensible qui expose les fonctionnalités de
connecteurs à des assistants compatibles avec le Model Context Protocol.
Python 3.12 ou supérieur est requis.

## Fonctionnalités

- Connecteurs indépendants distribuables sur PyPI sous le nom `yamcps-<nom>`.
- Outils, ressources et prompts MCP fournis par les connecteurs.
- Skills `SKILL.md` et fichiers associés consultables via MCP.
- Configuration non secrète des plugins en JSON local, avec `yamcps configs set`.
- Coffre local chiffré et configuration interactive des secrets requis par les connecteurs.
- Transports stdio et Streamable HTTP local.
- Plugins `yamcps-demo` et `yamcps-demo-secrets` pour tester les outils et la configuration des secrets.

## Démarrage depuis le dépôt

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install yamcps
yamcps connectors list
yamcps serve                  # Charge tous les connecteurs installé
```

Pour sélectionner plusieurs connecteurs dédié:
`yamcps serve --connector demo --connector demo-secrets`.

Pour HTTP : `yamcps serve --transport http --port 8000`.
Le serveur écoute sur `http://127.0.0.1:8000/mcp`.

## Documentation

- [Manuel utilisateur](docs/user-manual.md) : installation, clients et utilisation.
- [Architecture](docs/design.md) : contrats des connecteurs et gestion des skills.
- [Contribution](contributing.md) : conventions, tests et contrôles qualité.
- [Consignes pour les agents](AGENTS.md) : règles de travail dans le dépôt.

## Dépôts des plugins

| Plugins | Dépôt |
| --- | --- |
| Documents / RAG métier | [yamcps-docs](https://github.com/JoReci2/yamcps-docs) |
| Sonarr, Radarr et Prowlarr | [yamcps-arr](https://github.com/JoReci2/yamcps-arr) |
| Skills de développement | [yamcps-extras](https://github.com/JoReci2/yamcps-extras) |

Le moteur conserve `yamcps.rag` et les deux plugins de démonstration. Voir
[le guide de migration et d’installation](docs/plugins.md).