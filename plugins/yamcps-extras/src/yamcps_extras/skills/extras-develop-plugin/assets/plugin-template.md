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
