# yamcps-extras

Plugin qui fournit uniquement deux skills de développement via le catalogue MCP
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
| `skill://extras-configure-agents/SKILL.md` | Préparer les consignes avec sécurité, protection de l'existant, découverte, questionnaire et usages MCP, puis validation avant écriture |
| `skill://extras-develop-plugin/SKILL.md` | Développer un plugin autonome sans dépôt du moteur, avec contrat public, projet complet, tests et README |

Les modèles sont accessibles sous l'URI du skill, par exemple :
`skill://extras-configure-agents/assets/AGENTS.template.md`.

Le guide de configuration des consignes traite `AGENTS.md`, `AGENT.md` ou `Agent.md`
selon le client et le fichier existant. Il inventorie les capacités MCP visibles
(skills, RAG et outils) et propose leur usage par plugin. Le contenu ou le diff
doit être approuvé avant écriture ; les modifications concurrentes sont préservées.

Les clients compatibles découvrent ces guides avec `skills/list` et `skills/get`.
Les ressources MCP standard permettent aussi de les lire si le client ne prend pas
l'extension Skills en charge. L'affichage et l'utilisation automatiques dépendent
du client. Le plugin n'installe pas de skills dans son système de fichiers.

Exemples de demandes après chargement du skill pertinent : « prépare les consignes
de ce dépôt » ou « crée un plugin yamcps météo ».

Le skill `extras-develop-plugin` est utilisable sans accès au dépôt yamcps : lire
son `SKILL.md`, puis `skill://extras-develop-plugin/assets/plugin-template.md`.
Ces deux ressources fournissent le contrat public, les fichiers d'un projet
autonome, les recettes de configurations/secrets/RAG, les tests, le packaging et
le modèle de README. Seul le moteur distribué et ses dépendances sont nécessaires
pour exécuter le plugin. Le développeur travaille sur sa machine ; l'opérateur
installe le wheel dans l'environnement du serveur cible puis le redémarre.

Le guide de configuration des consignes demande d'inspecter les sources et consignes présentes plutôt
que de supposer une version de yamcps. Les guides couvrent les configurations JSON via
`required_configs()` / `configure_configs()` et `yamcps configs set`, ainsi que
le RAG natif facultatif (`rag_config()` / `configure_rag()`), l'ingestion séparée
et les modèles locaux. Voir les guides de [configuration](../../docs/configuration.md)
et de [RAG](../../docs/rag.md). Leur application requiert un client disposant des
outils d'édition et d'exécution nécessaires. Redémarrer le serveur après une
modification des fichiers de skills.
