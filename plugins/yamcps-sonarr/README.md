# yamcps-sonarr

Connecteur Sonarr pour yamcps : consultation de la bibliothèque, épisodes,
calendrier et file de téléchargements, recherche de séries et ajout.
Utilise l’[API v3 officielle](https://sonarr.tv/docs/api/) de Sonarr v3/v4.

Depuis la racine du dépôt :

```sh
python -m pip install -e . -e plugins/yamcps-sonarr
yamcps secrets set --connector sonarr
yamcps serve --connector sonarr
```

L’assistant demande deux champs, conservés dans le coffre chiffré :

- `url` : URL de l’instance, par exemple `http://localhost:8989` ou
  `https://sonarr.example.net/sonarr` avec un préfixe de reverse proxy.
  Ne pas ajouter `/api/v3`, de paramètres de requête ou d’identifiants à l’URL.
- `api-key` : clé API de Sonarr, disponible dans Settings → General → Security.
  Elle est envoyée uniquement dans l’en-tête `X-Api-Key`, jamais en paramètre MCP.

`yamcps serve` charge aussi ce plugin automatiquement s’il est installé. Depuis un
client MCP sans terminal, configurer les champs au préalable sous le même compte.
La configuration ne contacte pas Sonarr : `sonarr_system_status` vérifie la connexion.

## Outils

| Outil | Fonction |
| --- | --- |
| `sonarr_system_status` | Version et état de l’instance |
| `sonarr_list_series` | Bibliothèque, filtre facultatif sur le titre |
| `sonarr_get_series` | Détails d’une série par identifiant Sonarr |
| `sonarr_list_episodes` | Épisodes d’une série, saison facultative |
| `sonarr_calendar` | Épisodes diffusés entre deux dates |
| `sonarr_queue` | File de téléchargements, avec pagination |
| `sonarr_lookup_series` | Recherche dans le catalogue par titre ou `tvdb:<id>` |
| `sonarr_quality_profiles` | Profils qualité existants |
| `sonarr_root_folders` | Dossiers racines existants |
| `sonarr_add_series` | Ajout à partir d’un identifiant TVDB, d’un profil et d’un dossier racine |
| `sonarr_search_series` | Recherche active d’épisodes pour une série existante |
| `sonarr_search_episodes` | Recherche active d’épisodes par identifiants Sonarr |
| `sonarr_command_status` | Suivi d’une recherche asynchrone par identifiant de commande |

Les identifiants Sonarr (`series_id`, `episode_ids`) diffèrent des identifiants
TVDB (`tvdb_id`). Pour ajouter : rechercher la série, lister profils et dossiers,
puis fournir `tvdb_id`, `quality_profile_id` et `root_folder_id`. Le plugin récupère
les métadonnées et vérifie que le profil et le dossier existent. Une série déjà
présente n’est pas ajoutée à nouveau. Sonarr reste l’autorité de validation finale.

Par défaut, une série ajoutée est surveillée avec ses saisons, les dossiers de
saison sont activés et aucune recherche initiale n’est déclenchée. Le paramètre
`search_for_missing_episodes=true` déclenche la recherche à l’ajout. Les outils
`sonarr_search_*` contactent les indexeurs et peuvent lancer des téléchargements :
ils ne correspondent pas à une simple consultation du catalogue. Leur résultat
est une commande en file, pas une confirmation de téléchargement terminé.

## Connexion et limites

Les appels sont asynchrones, avec timeout de 15 secondes (connexion : 5 secondes),
vérification TLS activée, sans suivi des redirections ni proxy d’environnement.
Utiliser HTTPS pour protéger la clé sur le réseau ; HTTP reste disponible pour
une instance locale ou un réseau privé maîtrisé. Aucun paramètre ne désactive TLS.
Il n’y a pas de retry automatique, notamment sur les ajouts et recherches.

Les erreurs distinguent authentification, ressource absente, validation, timeout
et indisponibilité sans retourner le corps d’erreur de Sonarr ou la clé API.
En cas de timeout après un ajout, vérifier la bibliothèque avant de réessayer.
Les réponses sont limitées aux champs utiles ; les configurations des indexeurs,
clients de téléchargement et secrets du serveur ne sont pas exposés.
Aucun outil de suppression, redémarrage ou modification de configuration n’est fourni.
Le skill `sonarr-manage` est embarqué dans la distribution.
