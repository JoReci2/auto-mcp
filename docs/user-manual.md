# Manuel utilisateur

hmcp (Home MCP) expose les fonctionnalités de connecteurs Python à des clients
compatibles avec le Model Context Protocol. Python 3.12 ou supérieur est requis.

## Installation et démarrage

Depuis ce dépôt (les packages ne sont pas encore publiés) :

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -e plugins/hmcp-demo
hmcp connectors list
hmcp serve --connector demo
hmcp serve --connector demo --transport http --port 8000
```

Après publication :

```sh
pip install hmcp hmcp-demo
uvx --from hmcp --with hmcp-demo hmcp serve --connector demo
```

`stdio` est le transport par défaut ; ses logs vont sur stderr. HTTP utilise
Streamable HTTP à `http://127.0.0.1:8000/mcp`, avec les protections DNS rebinding
du SDK. Il reste local, sans authentification. Le serveur ne propose pas de
paramètre pour écouter sur une interface publique.

Exemple de configuration pour un client acceptant `mcpServers` :

```json
{
  "mcpServers": {
    "home": {
      "command": "uvx",
      "args": ["--from", "hmcp", "--with", "hmcp-demo", "hmcp", "serve", "--connector", "demo"]
    }
  }
}
```

Avant publication, remplacer cette commande par le chemin absolu de `.venv/bin/hmcp`
et utiliser `args: ["serve", "--connector", "demo"]`.
Pour HTTP, configurer l’URL ci-dessus selon les options de votre client.

## Utiliser les fonctionnalités

Le connecteur `demo` expose l’outil `demo_echo`, qui retourne le message reçu.
Demander au client MCP d’appeler cet outil avec un argument `message` permet de
vérifier la connexion. Les outils disponibles dépendent des plugins sélectionnés.

Installer séparément chaque plugin `hmcp-<nom>`, puis utiliser une option
`--connector <nom>` par connecteur. `hmcp connectors list` affiche les plugins
installés sans importer leur code. Aucun connecteur n’est activé implicitement.
Les paramètres et variables d’environnement propres à un plugin sont décrits
par sa documentation.

## Consulter les skills

Le démonstrateur fournit `skill://demo-echo/SKILL.md`. Un client peut lire ce
fichier comme une ressource MCP. Les clients prenant en charge l’extension
`io.modelcontextprotocol/skills` peuvent découvrir les skills avec `skills/list`
et obtenir leur manifeste avec `skills/get`.

Les skills sont des instructions et des fichiers consultables : hmcp ne les
installe pas dans les agents et n’exécute pas leurs scripts. Leur utilisation
dépend des fonctionnalités du client. Redémarrer le serveur après toute
modification des fichiers ou installation d’un plugin.

## Résoudre les erreurs courantes

- **Commande introuvable** : activer l’environnement virtuel ou utiliser le chemin
  absolu de son exécutable `hmcp`.
- **Connecteur inconnu** : vérifier son installation dans le même environnement
  que hmcp et consulter `hmcp connectors list`.
- **Erreur de chargement ou d’enregistrement** : consulter stderr ; le diagnostic
  identifie le connecteur. Vérifier ses dépendances et sa configuration.
- **Port occupé** : choisir un autre port avec `--port` et adapter l’URL du client.
- **Skill absent** : vérifier que son connecteur est sélectionné et que le client
  sait lire les ressources MCP ou l’extension Skills.

HTTP est limité à la machine locale et ne fournit pas d’authentification dans
cette version. Ne pas l’exposer par un proxy public sans concevoir la protection
et l’authentification correspondantes.
