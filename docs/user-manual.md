# Manuel utilisateur

yamcps (Yet Another Model Context Protocole Server) expose les fonctionnalités de connecteurs Python à des clients
compatibles avec le Model Context Protocol. Python 3.12 ou supérieur est requis.

## Installation et démarrage

Depuis ce dépôt (les packages ne sont pas encore publiés) :

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -e plugins/yamcps-demo
yamcps connectors list
yamcps serve --connector demo
yamcps serve --connector demo --transport http --port 8000
```

Après publication du package de base sur PyPI, il pourra être installé avec
`python -m pip install yamcps`. Les plugins ne sont pas publiés par le workflow :
les installer séparément depuis leurs dossiers avec `pip install -e plugins/yamcps-<nom>`.

`stdio` est le transport par défaut ; ses logs vont sur stderr. HTTP utilise
Streamable HTTP à `http://127.0.0.1:8000/mcp`, avec les protections DNS rebinding
du SDK. Il reste local, sans authentification. Le serveur ne propose pas de
paramètre pour écouter sur une interface publique.

Exemple de configuration pour un client acceptant `mcpServers` :

```json
{
  "mcpServers": {
    "home": {
      "command": "/chemin/absolu/vers/.venv/bin/yamcps",
      "args": ["serve", "--connector", "demo"]
    }
  }
}
```

Adapter le chemin absolu de l’exécutable à l’environnement où sont installés
le cœur et les plugins.
Pour HTTP, configurer l’URL ci-dessus selon les options de votre client.

## Utiliser les fonctionnalités

Le connecteur `demo` expose l’outil `demo_echo`, qui retourne le message reçu.
Demander au client MCP d’appeler cet outil avec un argument `message` permet de
vérifier la connexion. Les outils disponibles dépendent des plugins sélectionnés.

Installer séparément chaque plugin `yamcps-<nom>`. Sans option `--connector`, tous
les plugins installés sont chargés par ordre alphabétique :

```sh
yamcps serve
yamcps serve --transport http
```

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

## Configurer les secrets des API

Les connecteurs déclarent leurs secrets requis (token, username/password, etc.).
Lors d’un lancement depuis un terminal, yamcps inspecte **uniquement les connecteurs
sélectionnés**, consulte le coffre et demande les valeurs manquantes avec saisie
masquée, avant de démarrer le serveur :

```sh
yamcps serve --connector my-api
```

Le connecteur `yamcps-my-api` doit être installé et déclarer ses besoins. Pour un
connecteur Basic Auth, yamcps demande par exemple `my-api/username` puis
`my-api/password`. Les valeurs présentes sont réutilisées sans nouvelle question.
`yamcps-demo` ne demande aucun secret.

Le coffre et sa clé sont créés automatiquement au premier enregistrement :

- Coffre : `~/.local/share/yamcps/secrets.yamcps-vault`.
- Clé séparée : `~/.config/yamcps/keys/master.yamcps-key`.

Les nouveaux répertoires finaux sont privés (`0700`), et les fichiers sont créés
avec accès réservé au propriétaire (`0600` sous POSIX). Sous Windows, restreindre
aussi leurs ACL au compte du service. Un coffre ou une clé existant seul, une
mauvaise clé ou un coffre altéré provoquent une erreur : rien n’est réinitialisé.

### Configurer ou modifier un connecteur

L’assistant complet peut être ouvert directement :

```sh
yamcps secrets set --connector my-api
```

Il demande tous les champs déclarés par le connecteur. Une saisie vide conserve
une valeur déjà enregistrée ; pour un champ absent, une valeur non vide est
obligatoire. Les modifications ne sont enregistrées qu’après toutes les saisies.
Une interruption ou une fin d’entrée conserve le coffre inchangé.

Les commandes existantes restent disponibles, avec les chemins par défaut :

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

Les options de chemin restent disponibles sur toutes les commandes :

```sh
yamcps secrets set --connector my-api --vault /chemin/secrets.yamcps-vault --key-file /autre/chemin/master.yamcps-key
yamcps serve --connector my-api --vault /chemin/secrets.yamcps-vault --key-file /autre/chemin/master.yamcps-key
```

