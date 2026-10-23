# Architecture de yamcps

## Objectifs et limites

Fournir un serveur MCP extensible avec un contrat de connecteur minimal et une
distribution Python standard. Le cœur `yamcps` et les plugins `yamcps-<nom>` sont des
packages indépendants. La V1 utilise stdio ou HTTP local, sans rechargement à
chaud ni installation de skills chez le client.

## Organisation et démarrage

- `src/yamcps/cli.py` : commandes, sélection des connecteurs et transport.
- `src/yamcps/connectors.py` : contrat structurel et découverte des entry points.
- `src/yamcps/server.py` : composition des connecteurs et du catalogue de skills.
- `src/yamcps/registry.py` : refus des enregistrements en double.
- `src/yamcps/skills.py` : indexation des fichiers et extension MCP Skills.
- `plugins/yamcps-demo` : distribution autonome servant d’exemple.
- `plugins/yamcps-demo-secrets` : exemple avec trois secrets déclarés, helpers Bearer/Basic
  et outil de statut local ne révélant aucun identifiant.
- `tests` : tests du cœur et intégration avec le client MCP officiel.

La CLI découvre les entry points `yamcps.connectors`. Sans `--connector`, elle
charge toutes les factories par ordre alphabétique ; sinon elle charge uniquement
la sélection explicite, dans l’ordre fourni. Une découverte vide en mode
automatique est une erreur expliquant qu’il faut installer un plugin. Le chargeur vérifie les identifiants et le contrat.
Le serveur découvre les secrets requis, résout les valeurs du coffre (avec
questions masquées si un terminal est disponible), configure les connecteurs,
puis indexe les skills, construit le serveur MCP et enregistre les
fonctionnalités des connecteurs et les ressources des skills, puis lance le
transport choisi. Une erreur de plugin empêche le démarrage.

Le serveur s’appuie sur le SDK officiel `mcp>=2.3,<3`. Les logs vont sur stderr
pour préserver les messages du transport stdio. HTTP écoute sur
`127.0.0.1:<port>/mcp` et conserve les protections réseau du SDK.

## Écrire un connecteur

Convention : distribution `yamcps-github`, module `yamcps_github`, identifiant `github`.
Le contrat public `yamcps.Connector` est un `Protocol` structurel : aucun héritage requis.

```python
from mcp.server import MCPServer

class GitHubConnector:
    id = "github"

    def register(self, server: MCPServer) -> None:
        @server.tool()
        async def github_status() -> str:
            """Report connector status."""
            return "ready"
```

Dans le `pyproject.toml` du plugin :

```toml
[project]
name = "yamcps-github"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["yamcps>=0.1,<0.2"]

[project.entry-points."yamcps.connectors"]
github = "yamcps_github:GitHubConnector"
```

La cible est une factory sans argument ; la classe ci-dessus convient directement.
L’entry point doit porter le même nom que `id`. Préfixer outils et prompts par
`github_` et choisir des URI propres au connecteur. Les doublons sont des erreurs.
L’enregistrement est synchrone ; les handlers peuvent être asynchrones.
Les dépendances réseau doivent être créées et fermées dans les handlers ou via
les mécanismes de contexte du SDK ; ne pas effectuer d’appel réseau à l’import.
Les configurations et secrets propres au plugin passent par ses variables
d’environnement documentées, par exemple `YAMCPS_GITHUB_TOKEN`.

Installer le plugin avec pip : il est inclus par défaut par `yamcps serve`.
Pour limiter les plugins chargés, sélectionner leurs identifiants :
`yamcps serve --connector github --connector demo`. La découverte n’importe pas les
plugins ; seules les factories sélectionnées sont chargées. Un échec de chargement
ou d’enregistrement interrompt le démarrage et identifie le plugin concerné.
Les plugins installés sont du code Python de confiance exécuté dans le processus.

Le package autonome [yamcps-demo](../plugins/yamcps-demo) est un exemple complet avec
Hatchling, entry point et fichiers de skills inclus dans le wheel.

## Authentification des API

Le contrat minimal reste inchangé. Pour bénéficier de la découverte et de
l’assistant, un connecteur déclare `required_secrets() -> Iterable[SecretSpec]`.
Chaque `SecretSpec(name, description="")` décrit un champ obligatoire, sans
valeur ni défaut. Les noms doivent être uniques dans le connecteur et en
kebab-case ; la liste peut être vide. Pour un token : `SecretSpec("token")` ;
pour Basic Auth : `SecretSpec("username")` et `SecretSpec("password")`.

Un connecteur peut ajouter la capacité
`configure(secrets: ConnectorSecrets) -> None`, synchrone, appelée avant
l’indexation des skills et `register`. Elle valide et conserve ses identifiants ;
aucune donnée d’authentification n’est ajoutée aux schémas des outils MCP.

