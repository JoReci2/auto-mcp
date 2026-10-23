# Manuel utilisateur

yamcps (Yet Another Model Context Protocole Server) expose les fonctionnalités de
connecteurs Python à des clients compatibles avec le Model Context Protocol.

## Prérequis

- Python 3.12 ou supérieur, avec `pip` et `venv`.
- Un client compatible MCP, prenant en charge stdio ou Streamable HTTP.
- Au moins un connecteur, à installer dans le même environnement que yamcps
  selon sa documentation.

## Installation

Créer un environnement virtuel, puis installer yamcps.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install yamcps
```

### Unix (Linux / macOS)

```sh
python3 -m venv .venv
.venv/bin/python -m pip install yamcps
```

Les commandes ci-dessous s’exécutent depuis le dossier contenant `.venv`.
Dans la suite du guide, remplacer `yamcps` et `python` par les exécutables de cet
environnement, ou activer celui-ci avant de lancer les commandes.

### Installation des extensions

Les extensions (ou plugins) sont des distributions Python indépendantes.
Installer les connecteurs souhaités dans le même environnement que `yamcps`,
selon les instructions de leurs dépôts respectifs, puis vérifier leur découverte :

```sh
yamcps connectors list
```

Redémarrer le serveur après l’installation d’une extension. Utiliser des chemins
absolus pour les données locales et ne pas copier de coffre, de clé ou de données
sensibles dans Git. Voir la [configuration](#configuration) pour les secrets
et les paramètres non secrets.

## Démarrage

Vérifier les connecteurs disponibles :

- Windows : `.\.venv\Scripts\yamcps.exe connectors list`
- Unix : `.venv/bin/yamcps connectors list`

Sans `--connector`, yamcps charge tous les connecteurs installés par ordre
alphabétique. Pour limiter la sélection, ajouter `--connector <identifiant>` ;
cette option peut être répétée.

### Stdio

Le client MCP lance lui-même le serveur. Pour un client acceptant `mcpServers`,
utiliser l’une des configurations suivantes avec un chemin absolu.

#### Windows

```json
{
  "mcpServers": {
    "yamcps": {
      "command": "C:\\chemin\\vers\\.venv\\Scripts\\yamcps.exe",
      "args": ["serve"]
    }
  }
}
```

#### Unix

```json
{
  "mcpServers": {
    "yamcps": {
      "command": "/chemin/absolu/vers/.venv/bin/yamcps",
      "args": ["serve"]
    }
  }
}
```

Stdio est le transport par défaut. Les logs sont envoyés sur stderr ; stdout
est réservé au protocole MCP. Configurer les secrets et paramètres obligatoires
dans un terminal avant de lancer le client : voir la [configuration](#configuration).

### HTTP (Streamable HTTP)

Démarrer le serveur dans un terminal et le laisser ouvert.

#### Windows (PowerShell)

```powershell
.\.venv\Scripts\yamcps.exe serve --transport http --port 8000
```

#### Unix

```sh
.venv/bin/yamcps serve --transport http --port 8000
```

Dans le client MCP, choisir Streamable HTTP et renseigner
`http://127.0.0.1:8000/mcp`. Adapter le port si nécessaire et arrêter le serveur
avec `Ctrl+C`.

HTTP reste local, sans authentification, avec les protections DNS rebinding du
SDK. Le serveur ne propose pas de paramètre pour écouter sur une interface publique.

## Utiliser les fonctionnalités

Le connecteur `demo` expose l’outil `demo_echo`, qui retourne le message reçu.
Demander au client MCP d’appeler cet outil avec un argument `message` permet de
vérifier la connexion. Les outils disponibles dépendent des plugins sélectionnés.

Pour sélectionner un ou plusieurs plugins, répéter `--connector` :

```sh
yamcps serve --connector demo --connector demo-secrets
```

Dans ce cas, seuls les connecteurs indiqués sont chargés, dans l’ordre fourni.
`yamcps connectors list` affiche les plugins installés sans importer leur code.
Si aucun plugin n’est installé, `yamcps serve` indique qu’il faut en installer un.
Les secrets requis par tous les plugins chargés sont vérifiés : les valeurs
manquantes sont demandées dans un terminal, ou signalées sans terminal.
Les paramètres et variables d’environnement propres à un plugin sont décrits
par sa documentation.

## Configuration

Les connecteurs déclarent leurs secrets requis (token, username/password, etc.).
Lors d’un lancement depuis un terminal, yamcps inspecte **uniquement les connecteurs
sélectionnés**, consulte le coffre et demande les valeurs manquantes avec saisie
masquée, avant de démarrer le serveur :

```sh
yamcps serve --connector my-api
```

