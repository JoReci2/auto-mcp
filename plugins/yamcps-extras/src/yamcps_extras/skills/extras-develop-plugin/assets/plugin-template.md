# Squelette à adapter

Exemple pour `weather` ; remplacer les noms et adapter la compatibilité à la version
réellement ciblée. Aucun appel météo réel n'est implémenté ici.

`pyproject.toml` :

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "yamcps-weather"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["yamcps>=0.1,<0.2"]

[project.entry-points."yamcps.connectors"]
weather = "yamcps_weather:WeatherConnector"

[tool.hatch.build.targets.wheel]
packages = ["src/yamcps_weather"]
```

`src/yamcps_weather/__init__.py` :

```python
from mcp.server import MCPServer


class WeatherConnector:
    """Expose the local weather connector status."""

    id = "weather"

    def register(self, server: MCPServer) -> None:
        """Register MCP handlers.

        Args:
            server: Server receiving this connector's tools.
        """

        @server.tool()
        async def weather_status() -> str:
            """Report local readiness without contacting an external service."""
            return "ready"
```

Pour un plugin de skills uniquement, retirer le décorateur et le handler ; garder
`register` vide avec sa docstring et implémenter `skill_roots()` retournant les
chemins de dossiers `<id>-<action>` embarqués dans `src/yamcps_weather/skills/`.
Les annotations MCP doivent décrire les effets réels des outils ajoutés.

## Capacités optionnelles du moteur

Pour ajouter des paramètres non secrets, compléter la classe avec ces deux hooks
synchrones et les imports ; garder `register()` :

```python
from yamcps import ConfigSpec, ConnectorConfigs


def required_configs(self) -> list[ConfigSpec]:
    """Declare nonsecret settings managed by the core."""
    return [ConfigSpec("endpoint", "URL sans identifiants", default="http://localhost")]


def configure_configs(self, configs: ConnectorConfigs) -> None:
    """Retain resolved settings before handler registration."""
    self.endpoint = configs.require("endpoint")
```

Configurer avec `yamcps configs set --connector weather` : aucun export nécessaire.
Réserver `SecretSpec`, `ConnectorSecrets`, `required_secrets()` et `configure()`
aux secrets du vault. Ne pas écrire de credentials dans la configuration JSON.

Pour une recherche documentaire, ajouter les imports et méthodes suivants à la
classe, en conservant `register()` et en y exposant seulement les outils souhaités :

```python
from yamcps import RagConfig, RagContext


def rag_config(self) -> RagConfig:
    """Select lexical retrieval without loading an index or model."""
    return RagConfig()


def configure_rag(self, context: RagContext) -> None:
    """Retain the lazy core-managed retrieval context."""
    self.rag = context
```

Ne pas accéder à `self.rag.index` au démarrage. Prévoir une ingestion séparée et
consulter `docs/rag.md` : `sync()` remplace le snapshot complet d'un corpus.
Les hooks sont injectés dans l'ordre secrets, configs, RAG, skills, puis handlers.
Le RAG est dans `yamcps.rag`, sans package séparé. Les embeddings locaux exigent
l'extra `rag` ; le téléchargement (`yamcps models download`, extra `models`)
et l'activation du modèle sont deux étapes explicites. Pour un exemple complet
avec chemins configurables et opérations async, lire `plugins/yamcps-docs`.