```python
from yamcps import ConnectorSecrets, SecretSpec, TokenAuth
from mcp.server import MCPServer

class GitHubConnector:
    id = "github"
    auth: TokenAuth

    def required_secrets(self) -> list[SecretSpec]:
        """Describe the credentials requested by the setup wizard.

        Returns:
            Required API credential fields in prompt order.
        """
        return [SecretSpec("token", "GitHub API token")]

    def configure(self, secrets: ConnectorSecrets) -> None:
        """Load API credentials before registering handlers.

        Args:
            secrets: Credentials scoped to the github connector.
        """
        self.auth = secrets.token_auth()  # secret nommé token

    def register(self, server: MCPServer) -> None:
        """Register handlers that use credentials internally.

        Args:
            server: MCP server receiving this connector's handlers.
        """
        # Dans le handler qui effectue la requête HTTPS :
        # headers = {"Authorization": self.auth.authorization_header().get_secret_value()}
        # Transmettre headers au client HTTP ; ne jamais les retourner ni les logger.
```

Pour Basic Auth : `self.auth = secrets.basic_auth()` lit `username` et `password`
et fournit également `authorization_header()`. Le nom d’utilisateur ne peut pas
contenir `:` ; les identifiants sont encodés en UTF-8 avant base64. Vérifier la
compatibilité d’encodage avec l’API cible. `token_auth(name="api-token", scheme="Token")`
permet un autre nom de secret ou schéma. `require(name)` et `get(name)` donnent un
`SecretStr` pour les autres formats d’API. Les tokens doivent être non vides et
composés de caractères ASCII visibles ; les noms de secrets sont en kebab-case.
Les erreurs de configuration de plugins sont limitées et leurs valeurs connues
sont masquées dans les diagnostics du démarrage. Les auteurs doivent aussi éviter
de propager les credentials ou les en-têtes dans les erreurs de leurs handlers.

`yamcps.secrets` contient les objets masqués et les vues par connecteur ;
`yamcps.vault` gère le stockage chiffré ; `yamcps.onboarding` découvre les champs,
pose les questions et collecte un lot avant son écriture atomique. La CLI choisit
les chemins par défaut ou explicites et autorise l’interaction seulement si stdin
est un terminal. Les valeurs absentes déclenchent un message d’action sans lecture
de stdin en mode non interactif. Les valeurs existantes ne sont pas redemandées
au démarrage ; l’assistant explicite permet de les remplacer ou de les conserver.
Les instances des plugins sélectionnés ne sont chargées qu’une fois : la déclaration,
la résolution, `configure` et `register` utilisent les mêmes instances.
Un ancien plugin sans déclaration reste utilisable, mais ses champs doivent être
préconfigurés avec `set --name` si son `configure` les exige. Les
commandes de gestion ne sont pas des outils MCP accessibles à un modèle.
Un coffre explicitement sélectionné remplace la source environnement pour
l’injection. `os.environ` n’est pas modifié. Les plugins restent du code de
confiance : la vue par connecteur est une convention d’API, pas une sandbox.

Le format binaire est `HMCPVAULT` (signature historique conservée) + version `0x01` + nonce 12 octets + ciphertext
avec tag GCM 16 octets. L’en-tête est authentifié comme données associées. Le
contenu chiffré est un objet JSON de noms normalisés vers des valeurs texte.
La clé de 32 octets est produite par `AESGCM.generate_key` ; les nonces sont
produits par le générateur système via `os.urandom`. Chaque sauvegarde génère un
nouveau nonce. Le coffre vise un usage local à faible volume ; pas de service
multi-utilisateur, de verrou distribué ni de stockage de clé dans le trousseau.

