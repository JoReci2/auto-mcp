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
5. Pour une API authentifiée, examiner `SecretSpec`, `ConnectorSecrets`,
   `required_secrets()` et `configure()` dans le dépôt. Déclarer les champs requis
   et injecter les secrets sans les exposer dans les arguments des outils ou les
   erreurs. Documenter `YAMCPS_<IDENTIFIANT>_<SECRET>` ; ne pas stocker de valeur
   réelle dans le code, les skills, le README ou les fixtures.
6. Pour des skills seuls, ne rien enregistrer dans `register` et exposer les dossiers
   par `skill_roots()`. Chaque nom et dossier commence par `<id>-`, contient un
   `SKILL.md` avec `name` et `description`, et est inclus dans le wheel. Résoudre
   les chemins depuis `__file__` ; refuser les symlinks et ne pas exécuter les assets.
7. Ajouter des tests unittest collectables par les runners existants : chargement
   par entry point, contrat, collisions, cas métier, erreurs et absence de fuite
   de secrets. Simuler les API. Vérifier la coexistence avec un autre plugin.
8. Installer le plugin dans le même environnement que yamcps, vérifier
   `yamcps connectors list`, puis la découverte/appel MCP approprié. Construire
   wheel et sdist et installer le wheel hors du dépôt pour lire les skills sans
   dépendre du répertoire courant. Appliquer les contrôles qualité du dépôt.
9. Documenter installation, configuration, exemples, outils et limites dans le
   README du package. Mettre à jour les guides et contraintes concernés. Relire
   le diff avant livraison ; ne pas publier sur PyPI sans demande de l'utilisateur.

## Résultat attendu

Un plugin installable séparément, dont le contrat, les secrets et les ressources
sont vérifiés, avec la liste exacte des tests effectués et des limites restantes.
Le MCP fournit ces instructions ; l'édition des fichiers nécessite les capacités
et autorisations du client. Ne pas prétendre que ce skill installe le plugin.
