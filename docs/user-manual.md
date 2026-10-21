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

Installer séparément chaque plugin `hmcp-<nom>`. Sans option `--connector`, tous
les plugins installés sont chargés par ordre alphabétique :

```sh
hmcp serve
hmcp serve --transport http
```

Pour sélectionner un ou plusieurs plugins, répéter `--connector` :

```sh
hmcp serve --connector demo --connector demo-secrets
```

Dans ce cas, seuls les connecteurs indiqués sont chargés, dans l’ordre fourni.
`hmcp connectors list` affiche les plugins installés sans importer leur code.
Si aucun plugin n’est installé, `hmcp serve` indique qu’il faut en installer un.
Les secrets requis par tous les plugins chargés sont vérifiés : les valeurs
manquantes sont demandées dans un terminal, ou signalées sans terminal.
Les paramètres et variables d’environnement propres à un plugin sont décrits
par sa documentation.

## Configurer les secrets des API

Les connecteurs déclarent leurs secrets requis (token, username/password, etc.).
Lors d’un lancement depuis un terminal, hmcp inspecte **uniquement les connecteurs
sélectionnés**, consulte le coffre et demande les valeurs manquantes avec saisie
masquée, avant de démarrer le serveur :

```sh
hmcp serve --connector my-api
```

Le connecteur `hmcp-my-api` doit être installé et déclarer ses besoins. Pour un
connecteur Basic Auth, hmcp demande par exemple `my-api/username` puis
`my-api/password`. Les valeurs présentes sont réutilisées sans nouvelle question.
`hmcp-demo` ne demande aucun secret.

Le coffre et sa clé sont créés automatiquement au premier enregistrement :

- Coffre : `~/.local/share/hmcp/secrets.hmcp-vault`.
- Clé séparée : `~/.config/hmcp/keys/master.hmcp-key`.

Les nouveaux répertoires finaux sont privés (`0700`), et les fichiers sont créés
avec accès réservé au propriétaire (`0600` sous POSIX). Sous Windows, restreindre
aussi leurs ACL au compte du service. Un coffre ou une clé existant seul, une
mauvaise clé ou un coffre altéré provoquent une erreur : rien n’est réinitialisé.

### Configurer ou modifier un connecteur

L’assistant complet peut être ouvert directement :

```sh
hmcp secrets set --connector my-api
```

Il demande tous les champs déclarés par le connecteur. Une saisie vide conserve
une valeur déjà enregistrée ; pour un champ absent, une valeur non vide est
obligatoire. Les modifications ne sont enregistrées qu’après toutes les saisies.
Une interruption ou une fin d’entrée conserve le coffre inchangé.

Les commandes existantes restent disponibles, avec les chemins par défaut :

```sh
hmcp secrets init
hmcp secrets list
hmcp secrets set --connector my-api --name token
hmcp secrets delete --connector my-api --name token
```

`init` reste facultatif et refuse d’écraser un coffre existant. `list` affiche
uniquement les noms. `set --name` permet de configurer un secret individuel, y
compris pour un ancien plugin qui ne déclare pas ses champs. Sans `--name`, le
connecteur doit être installé et implémenter `required_secrets()`.
Il n’existe pas de paramètre `--value` : la saisie se fait dans le terminal pour
ne pas placer les secrets dans l’historique ou les arguments du processus.

Les options de chemin restent disponibles sur toutes les commandes :

```sh
hmcp secrets set --connector my-api --vault /chemin/secrets.hmcp-vault --key-file /autre/chemin/master.hmcp-key
hmcp serve --connector my-api --vault /chemin/secrets.hmcp-vault --key-file /autre/chemin/master.hmcp-key
```

Toujours fournir ces deux options ensemble, et utiliser les mêmes chemins pour
l’administration et le serveur. Les secrets sont chargés au démarrage ;
redémarrer après une modification.

### Lancement depuis un client MCP

