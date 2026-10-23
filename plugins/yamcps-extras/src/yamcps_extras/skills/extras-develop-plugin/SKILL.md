---
name: extras-develop-plugin
description: Créer ou faire évoluer un plugin yamcps indépendant avec entry point, outils ou skills, configuration, tests et packaging. Utiliser pour ajouter un connecteur métier ou un plugin qui expose uniquement des skills.
---

# Développer un plugin yamcps

1. Lire les consignes du dépôt, `docs/design.md`, `contributing.md`, le contrat
   dans `src/yamcps/connectors.py` et un plugin proche du besoin. Pour un dépôt
   de plugin autonome, inspecter aussi la version installée de yamcps. Les sources
   réellement utilisées priment sur les exemples de ce guide.
2. Définir les opérations, leurs entrées/sorties et leur caractère lecture seule
   ou mutation. Choisir un identifiant métier en kebab-case : par exemple `weather`.
   Utiliser `yamcps-weather`, `yamcps_weather`, `weather` pour distribution, module
   et entry point ; préfixer outils et prompts par `weather_`.
3. Créer un package indépendant sous `plugins/yamcps-<nom>` dans le monorepo,
   ou à la racine d'un dépôt autonome. Partir du [squelette](assets/plugin-template.md).
   Déclarer une factory sans argument et une contrainte de version du cœur compatible.
   Ne pas importer les modules internes d'un autre plugin.
4. Implémenter `id` et `register(server: MCPServer) -> None` synchrones ; rendre
   les handlers asynchrones si nécessaire. Ne faire aucun appel réseau à l'import,
   dans la factory ou pendant l'enregistrement. Fermer les clients réseau dans
   les handlers ou via un mécanisme de cycle de vie déjà pris en charge.
5. Pour les paramètres non secrets (chemins, modes, URL sans identifiants), lire
   `docs/configuration.md` et implémenter ensemble `required_configs()` retournant
   des `ConfigSpec` et `configure_configs(configs: ConnectorConfigs)`, synchrones.
   Utiliser `yamcps configs set --connector <id>` plutôt que demander des exports.
   Les valeurs sont des chaînes en JSON local ; un défaut rend un champ facultatif.
   Ne jamais y stocker de token ou mot de passe. Pour une API authentifiée, examiner `SecretSpec`, `ConnectorSecrets`,
   `required_secrets()` et `configure()` dans le dépôt. Déclarer les champs requis
   et injecter les secrets sans les exposer dans les arguments des outils ou les
   erreurs. Documenter `YAMCPS_<IDENTIFIANT>_<SECRET>` ; ne pas stocker de valeur
   réelle dans le code, les skills, le README ou les fixtures.
6. Si le plugin a besoin de recherche documentaire, lire `docs/rag.md` et prendre
   `yamcps-docs` comme exemple. Le RAG appartient au moteur `yamcps.rag` ; ne pas
   créer ni installer de package `yamcps-rag-core`. Déclarer ensemble `rag_config()`
   et `configure_rag(context: RagContext)`, synchrones. L'ordre d'injection est
   secrets, configs, RAG, skills, puis handlers. Garder le contexte paresseux :
   aucun accès à `context.index`, modèle, source ou ingestion dans ces hooks.
   Préparer l'ingestion séparément : `Index.sync()` remplace tout le corpus donné,
   y compris les suppressions. Déporter les opérations bloquantes des handlers async.
   Le mode lexical fonctionne sans modèle ; télécharger un modèle est une action
   CLI explicite (`yamcps models download`), puis configurer son chemin local.
   Installer l'extra `rag` pour les embeddings ; changer de modèle exige un nouvel
   index et une réingestion. Ne pas télécharger implicitement au démarrage.
7. Pour des skills seuls, ne rien enregistrer dans `register` et exposer les dossiers
   par `skill_roots()`. Chaque nom et dossier commence par `<id>-`, contient un
   `SKILL.md` avec `name` et `description`, et est inclus dans le wheel. Résoudre
   les chemins depuis `__file__` ; refuser les symlinks et ne pas exécuter les assets.
8. Ajouter des tests unittest collectables par les runners existants : chargement
   par entry point, contrat, collisions, cas métier, erreurs et absence de fuite
   de secrets. Simuler les API. Vérifier la coexistence avec un autre plugin.
9. Installer le plugin dans le même environnement que yamcps, vérifier
   `yamcps connectors list`, puis la découverte/appel MCP approprié. Construire
   wheel et sdist et installer le wheel hors du dépôt pour lire les skills sans
   dépendre du répertoire courant. Appliquer les contrôles qualité du dépôt.
10. Créer ou actualiser le `README.md` du package avec la structure obligatoire
   ci-dessous et la section « README uniformisé » du [squelette](assets/plugin-template.md).
   Mettre à jour les guides et contraintes concernés. Relire
   le diff avant livraison ; ne pas publier sur PyPI sans demande de l'utilisateur.

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

Un plugin installable séparément, dont le contrat, les secrets et les ressources
sont vérifiés, avec la liste exacte des tests effectués et des limites restantes.
Le MCP fournit ces instructions ; l'édition des fichiers nécessite les capacités
et autorisations du client. Ne pas prétendre que ce skill installe le plugin.
