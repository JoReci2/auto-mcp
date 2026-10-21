# hmcp-prowlarr

Connecteur indépendant pour l’[API v1 de Prowlarr](https://prowlarr.com/docs/api/),
limité à la consultation et à la recherche. Aucun envoi au téléchargement,
changement de configuration ou modification d’indexeur n’est exposé.

```sh
# Depuis la racine du dépôt
python -m pip install -e . -e plugins/hmcp-prowlarr
hmcp secrets set --connector prowlarr
hmcp serve --connector prowlarr
```

L’assistant demande `url` (ex. `http://localhost:9696`) et `api-key`, disponible
dans Prowlarr, Settings → General → Security. Un préfixe de reverse proxy est
accepté, sans suffixe `/api/v1`, paramètres ou identifiants dans l’URL. Les deux
champs sont conservés dans le coffre ; la clé est envoyée dans `X-Api-Key`.
La configuration ne contacte pas l’instance : `prowlarr_system_status` vérifie la
connexion. Depuis un client MCP sans terminal, préconfigurer les secrets.

`hmcp serve` charge ce plugin automatiquement s’il est installé. Il peut aussi
être sélectionné avec les autres services :

```sh
hmcp serve --connector sonarr --connector radarr --connector prowlarr
```

## Outils

| Outil | Fonction |
| --- | --- |
| `prowlarr_system_status` | Version et informations publiques d’exécution |
| `prowlarr_list_indexers` | Métadonnées et capacités des indexeurs configurés |
| `prowlarr_get_indexer` | Métadonnées d’un indexeur par identifiant |
| `prowlarr_indexer_status` | Derniers échecs et désactivations temporaires |
| `prowlarr_categories` | Identifiants et hiérarchie des catégories |
| `prowlarr_search` | Recherche de releases, sans téléchargement |
| `prowlarr_history` | Historique paginé, filtrable par indexeurs |
| `prowlarr_health` | Sources et sévérité des contrôles de santé |
| `prowlarr_statistics` | Compteurs et temps de réponse par indexeur |
| `prowlarr_applications` | Noms et niveau de synchronisation des applications liées |

Pour rechercher, consulter les indexeurs et les catégories puis utiliser
`prowlarr_search(query="Example", indexer_ids=[1], category_ids=[2000])` avec des
identifiants réellement disponibles. Les modes `search`, `tvsearch`, `movie`,
`music` et `book` dépendent des capacités de chaque indexeur. `limit` (1 à 100)
et `offset` sont transmis à Prowlarr : les capacités de pagination et le nombre
total de résultats varient selon les indexeurs, sans garantie de page globale
stable. La recherche contacte les fournisseurs, consomme leurs quotas et peut
alimenter l’historique Prowlarr ; aucun téléchargement n’est lancé.

Les résultats contiennent titre, indexeur, taille, date, protocole, disponibilité
des seeders/leechers et catégories. Les GUIDs, URL de téléchargement, magnets et
liens de détails sont omis : ils peuvent contenir des passkeys de trackers.
Les champs de configuration `fields`, les presets, données brutes d’historique,
messages de santé et statistiques par hôte/user-agent ne sont jamais retournés.
Le diagnostic détaillé de ces éléments se consulte dans l’interface Prowlarr.

## Connexion et limites

Le client n’utilise que GET, avec une connexion limitée à 5 secondes, un timeout
de 15 secondes pour les métadonnées et 60 secondes pour la recherche. TLS est
vérifié, les redirections et proxies d’environnement sont désactivés et aucune
requête n’est retentée automatiquement. Utiliser HTTPS pour protéger la clé sur
le réseau ; HTTP reste possible pour une instance locale ou un réseau privé maîtrisé.

Les erreurs de transport et d’API sont retournées sans corps brut ni credentials.
Le plugin n’importe ni Sonarr ni Radarr et reste installable seul avec hmcp.
Le skill `prowlarr-search` est inclus dans le package. La compatibilité avec une
instance réelle reste à vérifier après configuration ; les tests utilisent une
API simulée basée sur le schéma officiel.
