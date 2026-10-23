# yamcps — Yet Another Model Context Protocole Server

**yamcps** est un serveur MCP Python extensible qui expose les fonctionnalités de
connecteurs à des assistants compatibles avec le Model Context Protocol.
Python 3.12 ou supérieur est requis.

## Fonctionnalités

- Connecteurs indépendants : outils, ressources et prompts MCP.
- Skills et fichiers associés accessibles via MCP.
- Configuration locale en JSON et coffre chiffré avec saisie interactive des secrets.
- RAG facultatif : indexation et recherche lexicale ou sémantique locale.
- Transports stdio et Streamable HTTP local.

## Quicktart

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install yamcps
```

Exemple de configuration pour un client acceptant `mcpServers` via `stdio`:

```json
{
  "mcpServers": {
    "yamcps": {
      "command": "/chemin/absolu/vers/.venv/bin/yamcps",
      "args": ["serve"]
    }
  }
}
```

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
