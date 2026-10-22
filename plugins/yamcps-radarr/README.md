# yamcps-radarr

Connecteur Radarr indépendant pour yamcps : bibliothèque de films, calendrier de
sorties, file de téléchargements, recherche de catalogue, ajout et recherche active.
Il utilise l’[API v3 officielle](https://radarr.video/docs/api/).

Depuis la racine du dépôt :

```sh
python -m pip install -e . -e plugins/yamcps-radarr
yamcps secrets set --connector radarr
yamcps serve --connector radarr
```

L’assistant demande `url` (ex. `http://localhost:7878`) et `api-key`, disponible
dans Radarr, Settings → General → Security. Un préfixe de reverse proxy est
accepté (`https://radarr.example.net/radarr`), sans ajouter `/api/v3`, paramètres
ou identifiants à l’URL. Les champs sont conservés dans le coffre chiffré ; la clé
est envoyée uniquement dans `X-Api-Key`, jamais dans les arguments des outils.

`yamcps serve` charge automatiquement ce plugin s’il est installé. Pour combiner
explicitement les deux services :

```sh
yamcps serve --connector sonarr --connector radarr
```

Configurer préalablement les secrets dans un terminal pour un client MCP sans
terminal. La configuration n’effectue aucun appel réseau ; vérifier la connexion
avec `radarr_system_status`.

## Outils

| Outil | Fonction |
| --- | --- |
| `radarr_system_status` | Version et état de l’instance |
| `radarr_list_movies` | Bibliothèque, filtre facultatif sur le titre |
| `radarr_get_movie` | Détails d’un film par identifiant Radarr |
| `radarr_calendar` | Sorties entre deux dates explicites |
| `radarr_queue` | File de téléchargements avec pagination |
| `radarr_lookup_movies` | Recherche de catalogue par titre ou `tmdb:<id>` |
| `radarr_quality_profiles` | Profils qualité existants |
| `radarr_root_folders` | Dossiers racines existants |
| `radarr_add_movie` | Ajout par identifiant TMDB, profil qualité et dossier racine |
| `radarr_search_movies` | Recherche active pour des identifiants Radarr existants |
| `radarr_command_status` | Suivi d’une recherche asynchrone |

Les identifiants Radarr (`movie_id`, `movie_ids`) diffèrent des identifiants TMDB
(`tmdb_id`). Avant un ajout, rechercher le film, lister profils et dossiers, puis
fournir `tmdb_id`, `quality_profile_id` et `root_folder_id`. Le plugin vérifie
l’absence du film et l’existence du profil et du dossier avant l’unique POST.
Radarr reste l’autorité finale en cas de validation ou d’ajout concurrent.

Par défaut, le film est surveillé, sa disponibilité minimale est `released`,
aucune recherche initiale n’est lancée et sa collection n’est pas ajoutée.
`minimum_availability` accepte `announced`, `inCinemas` ou `released`.
`search_for_movie=true` ou `radarr_search_movies` peut lancer des téléchargements.
Un identifiant de commande en file ne signifie pas que le téléchargement est terminé.

## Connexion et limites

Timeout de 15 secondes (connexion : 5 secondes), TLS vérifié, aucun suivi de
redirection, proxy d’environnement ou retry automatique. HTTPS protège la clé
sur le réseau ; HTTP reste possible pour une instance locale ou un réseau privé
maîtrisé. Aucun paramètre ne permet de désactiver TLS.

Les erreurs d’authentification, validation, ressource absente ou réseau sont
signalées sans corps d’erreur brut ni clé API. Après un timeout sur un ajout,
consulter la bibliothèque avant de réessayer. Les réponses sont projetées sur des
champs utiles, sans configuration d’indexeur ou de client de téléchargement.
Aucun outil de suppression ou d’administration système n’est fourni.
Le skill `radarr-manage` est inclus dans la distribution. Ce package ne dépend
pas de `yamcps-sonarr` et peut être installé seul avec yamcps.
