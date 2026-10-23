---
name: extras-develop-plugin
description: "Développer un plugin yamcps autonome sans accès au dépôt du moteur, à partir des ressources MCP de ce skill : contrat public, projet complet, configuration, secrets, RAG, tests, packaging et README uniforme. Utiliser pour créer ou faire évoluer un connecteur métier ou un plugin de skills."
---

# Développer un plugin yamcps sans le dépôt du moteur

Ce guide et son asset contiennent les informations nécessaires au développement.
Ne pas demander le clone de yamcps, ses documents internes ou le code d'un autre
plugin. Travailler dans un nouveau projet de plugin, ou respecter les consignes
locales du projet de plugin existant si elles sont accessibles.

## Lire les ressources depuis MCP

1. Lire cette ressource : `skill://extras-develop-plugin/SKILL.md`.
2. Lire le [projet complet et les recettes](assets/plugin-template.md) avec
   `resources/read` sur `skill://extras-develop-plugin/assets/plugin-template.md`.
   Un lien relatif désigne ici une ressource du skill, pas un fichier du dépôt.
   Les clients compatibles peuvent aussi employer `skills/list` et `skills/get` ;
   lire ensuite le contenu des fichiers indiqués dans les ressources retournées.
3. Copier les fichiers du projet minimal de l'asset dans l'espace de travail du
   développeur, puis les adapter. Toutes les recettes et le modèle de README sont
   dans ce même asset ; aucune autre documentation yamcps n'est nécessaire.

Le serveur MCP fournit des instructions et des fichiers en lecture. Le client
agent ou le développeur doit pouvoir écrire et exécuter du Python sur sa machine.
Si le client n'a que la lecture MCP, produire les fichiers et commandes à copier,
mais ne pas annoncer de création, de test ou d'installation déjà effectués.
L'administrateur du serveur cible installe ensuite le wheel dans l'environnement
Python de ce serveur et le redémarre ; le client MCP distant ne l'installe pas.

## Compatibilité et contrat public

Référence de ce guide : Python ≥ 3.12, yamcps 0.1.x et SDK `mcp>=2.3,<3`.
La version 0.1.0 seule ne distingue pas les capacités ajoutées dans ses branches :
vérifier les imports requis dans l'environnement de développement ET celui du
serveur cible. Une bibliothèque distribuée ou un wheel fourni par l'administrateur
suffit, sans sources du moteur. Le projet minimal n'utilise que le contrat de base.
Pour configs/RAG, exécuter avant de les choisir :

```sh
python -c "from importlib.metadata import version; print(version('yamcps'), version('mcp'))"
python -c "from yamcps import ConfigSpec, ConnectorConfigs, RagConfig, RagContext"
```

Si une capacité manque, rester sur le contrat minimal ou obtenir un wheel du
moteur qui la fournit ; ne pas inventer une API ni installer un package RAG séparé.
Sur un poste hors ligne, utiliser un répertoire de wheels compatibles avec Python
et l'OS cibles : `python -m pip install --no-index --find-links /chemin/wheels yamcps`.
Sans accès au runtime distant, faire vérifier cette compatibilité par son opérateur.