Toujours fournir ces deux options ensemble, et utiliser les mêmes chemins pour
l’administration et le serveur. Les secrets sont chargés au démarrage ;
redémarrer après une modification.

### Lancement depuis un client MCP

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

### Protection et exploitation du coffre

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

## Utiliser Sonarr

Installer le plugin depuis le dépôt, puis configurer l’instance :

```sh
python -m pip install -e . -e plugins/yamcps-sonarr
yamcps secrets set --connector sonarr
yamcps serve --connector sonarr
```

L’assistant demande `url` (par exemple `http://localhost:8989`) et `api-key`
(disponible dans Sonarr, Settings → General → Security). Le préfixe d’un reverse
proxy est accepté, par exemple `https://sonarr.example.net/sonarr` ; ne pas ajouter
`/api/v3` à l’URL. Les deux champs sont conservés dans le coffre. Depuis un terminal,
le lancement direct `yamcps serve --connector sonarr` demande aussi les champs absents.
`yamcps serve` inclut Sonarr automatiquement dès que le plugin est installé.

Dans le client MCP :

1. Appeler `sonarr_system_status` pour vérifier la connexion.
2. Consulter les séries (`sonarr_list_series`, `sonarr_get_series`), leurs épisodes
   (`sonarr_list_episodes`), le calendrier (`sonarr_calendar`) ou la file paginée
   (`sonarr_queue`).
3. Pour un ajout, utiliser `sonarr_lookup_series`, `sonarr_quality_profiles` et
   `sonarr_root_folders`, puis fournir leurs identifiants à `sonarr_add_series`.

La recherche de catalogue ne modifie pas la bibliothèque. Les outils
`sonarr_search_series` et `sonarr_search_episodes`, ainsi que l’option d’ajout
`search_for_missing_episodes`, lancent une recherche active qui peut démarrer des
téléchargements. Par défaut, l’ajout surveille la série sans lancer de recherche.
Suivre une commande via `sonarr_command_status`, et les transferts via `sonarr_queue`.

