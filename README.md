# yamcps — Yet Another Model Context Protocole Server

**yamcps** est un serveur MCP Python extensible qui expose les fonctionnalités de
connecteurs à des assistants compatibles avec le Model Context Protocol.
Python 3.12 ou supérieur est requis.

```mermaid
flowchart LR
    assistant["Assistant compatible MCP"]
    subgraph yamcps [yamcps]
        server["Serveur MCP"]
        connectors["Connecteurs installés"]
        server <--> connectors
    end
    services["Services et API"]
    documents["Documents et données"]
    assistant <-->|stdio ou HTTP local| server
    connectors <--> services
    connectors <--> documents
```

Vous installez les connecteurs adaptés à vos sources. yamcps expose leurs outils,
ressources et prompts à votre assistant via une interface MCP commune.

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Quickstart](#quickstart)
- [Connecter un client MCP](#connecter-un-client-mcp)
- [Configuration et commandes](#configuration-et-commandes)
- [Consulter les skills](#consulter-les-skills)
- [Résoudre les erreurs courantes](#résoudre-les-erreurs-courantes)
- [Dépôts des plugins](#dépôts-des-plugins)
- [Développement](#développement)

## Fonctionnalités

- Connecteurs indépendants : outils, ressources et prompts MCP.
- Skills et fichiers associés accessibles via MCP.
- Configuration locale en JSON et coffre chiffré avec saisie interactive des secrets.
- RAG facultatif : indexation et recherche lexicale ou sémantique locale.
- Transports stdio et Streamable HTTP ; accès distant protégé par OAuth.

## Quickstart

Python 3.12 ou supérieur et un client compatible MCP sont requis.
Créer un environnement virtuel, puis installer yamcps :

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

Installer ensuite au moins un connecteur dans ce même environnement, selon les
instructions de son dépôt. Yamcps fournit le serveur ; les connecteurs fournissent
les outils et ressources utilisables par votre assistant.

Les commandes suivantes supposent un environnement activé. Sinon, remplacer
`yamcps` par `.\.venv\Scripts\yamcps.exe` sous Windows ou `.venv/bin/yamcps`
sous Unix, et `python` par l’exécutable Python du même environnement.

```sh
yamcps connectors list
# Si le connecteur demande des secrets ou des paramètres obligatoires :
yamcps secrets set --connector <identifiant>
yamcps configs set --connector <identifiant>
```

Remplacer `<identifiant>` par le nom affiché pour le connecteur installé.
Configurer ensuite le client avec l’un des transports ci-dessous.

## Connecter un client MCP

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
dans un terminal avant de lancer le client : voir la [configuration](#configuration-et-commandes).

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

HTTP reste local par défaut, avec les protections DNS rebinding du SDK.

### HTTP distant avec OAuth

yamcps joue le rôle de **serveur de ressources OAuth**. Un serveur d’autorisation
externe gère les comptes, la connexion, le consentement et la délivrance des jetons.
Configurer ce serveur pour le client MCP (Authorization Code avec PKCE), avec
l’audience exacte `https://mcp.example.com/mcp` et le scope `mcp:access`.
Il doit publier ses métadonnées OAuth et accepter les clients enregistrés auprès de lui.
L’enregistrement dynamique dépend du fournisseur ; yamcps ne le fournit pas.

Créer `oauth.json` avec uniquement des paramètres publics :

```json
{
  "issuer_url": "https://auth.example.com",
  "resource_url": "https://mcp.example.com/mcp",
  "public_key_file": "issuer-public.pem",
  "required_scopes": ["mcp:access"]
}
```

Exporter la **clé publique RSA** du serveur d’autorisation au format PEM dans
`issuer-public.pem`, à côté du fichier JSON. Aucun secret client ni clé privée
n’est requis par yamcps. Les jetons d’accès doivent être signés en RS256 et contenir
`iss`, `aud`, `exp`, `iat`, `sub`, `client_id` et `scope` (chaîne séparée par des espaces).
L’émetteur doit correspondre exactement à `issuer_url`, y compris le slash final éventuel.

```sh
yamcps serve --transport http --host 0.0.0.0 --port 8000 --oauth-config oauth.json
```

Placer yamcps derrière un reverse proxy HTTPS : conserver le chemin `/mcp` et le
`Host` public, transmettre `Authorization` et laisser passer
`/.well-known/oauth-protected-resource/mcp`. Limiter le port 8000 au proxy par
pare-feu ou réseau privé. Le serveur Python ne termine pas TLS lui-même.
Le proxy doit supporter les réponses SSE et éviter leur mise en tampon.

Le client MCP utilise `https://mcp.example.com/mcp` et découvre le serveur
d’autorisation depuis la réponse 401. Sans jeton valide, les appels MCP sont refusés.
Les interfaces non locales exigent `--oauth-config` ; cette option est refusée en stdio.

Cette première version valide les jetons localement : pas de JWKS automatique,
d’introspection ni de révocation immédiate. Utiliser des jetons courts ; remplacer
le PEM et redémarrer lors d’une rotation de clé. Les utilisateurs autorisés accèdent
aux mêmes connecteurs et aux mêmes données : OAuth ne fournit pas d’isolation
par utilisateur ni de permissions par outil. La compatibilité du parcours de connexion
avec chaque client dépend des capacités OAuth de celui-ci et du fournisseur choisi.

## Configuration et commandes

Les exemples avec `my-api` supposent un connecteur installé sous cet identifiant.
Afficher l’aide avec `yamcps <commande> --help`.

### `connectors`

```sh
yamcps connectors list
```

Afficher les connecteurs disponibles. Sans connecteur installé, le serveur
ne peut pas démarrer.

### `secrets`

Les secrets sont conservés dans un coffre local chiffré. Depuis un terminal,
le démarrage demande uniquement les valeurs manquantes des connecteurs chargés.
Depuis un client MCP sans terminal, les configurer au préalable :

```sh
yamcps secrets set --connector my-api
yamcps secrets set --connector my-api --name token
yamcps secrets list
yamcps secrets delete --connector my-api --name token
```

`set` demande les valeurs avec saisie masquée ; une saisie vide conserve une valeur
existante. Les modifications sont enregistrées une fois toutes les saisies réussies.
`list` affiche uniquement les noms. Aucun secret ne se transmet avec `--value`.

Le coffre et sa clé sont créés au premier enregistrement :

- Coffre : `~/.local/share/yamcps/secrets.yamcps-vault`.
- Clé : `~/.config/yamcps/keys/master.yamcps-key`.

`yamcps secrets init` permet aussi de les créer explicitement, sans écraser les
fichiers existants. Pour choisir d’autres emplacements, fournir ensemble
`--vault <chemin>` et `--key-file <chemin>` aux commandes `secrets` et `serve`.
Utiliser les mêmes chemins et le même compte local pour configurer et démarrer
le serveur. Redémarrer après une modification.

Sauvegarder la clé séparément du coffre : sa perte rend les secrets irrécupérables.
Protéger les accès à ces fichiers, y compris leurs ACL sous Windows. Ne jamais
placer de secrets dans Git ou dans les dossiers de skills accessibles au client.
Le chiffrement au repos ne protège pas contre un processus ayant accès au coffre
et à sa clé. Yamcps n’est pas un produit qualifié ou certifié ANSSI.

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
Une valeur enregistrée prévaut sur une variable d’environnement, puis sur le
défaut du connecteur. Supprimer une valeur rétablit cette résolution sans effacer
les fichiers qu’elle désigne. Redémarrer le serveur après une modification.

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
et `--destination` son dossier local. La commande retourne le chemin du modèle téléchargé : le
renseigner
dans la configuration du plugin, puis ingérer les documents dans un nouvel index.
Le téléchargement n’active pas le modèle automatiquement et le serveur ne
télécharge aucun modèle au démarrage.
Pour un transfert hors ligne, télécharger le modèle sur une machine connectée,
puis copier son dossier vers la machine du serveur. Installer aussi `yamcps[rag]`
sur cette machine et configurer le plugin avec le nouveau chemin local.

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
| `--host` | Interface HTTP (`127.0.0.1` par défaut) ; OAuth requis hors loopback |
| `--oauth-config` | Configuration OAuth JSON pour HTTP |
| `--port` | Choisir le port HTTP (8000 par défaut) |
| `--config-file` | Choisir le fichier JSON des paramètres non secrets |
| `--vault` et `--key-file` | Choisir ensemble le coffre et sa clé |

Sans `--connector`, tous les connecteurs installés sont chargés par ordre
alphabétique. Répéter cette option pour en sélectionner plusieurs, dans l’ordre
fourni. Redémarrer le serveur après l’installation d’un connecteur.

## Consulter les skills

Les skills fournis par les connecteurs sont consultables comme ressources MCP. Les clients prenant
en charge l’extension
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

Pour un accès Internet, utiliser le mode OAuth et un reverse proxy HTTPS décrit ci-dessus.

## Dépôts des plugins

| Plugins | Dépôt |
| --- | --- |
| Documents / RAG métier | [yamcps-docs](https://github.com/JoReci2/yamcps-docs) |
| Sonarr, Radarr et Prowlarr | [yamcps-arr](https://github.com/JoReci2/yamcps-arr) |
| Skills de développement | [yamcps-extras](https://github.com/JoReci2/yamcps-extras) |

## Développement

Le [guide de contribution](CONTRIBUTING.md) regroupe les informations destinées
aux développeurs : architecture, API, contrats des connecteurs et validations.


### Secrets selon les fonctionnalités activées

À partir de yamcps 0.4.0, un connecteur peut demander seulement les secrets
nécessaires à sa configuration. Renseigner d'abord sa sélection de fonctionnalités :

```sh
yamcps configs set --connector arr --name enabled-services --value sonarr,seerr --config-file /chemin/config.json
yamcps secrets set --connector arr --config-file /chemin/config.json
yamcps serve --connector arr --config-file /chemin/config.json
```

Ces paramètres dépendent du plugin ; le moteur ne définit aucun service ARR.
Sans sélection obligatoire, un démarrage sans terminal échoue avant de demander
un secret. `secrets set --name` refuse les secrets inactifs. Les secrets des
fonctionnalités désactivées restent conservés et sont réutilisés à leur réactivation.
Redémarrer après toute modification. Le [contrat développeur](CONTRIBUTING.md#secrets-conditionnels-à-partir-de-yamcps-040)
décrit le hook et son ordre d'appel. Cette évolution cible la prochaine version 0.4.0.