Les exemples avec `my-api` supposent un connecteur installé sous cet identifiant
et déclarant ses besoins. Pour un connecteur Basic Auth, yamcps demande par exemple `my-api/username` puis
`my-api/password`. Les valeurs présentes sont réutilisées sans nouvelle question.
`yamcps-demo` ne demande aucun secret.

Le coffre et sa clé sont créés automatiquement au premier enregistrement :

- Coffre : `~/.local/share/yamcps/secrets.yamcps-vault`.
- Clé séparée : `~/.config/yamcps/keys/master.yamcps-key`.

Les nouveaux répertoires finaux sont privés (`0700`), et les fichiers sont créés
avec accès réservé au propriétaire (`0600` sous POSIX). Sous Windows, restreindre
aussi leurs ACL au compte du service. Un coffre ou une clé existant seul, une
mauvaise clé ou un coffre altéré provoquent une erreur : rien n’est réinitialisé.

Les sous-commandes de `yamcps` sont détaillées ci-dessous. Utiliser
`yamcps <commande> --help` pour afficher leurs options.

### `connectors`

Lister les connecteurs installés sans importer leur code :

```sh
yamcps connectors list
```

### `secrets`

Gérer les identifiants dans le coffre chiffré :

| Action | Rôle |
| --- | --- |
| `init` | Créer le coffre et sa clé, sans écraser les fichiers existants |
| `set` | Saisir les secrets d’un connecteur ou modifier un champ avec `--name` |
| `list` | Afficher uniquement les noms des secrets enregistrés |
| `delete` | Supprimer un secret désigné par `--connector` et `--name` |

#### Configurer ou modifier un connecteur

L’assistant complet peut être ouvert directement :

```sh
yamcps secrets set --connector my-api
```

Il demande tous les champs déclarés par le connecteur. Une saisie vide conserve
une valeur déjà enregistrée ; pour un champ absent, une valeur non vide est
obligatoire. Les modifications ne sont enregistrées qu’après toutes les saisies.
Une interruption ou une fin d’entrée conserve le coffre inchangé.

Pour gérer les secrets individuellement :

```sh
yamcps secrets init
yamcps secrets list
yamcps secrets set --connector my-api --name token
yamcps secrets delete --connector my-api --name token
```

`init` reste facultatif et refuse d’écraser un coffre existant. `list` affiche
uniquement les noms. `set --name` permet de configurer un secret individuel, y
compris pour un ancien plugin qui ne déclare pas ses champs. Sans `--name`, le
connecteur doit être installé et implémenter `required_secrets()`.
Il n’existe pas de paramètre `--value` : la saisie se fait dans le terminal pour
ne pas placer les secrets dans l’historique ou les arguments du processus.

Les options `--vault` et `--key-file` sont disponibles pour toutes les actions
de `secrets` et pour `serve` :

```sh
yamcps secrets set --connector my-api --vault /chemin/secrets.yamcps-vault --key-file /autre/chemin/master.yamcps-key
yamcps serve --connector my-api --vault /chemin/secrets.yamcps-vault --key-file /autre/chemin/master.yamcps-key
```

Toujours fournir ces deux options ensemble, et utiliser les mêmes chemins pour
l’administration et le serveur. Les secrets sont chargés au démarrage ;
redémarrer après une modification.

#### Lancement depuis un client MCP

Un client MCP lance généralement le serveur sans terminal interactif. Si tous
les secrets sont présents, yamcps démarre normalement. Sinon, il échoue rapidement
avec une commande `yamcps secrets set --connector <nom>` à exécuter dans un terminal.
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
conserve la lecture des variables `YAMCPS_<CONNECTEUR>_<SECRET>` pour compatibilité.

#### Protection et exploitation du coffre