Un client MCP lance généralement le serveur sans terminal interactif. Si tous
les secrets sont présents, hmcp démarre normalement. Sinon, il échoue rapidement
avec une commande `hmcp secrets set --connector <nom>` à exécuter dans un terminal.
Il ne lit jamais les messages du protocole pour demander un secret.
Configurer le coffre une première fois dans un terminal, sous le même compte que
le serveur, puis relancer le client. Pour un coffre personnalisé, reprendre ses
options `--vault` et `--key-file` dans la commande de configuration.

Les prompts et diagnostics vont sur stderr ; stdout reste réservé au protocole
stdio. La configuration est locale, sans outil de gestion des secrets accessible
au modèle. Le chiffrement concerne les identifiants des API appelées par les
connecteurs, pas l’authentification des clients qui se connectent au serveur MCP.

La CLI utilise toujours le coffre, sans repli sur l’environnement ni chargement
implicite de `.env`. L’API Python `create_server(..., secret_values=...)` reste
utilisable avec une source explicite ; sans coffre ni source explicite elle
conserve la lecture des variables `HMCP_<CONNECTEUR>_<SECRET>` pour compatibilité.

### Protection et exploitation du coffre

Le chiffrement authentifié AES-256-GCM utilise un nonce aléatoire de 96 bits à
chaque écriture et un tag de 128 bits. Une mauvaise clé ou une altération provoque
un refus de lecture. Ces choix s’appuient sur les principes des
[guides cryptographiques ANSSI](https://cyber.gouv.fr/reglementation/reglementation-identite-confiance-numerique/securite-echanges-voie-electronique/referentiel-general-de-securite/documents-referentiel-general-de-securite/)
et l’implémentation [AESGCM de cryptography](https://cryptography.io/en/latest/hazmat/primitives/aead/).
**hmcp n’est pas un produit qualifié ou certifié ANSSI et cette implémentation
n’a pas fait l’objet d’un audit de conformité.**

Conserver et sauvegarder la clé séparément du coffre, avec des accès restreints.
La perte de la clé rend les secrets irrécupérables. La possession du coffre et de
la clé permet leur déchiffrement ; le chiffrement au repos ne protège pas contre
un processus ou un plugin compromis ayant les mêmes droits. Les secrets sont
déchiffrés en mémoire et Python ne garantit pas leur effacement sécurisé.
Basic Auth encode les identifiants en base64 : les appels API doivent utiliser
HTTPS avec validation des certificats, comme les appels avec token.

Les écritures sont atomiques et protégées par un fichier `.lock` ; elles ne
permettent pas de détecter la restauration d’une ancienne version valide du
coffre. Après un arrêt brutal pendant une modification, vérifier qu’aucune
commande d’écriture n’est active avant de retirer un verrou résiduel. Conserver
une sauvegarde protégée ; la rotation de clé n’est pas automatisée dans cette
version (créer un nouveau coffre et y réenregistrer les identifiants).
Les fichiers `*.hmcp-key`, `*.hmcp-vault` et leurs verrous sont ignorés par Git.
Ne jamais placer de secrets dans les dossiers de skills, qui sont publiés via MCP.

## Essayer le plugin de démonstration des secrets

Depuis la racine du dépôt :

```sh
python -m pip install -e . -e plugins/hmcp-demo-secrets
hmcp serve --connector demo-secrets
```

Le premier lancement demande un token, un nom d’utilisateur et un mot de passe.
Utiliser des valeurs fictives : ce plugin ne contacte aucune API. Après connexion
avec un client MCP, appeler `demo_secrets_status` sans argument pour vérifier le
chargement et la construction locale des authentifications Bearer et Basic.
L’outil retourne uniquement le statut et les schémas, jamais les valeurs.

```sh
hmcp secrets set --connector demo-secrets
hmcp secrets delete --connector demo-secrets --name token
hmcp serve --connector demo-secrets
```

La première commande ouvre l’assistant complet ; après la suppression du token,
le prochain lancement ne demande que ce champ. Le skill
`skill://demo-secrets-check/SKILL.md` décrit l’outil. Pour un client sans terminal,
exécuter d’abord la commande `secrets set` dans un terminal.
Voir le [README du plugin](../plugins/hmcp-demo-secrets/README.md).

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
