# yamcps-extras

Plugin qui fournit uniquement quatre skills de développement via le catalogue MCP
existant. Il n'ajoute aucun outil, prompt, secret, commande CLI ni appel réseau.
Les fichiers des skills et leurs modèles sont des ressources statiques ; le serveur
ne les exécute pas et ne modifie aucun dépôt.

## Installation

Depuis la racine du dépôt :

```sh
python -m pip install -e . -e plugins/yamcps-extras
yamcps connectors list
yamcps serve --connector extras
```

Sans `--connector`, le plugin est inclus parmi les plugins installés. Pour le
combiner avec un autre : `yamcps serve --connector extras --connector demo`.
Il n'est pas publié par le workflow PyPI du package de base.

## Skills exposés

| URI | Usage |
| --- | --- |
| `skill://extras-configure-agents/SKILL.md` | Créer/actualiser AGENTS.md, ou AGENT.md selon le client, avec un modèle adaptable |
| `skill://extras-develop-plugin/SKILL.md` | Développer un plugin indépendant, avec un squelette de package |
| `skill://extras-add-core-feature/SKILL.md` | Ajouter une fonctionnalité au moteur et vérifier sa compatibilité |
| `skill://extras-fix-core-bug/SKILL.md` | Reproduire un bug, corriger sa cause et tester la non-régression |

Les modèles sont accessibles sous l'URI du skill, par exemple :
`skill://extras-configure-agents/assets/AGENTS.template.md`.

Les clients compatibles découvrent ces guides avec `skills/list` et `skills/get`.
Les ressources MCP standard permettent aussi de les lire si le client ne prend pas
l'extension Skills en charge. L'affichage et l'utilisation automatiques dépendent
du client. Le plugin n'installe pas de skills dans son système de fichiers.

Exemples de demandes après chargement du skill pertinent : « prépare les consignes
de ce dépôt », « crée un plugin yamcps météo », « ajoute une option CLI au moteur »,
« corrige ce bug de découverte avec un test de régression ».

Les guides demandent d'inspecter les sources et consignes présentes plutôt que de
supposer une version de yamcps. Leur application requiert un client disposant des
outils d'édition et d'exécution nécessaires. Redémarrer le serveur après une
modification des fichiers de skills.
