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

## README uniformisé

Créer `README.md` à la racine du package avec ce modèle. Remplacer tous les champs
entre chevrons d'après le plugin réel. Conserver les titres et l'ordre des sections.
Les quatre tableaux restent présents ; si une catégorie est vide, remplacer ses
lignes par `Aucun` (`Aucune` pour les variables) et `—` dans les autres colonnes.

````markdown
# yamcps-<nom>

## Description

<Description courte du rôle et du périmètre du plugin.>

## Quickstart

Prérequis : <version Python, services et droits nécessaires au plugin.>

Depuis la racine du dépôt yamcps, dans un environnement Python activé :

```sh
python -m pip install -e . -e plugins/yamcps-<nom>
yamcps connectors list
# Garder uniquement les commandes de configuration utiles au plugin :
yamcps configs set --connector <id>
yamcps secrets set --connector <id>
yamcps serve --connector <id>
```

<Adapter l'installation pour un dépôt autonome ou une distribution publiée.
Retirer les commandes de configuration inutiles et ce commentaire. Si nécessaire,
insérer la préparation du corpus et l'ingestion avant le démarrage.>

<Exemple d'utilisation court avec un outil ou un skill réellement exposé.>

## Outils

| Outil | Description |
| --- | --- |
| `<id>_<outil>` | <Fonction et effets de l'outil MCP.> |

## Skills

| Skill | Description |
| --- | --- |
| [`<id>-<action>`](src/<module>/skills/<id>-<action>/SKILL.md) | <Description du skill exposé.> |

## Variable de configuration

| Variable | Nom du champ | Description | Obligatoire | Valeur par défaut |
| --- | --- | --- | --- | --- |
| `<clé YAMCPS_* exacte>` | `<nom du champ>` | <Paramètre non secret.> | <Oui ou Non> | <Défaut réel, chaîne vide autorisée ou Aucun> |

## Secret

| Secret | Nom du champ | Description | Obligatoire |
| --- | --- | --- | --- |
| `<clé YAMCPS_* exacte>` | `<nom du champ>` | <Rôle du secret conservé dans le vault, sans sa valeur.> | <Oui ou Non> |
````

Pour le connecteur `weather_status` minimal du début de ce squelette, le tableau
Outils contient seulement `weather_status` (« Indique la disponibilité locale,
sans contacter de service externe »). Les sections Skills, Variable de configuration
et Secret contiennent une ligne d'absence et leurs commandes de configuration sont
retirées. Ajouter les champs `endpoint` ou les hooks RAG optionnels au code impose
de réexaminer le README ; ne pas les documenter comme actifs dans le plugin minimal.