Voir le [manuel utilisateur](user-manual.md#configurer-les-secrets-des-api) pour
les limites de protection, les sauvegardes et la portée des références ANSSI.

## Skills

Implémenter facultativement `skill_roots() -> Iterable[Path]`. Chaque chemin désigne
**un dossier de skill**, contenant `SKILL.md` et ses fichiers annexes :

```python
def skill_roots(self):
    return [Path(__file__).parent / "skills" / "github-review"]
```

Le nom du dossier et le champ YAML `name` doivent être identiques, en minuscules
avec tirets, préfixés par l’identifiant du connecteur (`github-review`). Une
`description` non vide est obligatoire. Les symlinks sont refusés. Inclure les
fichiers de skills dans les distributions et ne pas y placer de secrets : tous
les fichiers sous ces dossiers sont publiés.

Les fichiers sont indexés et mémorisés au démarrage : aucune lecture arbitraire de
chemin utilisateur, aucun rechargement à chaud, aucune exécution de script.
Les URI sont de la forme `skill://github-review/SKILL.md`. Les fichiers texte et
binaires sont disponibles par les ressources MCP standard ; `skills/list` et
`skills/get` exposent les métadonnées et le manifeste SHA-256 avec tailles en octets.

**Compatibilité SDK :** le SDK PyPI `mcp==2.3.0` testé fournit `Extension`, mais pas
le module `mcp.server.skills` décrit par sa documentation. `yamcps.skills` isole donc
un adaptateur utilisant cette API publique pour l’extension
`io.modelcontextprotocol/skills`. La lecture reste possible avec les ressources
standard sur les clients ne prenant pas en charge cette extension. Le serveur
n’installe pas les skills dans les agents ; leur chargement dépend du client.

## Distribution et compatibilité

Hatchling produit wheel et sdist. Les fichiers de skills doivent être inclus dans
le package du plugin et accessibles depuis son installation, sans dépendre du
répertoire courant. Le wheel `yamcps-demo` valide cette organisation.

La version initiale est `0.1.0`. Toute modification incompatible du contrat exige
une évolution de version et des contraintes des plugins. L’adaptateur Skills est
isolé pour permettre son remplacement par une API native du SDK après validation
de compatibilité.

## Validation de l’architecture

Les tests couvrent découverte sans import, sélection explicite, contrats invalides,
doublons, erreurs de plugins, frontmatter, empreintes, fichiers binaires et refus
des symlinks. Les intégrations exercent un client officiel en mémoire, en
sous-processus stdio et sur HTTP local. L’installation des wheels hors du dépôt
doit également être vérifiée localement. Le workflow `.github/workflows/workflow.yaml` construit et publie uniquement
la distribution racine `yamcps` lors de la publication d’une release GitHub.
Les plugins restent distribués séparément ; ils ne sont pas publiés par ce workflow.

## Recherche documentaire et RAG local

La capacité RAG est incluse dans le package de base, sous `src/yamcps/rag`.
Elle fournit les modèles `Document`, `Passage`, `SearchHit`, `Index`, le protocole
`Embedder`, `RagConfig` et `RagContext`. Le protocole facultatif `RagProvider`
déclare `rag_config() -> RagConfig` et `configure_rag(context) -> None` synchrones.
Le serveur configure les secrets, injecte le contexte RAG, indexe les skills,
puis enregistre les handlers sur les mêmes instances de connecteurs.

Le contexte crée son Index à la demande, avec un verrou par plugin. Les chemins
par défaut sont distincts : `YAMCPS_RAG_DIR/<id>.sqlite3`, ou
`~/.local/share/yamcps/rag/<id>.sqlite3`. Un plugin peut fournir des chemins
explicites. Aucun accès aux sources, création de base ou chargement de modèle ne
fait partie de l’injection. Un plugin sans hooks ne reçoit pas de contexte RAG.
Les deux hooks sont obligatoires dès que l’un est déclaré ; toute erreur de
configuration est signalée sans divulguer les chemins ou les secrets.
Les plugins demeurent du code de confiance ; les contextes ne sont pas des ACL.

Voir le [guide RAG natif](rag.md) pour l’indexation et les limites du stockage.

### Téléchargement explicite des modèles

`yamcps models download` utilise le module `yamcps.rag.download`. Seule cette
commande contacte Hugging Face, via la dépendance facultative `huggingface-hub`
(extra `models`, également inclus dans `rag`). Le démarrage et l'inférence restent
locaux. La révision est résolue en commit ; les fichiers sont préparés dans un
dossier temporaire, validés puis déplacés vers une nouvelle destination. Un verrou
par destination évite les écritures concurrentes. La commande ne charge pas les
poids et ne modifie ni la configuration des plugins ni leurs index. Les métadonnées
Hub temporaires sont retirées pour ne pas perturber l'empreinte locale du modèle.
`yamcps-model.json` conserve la provenance sans token. Les tokens éventuels viennent
de `HF_TOKEN` ; les erreurs réseau sont masquées.

## Configurations non secrètes des plugins

`yamcps.configs` fournit `ConfigSpec`, `ConnectorConfigs` et `ConfigStore`. Les
hooks synchrones `required_configs()` et `configure_configs()` déclarent puis
reçoivent les valeurs. Le stockage JSON en clair est séparé du vault et n’ajoute
aucune dépendance. Un verrou et un remplacement atomique protègent les écritures.
La résolution applique fichier, repli environnement, puis défaut ; les clés sont
normalisées par plugin. Les options `config_values`/`config_store` de create_server
sont exclusives. Les configurations sont injectées après les secrets, avant le
RAG, les skills et l’enregistrement. Sans déclaration, aucun fichier n’est lu.
Les champs requis manquants sont demandés seulement en terminal ; sans terminal,
un diagnostic de préconfiguration remplace toute lecture du flux MCP.

Voir [le contrat et les commandes](configuration.md).