Le chiffrement authentifié AES-256-GCM utilise un nonce aléatoire de 96 bits à
chaque écriture et un tag de 128 bits. Une mauvaise clé ou une altération provoque
un refus de lecture. Ces choix s’appuient sur les principes des
[guides cryptographiques ANSSI](https://cyber.gouv.fr/reglementation/reglementation-identite-confiance-numerique/securite-echanges-voie-electronique/referentiel-general-de-securite/documents-referentiel-general-de-securite/)
et l’implémentation [AESGCM de cryptography](https://cryptography.io/en/latest/hazmat/primitives/aead/).
**yamcps n’est pas un produit qualifié ou certifié ANSSI et cette implémentation
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
Les fichiers `*.yamcps-key`, `*.yamcps-vault` et leurs verrous sont ignorés par Git.
Ne jamais placer de secrets dans les dossiers de skills, qui sont publiés via MCP.

### `configs`

Gérer les paramètres non secrets dans un fichier JSON local :

```sh
yamcps configs set --connector my-api
yamcps configs list
yamcps configs delete --connector my-api --name endpoint
```

`set` ouvre l’assistant pour les champs déclarés par le connecteur.
Pour enregistrer une valeur sans interaction :

```sh
yamcps configs set --connector my-api --name endpoint --value https://api.example.com
```

Le fichier par défaut est `~/.config/yamcps/config.json`. L’option `--config-file`
permet d’en choisir un autre. Ne jamais y enregistrer de secrets.
Voir les [règles de résolution](design.md#stockage-et-résolution) pour les valeurs
par défaut et les priorités.

### `models`

Un modèle sémantique est facultatif : l’installer uniquement si un plugin utilisé
en a besoin pour sa recherche sémantique. Consulter sa documentation pour choisir
un modèle compatible et le configurer. La recherche lexicale fonctionne sans modèle.

Installer l’extra `rag`, puis télécharger un modèle compatible avec le plugin :

```sh
python -m pip install 'yamcps[rag]'
yamcps models download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

L’extra `rag` fournit les dépendances de téléchargement et d’exécution du modèle.
L’argument `repo_id` désigne le dépôt du modèle ; `--revision` choisit sa version
et `--destination` son dossier local. La commande retourne le chemin du modèle téléchargé : le renseigner
dans la configuration du plugin, puis ingérer les documents dans un nouvel index.
Le téléchargement n’active pas le modèle automatiquement et le serveur ne
télécharge aucun modèle au démarrage.
Voir le [guide RAG](design.md#télécharger-un-modèle-pour-lutiliser-localement).

### `serve`

Lancer le serveur avec les configurations et secrets enregistrés :

```sh
yamcps serve
yamcps serve --connector my-api
yamcps serve --transport http --port 8000
```

| Option | Rôle |
| --- | --- |
| `--connector` | Sélectionner un connecteur ; option répétable |
| `--transport` | Choisir `stdio` (par défaut) ou `http` |
| `--port` | Choisir le port HTTP (8000 par défaut) |
| `--config-file` | Choisir le fichier JSON des paramètres non secrets |
| `--vault` et `--key-file` | Choisir ensemble le coffre et sa clé |

Voir le [démarrage](#démarrage) pour les commandes Windows et Unix
et la configuration du client MCP.

## Essayer le plugin de démonstration des secrets

Depuis la racine du dépôt :

```sh
python -m pip install -e . -e plugins/yamcps-demo-secrets
yamcps serve --connector demo-secrets
```

Le premier lancement demande un token, un nom d’utilisateur et un mot de passe.
Utiliser des valeurs fictives : ce plugin ne contacte aucune API. Après connexion
avec un client MCP, appeler `demo_secrets_status` sans argument pour vérifier le
chargement et la construction locale des authentifications Bearer et Basic.
L’outil retourne uniquement le statut et les schémas, jamais les valeurs.

```sh
yamcps secrets set --connector demo-secrets
yamcps secrets delete --connector demo-secrets --name token
yamcps serve --connector demo-secrets
```

La première commande ouvre l’assistant complet ; après la suppression du token,
le prochain lancement ne demande que ce champ. Le skill
`skill://demo-secrets-check/SKILL.md` décrit l’outil. Pour un client sans terminal,
exécuter d’abord la commande `secrets set` dans un terminal.
Voir le [README du plugin](../plugins/yamcps-demo-secrets/README.md).

## Consulter les skills

Le démonstrateur fournit `skill://demo-echo/SKILL.md`. Un client peut lire ce
fichier comme une ressource MCP. Les clients prenant en charge l’extension
`io.modelcontextprotocol/skills` peuvent découvrir les skills avec `skills/list`
et obtenir leur manifeste avec `skills/get`.

Les skills sont des instructions et des fichiers consultables : yamcps ne les
installe pas dans les agents et n’exécute pas leurs scripts. Leur utilisation
dépend des fonctionnalités du client. Redémarrer le serveur après toute
modification des fichiers ou installation d’un plugin.

## Résoudre les erreurs courantes

- **Commande introuvable** : activer l’environnement virtuel ou utiliser le chemin
  absolu de son exécutable `yamcps`.
- **Connecteur inconnu** : vérifier son installation dans le même environnement
  que yamcps et consulter `yamcps connectors list`.
- **Erreur de chargement ou d’enregistrement** : consulter stderr ; le diagnostic
  identifie le connecteur. Vérifier ses dépendances et sa configuration.
- **Port occupé** : choisir un autre port avec `--port` et adapter l’URL du client.
- **Skill absent** : vérifier que son connecteur est sélectionné et que le client
  sait lire les ressources MCP ou l’extension Skills.

HTTP est limité à la machine locale et ne fournit pas d’authentification dans
cette version. Ne pas l’exposer par un proxy public sans concevoir la protection
et l’authentification correspondantes.