Le plugin cible l’[API v3 officielle de Sonarr](https://sonarr.tv/docs/api/),
utilise `X-Api-Key`, et n’expose aucun outil de suppression ou de configuration
administrateur. Les identifiants Sonarr et TVDB sont distincts. Les erreurs ne
retournent pas les corps de réponse pouvant contenir des données sensibles.

Consulter le [guide du plugin Sonarr](../plugins/yamcps-sonarr/README.md) pour les
outils, paramètres, contraintes réseau et comportements en cas de timeout.
Le skill `skill://sonarr-manage/SKILL.md` est inclus dans son package.

## Utiliser Radarr

Installer le plugin indépendant puis configurer l’instance :

```sh
python -m pip install -e . -e plugins/yamcps-radarr
yamcps secrets set --connector radarr
yamcps serve --connector radarr
```

L’assistant demande `url` (par exemple `http://localhost:7878`) et `api-key`
(Radarr, Settings → General → Security). Un préfixe de reverse proxy est accepté,
sans suffixe `/api/v3`. Les paramètres sont conservés dans le coffre sous le
connecteur `radarr`, séparément des secrets Sonarr. Le lancement depuis un terminal
demande automatiquement les valeurs manquantes.

Utiliser `radarr_system_status` pour vérifier la connexion ; `radarr_list_movies`
et `radarr_get_movie` pour la bibliothèque ; `radarr_calendar` pour les sorties
et `radarr_queue` pour les transferts. Pour ajouter un film, utiliser
`radarr_lookup_movies`, puis choisir les identifiants de `radarr_quality_profiles`
et `radarr_root_folders` et les passer à `radarr_add_movie` avec le `tmdb_id` retenu.

Par défaut, le film est surveillé sans ajout de sa collection et sa disponibilité
minimale est `released`. La recherche de catalogue ne lance aucun téléchargement.
L’option `search_for_movie=true` à l’ajout ou l’outil `radarr_search_movies` peut
en déclencher un. Ce dernier utilise des identifiants **Radarr**, distincts des
identifiants **TMDB** ; suivre la commande avec `radarr_command_status`.

Pour utiliser Sonarr et Radarr ensemble, installer les deux plugins et lancer :

```sh
yamcps serve --connector sonarr --connector radarr
```

`yamcps serve` les inclut aussi automatiquement avec tous les plugins installés.
Le [guide Radarr](../plugins/yamcps-radarr/README.md) détaille les 11 outils et leurs
limites. Le skill `skill://radarr-manage/SKILL.md` est inclus dans son package.

## Utiliser Prowlarr

Installer le plugin indépendant et configurer ses deux champs :

```sh
python -m pip install -e . -e plugins/yamcps-prowlarr
yamcps secrets set --connector prowlarr
yamcps serve --connector prowlarr
```

L’assistant demande `url` (ex. `http://localhost:9696`, sans `/api/v1`) et `api-key`
(Prowlarr, Settings → General → Security). Un préfixe de reverse proxy est accepté.
Le coffre utilise un espace `prowlarr` distinct de Sonarr/Radarr. Le premier
lancement depuis un terminal demande aussi automatiquement les valeurs absentes.

Utiliser `prowlarr_system_status` pour vérifier la connexion, puis
`prowlarr_list_indexers`, `prowlarr_get_indexer`, `prowlarr_indexer_status` et
`prowlarr_categories` pour consulter indexeurs, capacités et catégories.
`prowlarr_search` accepte une requête, des identifiants d’indexeurs et de catégories,
un mode de recherche, une limite et un offset. Les indexeurs déterminent leurs
capacités de pagination ; il n’y a pas de garantie de page globale stable.

La recherche consomme les quotas des fournisseurs et peut alimenter l’historique,
mais **ne lance aucun téléchargement**. Ce plugin ne fournit aucune opération
d’envoi, d’ajout, de suppression ou de modification de configuration. Les URL de
releases, GUIDs et magnets sont omis pour ne pas révéler d’éventuelles passkeys.

Consulter `prowlarr_history` pour les événements paginés, `prowlarr_statistics`
pour les compteurs et temps de réponse, `prowlarr_health` pour les sources et
sévérités des contrôles, et `prowlarr_applications` pour les applications liées.
Le détail sensible des configurations, messages de santé et données d’historique
reste dans l’interface Prowlarr.

```sh
yamcps serve --connector sonarr --connector radarr --connector prowlarr
```

`yamcps serve` charge aussi tous les plugins installés automatiquement. Le
[guide Prowlarr](../plugins/yamcps-prowlarr/README.md) décrit les 10 outils et les
limites réseau. Le skill `skill://prowlarr-search/SKILL.md` est inclus.

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

## Migration depuis hmcp

Le projet devient **yamcps — Yet Another Model Context Protocole Server**.
Installer `yamcps` et les nouveaux packages `yamcps-<nom>` dans un environnement
virtuel neuf, puis remplacer les imports `hmcp` par `yamcps` et les commandes
`hmcp` / `python -m hmcp` par `yamcps` / `python -m yamcps`.

Les plugins doivent déclarer leurs entry points dans `yamcps.connectors` et
dépendre de `yamcps`. Les modules deviennent `yamcps_<nom>`. Les identifiants
métier (`sonarr`, `radarr`, etc.), noms des outils et URI de skills restent identiques.
Les anciens plugins déclarés sous `hmcp.connectors` ne sont pas chargés.

Les variables de configuration passent du préfixe `HMCP_` à `YAMCPS_` et les
chemins par défaut utilisent désormais `yamcps`. Reconfigurer les clients MCP
et les secrets via `yamcps secrets set --connector <nom>`. Conserver les anciens
fichiers de coffre et de clé en sauvegarde : aucune migration ou suppression
implicite n'est effectuée. La signature binaire historique `HMCPVAULT` est
conservée, mais les anciennes clés de secrets `HMCP_*` ne sont pas reconnues
comme des clés `YAMCPS_*` ; ne pas se contenter de déplacer l'ancien coffre.

## Corpus documentaires locaux

Installer et préparer explicitement un corpus avant de le consulter :

```sh
python -m pip install -e . -e 'plugins/yamcps-docs[formats]'
yamcps configs set --connector docs
yamcps-docs ingest /chemin/vers/manifest.json
yamcps serve --connector docs
```

Le [guide du plugin](../plugins/yamcps-docs/README.md) fournit le manifeste,
les formats, limites, outils et l'activation optionnelle des embeddings locaux.
Le manifeste est la liste complète des révisions à conserver dans un corpus :
une source retirée sera supprimée lors de la prochaine ingestion réussie.
Ne pas mettre de secret dans les contenus, les métadonnées ou le manifeste.
L'index contient les textes en clair et ne fournit pas de droits par utilisateur.

Dans un client stdio, le fichier JSON de configuration est lu sous le compte
local du serveur, sans export. Utiliser des chemins absolus vers
les fichiers de la machine qui exécute le serveur. Aucune indexation n'est
déclenchée au démarrage ; un index absent est signalé lors de l'appel documentaire.
Les autres connecteurs continuent de fonctionner.

## Capacité RAG facultative des connecteurs

Le RAG fait partie du package de base `yamcps`. Un plugin choisit de l'utiliser
avec `rag_config()` et `configure_rag(context)`, comme les autres capacités
facultatives. Les plugins existants restent utilisables sans modification. Le
[guide RAG](rag.md) décrit les hooks, les chemins, l'API Python et l'extra `rag`.
Aucun index n'est créé tant qu'une ingestion n'est pas effectuée. Pour les anciens
index documentaires, conserver leur chemin dans `YAMCPS_DOCS_INDEX`.

## Télécharger des modèles sémantiques locaux

```sh
python -m pip install -e '.[rag]'
yamcps models download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

La commande retourne le dossier local du modèle. Enregistrer ce chemin avec
`yamcps configs set --connector docs --name model --value /chemin/du/modele`,
ou le fournir dans `RagConfig.model_path`, puis ingérer les documents
dans un nouvel index. `--revision` fixe la version à télécharger et
`--destination` permet un dossier personnalisé, notamment pour un transfert hors
ligne. L'extra `models` suffit pour télécharger sans installer le moteur
d'embeddings. Les plugins sans RAG n'ont besoin d'aucun de ces extras.

Voir le [guide RAG](rag.md#télécharger-un-modèle-pour-lutiliser-localement) pour
le stockage, le manifeste, l'authentification et les limites. Le serveur ne
télécharge aucun modèle automatiquement.

## Configurer les plugins sans variables d’environnement

Le moteur prend en charge `required_configs()` et `configure_configs()` pour les
paramètres non secrets. Le fichier JSON local est distinct du vault chiffré.

```sh
yamcps configs set --connector docs
yamcps configs list
yamcps-docs ingest plugins/yamcps-docs/examples/manifest.json
yamcps serve --connector docs
```

L’assistant demande les champs `index` et `model`. Les valeurs enregistrées sont
réutilisées au démarrage et à l’ingestion, sans export. Pour une automatisation,
utiliser `--name model --value /chemin/absolu/du/modele`. Les tokens restent dans
le vault. Voir le [guide complet](configuration.md).

## Skills de développement avec yamcps-extras

```sh
python -m pip install -e . -e plugins/yamcps-extras
yamcps serve --connector extras
```

Ce plugin expose uniquement des skills et leurs modèles en ressources MCP :

- `extras-configure-agents` : AGENTS.md, ou AGENT.md selon le client ciblé ;
- `extras-develop-plugin` : créer et vérifier un plugin indépendant ;
- `extras-add-core-feature` : faire évoluer le moteur avec compatibilité et tests ;
- `extras-fix-core-bug` : reproduire et corriger un bug avec non-régression.

Lire par exemple `skill://extras-develop-plugin/SKILL.md`. Les clients compatibles
avec l'extension Skills peuvent découvrir les quatre guides automatiquement ;
les autres peuvent lire les ressources MCP standard. Le plugin n'installe aucun
skill chez le client et ne modifie pas vos fichiers. Son chargement ne confère
aucune capacité d'exécution supplémentaire au modèle.

Le [guide du plugin](../plugins/yamcps-extras/README.md) détaille les URI et les
modèles fournis. Pour le combiner à d'autres connecteurs :
`yamcps serve --connector extras --connector demo`. Sans sélection explicite,
les plugins installés sont chargés selon le comportement habituel.