| Élément | Contrat |
| --- | --- |
| Distribution / module / identifiant | `yamcps-weather` / `yamcps_weather` / `weather` ; noms kebab-case pour les identifiants, underscores pour les modules |
| Découverte | Entry point dans `yamcps.connectors`, nom égal à `id`, valeur `module:classe_ou_factory` appelable sans argument |
| Base obligatoire | `id: str`, `register(server: MCPServer) -> None` synchrone ; aucune classe mère yamcps imposée |
| Enregistrement | `from mcp.server import MCPServer` ; décorateurs `@server.tool()`, `@server.prompt()` ou `@server.resource("scheme://...")` ; handlers sync ou async |
| Noms et collisions | Préfixer outils/prompts par `<id>_` (tirets de l'id remplacés par `_`) et choisir des URI propres ; doublons refusés |
| Configs facultatives | Deux hooks synchrones : `required_configs() -> Iterable[ConfigSpec]`, `configure_configs(configs: ConnectorConfigs) -> None` |
| Secrets facultatifs | `required_secrets() -> Iterable[SecretSpec]` pour l'assistant ; `configure(secrets: ConnectorSecrets) -> None` pour recevoir les valeurs |
| RAG facultatif | Deux hooks synchrones : `rag_config() -> RagConfig`, `configure_rag(context: RagContext) -> None` |
| Skills facultatifs | `skill_roots() -> Iterable[Path]`, une racine par skill embarqué |
| Ordre d'injection | Secrets → configs → RAG → catalogue des skills → enregistrement des handlers |

Les imports des capacités sont publics : `from yamcps import ConfigSpec,
ConnectorConfigs, SecretSpec, ConnectorSecrets, RagConfig, RagContext`.
Pour la composition et les tests : `from yamcps.server import create_server`.
Pour les documents et l'index natifs : `from yamcps.rag import Document, Index`.
Le moteur ne fournit pas de sandbox pour le code des plugins.

## Réaliser le plugin

1. Définir opérations, entrées/sorties, accès métier et effets de chaque outil.
   Partir du projet minimal de l'asset ; ne pas importer un autre plugin.
2. Ajouter seulement les capacités nécessaires avec les recettes de l'asset.
   Les hooks, la factory et `register()` ne doivent faire aucun appel réseau,
   accès aux sources, ingestion ou chargement de modèle. Garder RAG paresseux :
   ne pas accéder à `context.index` pendant le démarrage.
3. Typer les interfaces et documenter les fonctions publiques en anglais avec
   des docstrings Google. Suivre PEP 8 ; formater/linter avec Ruff (100 caractères).
   Borner les entrées et délais réseau, fermer les clients, simuler les API dans
   les tests. Déporter les opérations bloquantes hors des handlers async.
4. Préserver stdout pour MCP stdio ; utiliser les logs stderr. Garder HTTP local
   par défaut. Ne pas ajouter d'authentification ou d'accès distant implicitement.
   Masquer les credentials ; ne jamais retourner les exceptions brutes d'une API.
   Décrire les effets réels via `ToolAnnotations` plutôt que déclarer une mutation
   en lecture seule. Les skills sont des fichiers servis, pas des scripts exécutés.
5. Appliquer le README uniforme ci-dessous et le modèle de l'asset. Inventorier
   seulement les outils, skills, configs et secrets réellement implémentés.
6. Exécuter les commandes de l'asset dans le projet autonome : découverte par
   entry point, tests unittest/MCP en mémoire et stdio, build wheel/sdist,
   installation du wheel et lecture du skill hors du projet. Ajouter des tests
   métier et de non-régression ainsi que les cas de collisions et d'erreurs utiles.
   Pour une modification liée à HTTP, tester aussi ce transport local.
7. Appliquer les contrôles qualité et la couverture de l'asset (objectif >80 %).
   Livrer les fichiers, le wheel, les commandes d'installation sur le serveur
   cible et les résultats réellement obtenus. Ne pas publier sur PyPI ni installer
   sur le serveur distant sans demande correspondante.

## Structure obligatoire du README des plugins

Conserver exactement ces titres, dans cet ordre, pour tout plugin créé ou modifié :

```markdown
# nom du plugin
## Description
## Quickstart
## Outils
## Skills
## Variable de configuration
## Secret
```

- Remplacer le titre principal par le nom de distribution réel (`yamcps-<nom>`).
  Écrire une description courte du rôle et du périmètre du plugin.
- Dans Quickstart, donner les prérequis, l'installation réellement disponible,
  les étapes de configuration nécessaires puis la commande de démarrage avec
  `--connector <id>`. Privilégier `yamcps configs set` pour les paramètres en clair
  et `yamcps secrets set` pour le vault ; aucun export ni secret en argument requis.
  Inclure l'ingestion préalable si nécessaire et un exemple d'utilisation court.
  Ne pas proposer une installation PyPI si le plugin n'y est pas publié.
- Dans Outils, fournir un tableau `Outil | Description` avec les noms MCP exacts
  des handlers enregistrés, leurs fonctions et leurs effets si pertinents.
- Dans Skills, fournir un tableau `Skill | Description` correspondant aux noms
  et descriptions des `SKILL.md` fournis par `skill_roots()`. Lier les fichiers
  locaux lorsque possible et expliquer leur lecture MCP dans Quickstart si utile.
- Dans Variable de configuration, fournir un tableau
  `Variable | Nom du champ | Description | Obligatoire | Valeur par défaut`.
  Relever les paramètres réellement consommés et les déclarations `ConfigSpec` ;
  vérifier les clés `YAMCPS_*` dans le code plutôt que les déduire approximativement.
  Distinguer une valeur vide autorisée de l'absence de défaut. Expliquer la commande
  de configuration dans Quickstart ; ces clés JSON ne nécessitent pas d'export.
- Dans Secret, fournir un tableau
  `Secret | Nom du champ | Description | Obligatoire` avec les clés exactes et les
  champs utilisés par `SecretSpec` / `ConnectorSecrets`. Décrire leur configuration
  via le vault dans Quickstart ; ne jamais inclure de valeur réelle ni de défaut
  contenant un identifiant sensible. Ne pas classer un secret comme config en clair.
- Garder les quatre tableaux même si une catégorie est vide : utiliser une ligne
  `Aucun` (ou `Aucune` pour les variables) et `—` dans les autres colonnes. Ne pas
  inventer de capacité, de paramètre ou de secret pour remplir une section.
- Préserver les informations utiles d'un README existant en les plaçant dans les
  sections correspondantes ou dans des guides liés ; garder ces six sections de
  niveau 2 et déplacer les détails longs vers la documentation spécialisée.
  Avant livraison, comparer les tableaux au code et vérifier commandes et liens.

## Résultat attendu

Un projet de plugin indépendant, installable avec le moteur distribué, documenté,
testé et livré sans dépendance au dépôt yamcps. Distinguer les étapes exécutées
localement de celles qui restent à effectuer sur le serveur cible.
