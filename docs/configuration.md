# Configuration en clair des plugins

Les paramètres non secrets (chemins, modes, noms, adresses sans credentials) sont
stockés séparément des secrets : JSON local pour les configs, vault chiffré pour
les mots de passe et tokens. Les valeurs de configuration de cette V1 sont des
chaînes de caractères.

## Utilisation sans export

Installer le plugin dans le même environnement que yamcps, puis lancer :

```sh
yamcps configs set --connector docs
```

L'assistant demande les champs déclarés par le plugin. Pour docs :

- `index` : chemin de la base SQLite ; vide = chemin par défaut du moteur ;
- `model` : dossier local du modèle ; vide = recherche lexicale.

Une saisie vide conserve une valeur existante ou son défaut. Pour effacer
explicitement le modèle et sélectionner le mode lexical, enregistrer une chaîne vide :

```sh
yamcps configs set --connector docs --name model --value ""
```

Les paramètres peuvent également être enregistrés sans interaction :

```sh
yamcps configs set --connector docs --name model --value /chemin/absolu/du/modele
yamcps configs set --connector docs --name index --value /chemin/absolu/docs-hybrid.sqlite3
yamcps configs list
yamcps-docs ingest plugins/yamcps-docs/examples/manifest.json
yamcps serve --connector docs
```

Utiliser des chemins absolus pour que le client stdio et l'ingestion retrouvent
les mêmes fichiers, même avec des répertoires de travail différents. Après un
changement de modèle, choisir un nouvel index et réingérer les sources.
Télécharger un modèle avec `yamcps models download` ne l'active pas à lui seul.

Le fichier par défaut est `~/.config/yamcps/config.json`, créé seulement lors d'une
écriture. Exemple de contenu, entièrement lisible :

```json
{
  "YAMCPS_DOCS_INDEX": "/chemin/absolu/docs-hybrid.sqlite3",
  "YAMCPS_DOCS_MODEL": "/chemin/absolu/du/modele"
}
```

Ces clés sont des identifiants dans un fichier JSON, pas des commandes `export`.
La priorité est : valeur enregistrée, ancienne variable d'environnement si la
clé est absente, puis défaut déclaré. Une valeur vide enregistrée prévaut donc
sur une variable d'environnement. Les anciens exports restent compatibles,
mais aucun n'est nécessaire pour le parcours ci-dessus.

Pour supprimer une valeur enregistrée :

```sh
yamcps configs delete --connector docs --name model
```

La suppression rétablit la résolution environnement/défaut ; elle ne supprime
ni le modèle téléchargé ni les données de l'index.

## Fichier explicite et clients MCP

Les commandes de gestion et le serveur acceptent `--config-file`. Pour docs,
l'ingestion accepte le même paramètre :

```sh
yamcps configs set --connector docs --config-file /projet/yamcps.json
yamcps-docs ingest /projet/manifest.json --config-file /projet/yamcps.json
yamcps serve --connector docs --config-file /projet/yamcps.json
```

Pour le fichier par défaut, aucune configuration `env` du client MCP n'est requise.
Le serveur et la commande d'ingestion doivent s'exécuter sous le même compte
local, ou recevoir explicitement le même fichier. Redémarrer le serveur après
une modification de configuration ; il n'y a pas de rechargement à chaud.

## Contrat pour les auteurs de plugins

Déclarer les deux hooks synchrones suivants, en complément du contrat minimal :

```python
from yamcps import ConfigSpec, ConnectorConfigs


class ExampleConnector:
    id = "example"

    def required_configs(self) -> list[ConfigSpec]:
        return [
            ConfigSpec("endpoint", "Adresse du service sans identifiants"),
            ConfigSpec("mode", "Mode de fonctionnement", default="local"),
        ]

    def configure_configs(self, configs: ConnectorConfigs) -> None:
        self.endpoint = configs.require("endpoint")
        self.mode = configs.get("mode")

    # Implémenter également register(server) selon le contrat du connecteur.
```

Sans défaut (`default=None`), un champ exige une valeur non vide. Un défaut
chaîne rend le champ facultatif ; `default=""` permet de désactiver une option.
Les noms suivent le kebab-case et sont uniques par connecteur. L'assistant explicite
propose les champs déclarés, même ceux possédant un défaut.

Au démarrage, le moteur ne charge que les plugins sélectionnés, résout les configs
et demande uniquement les champs obligatoires manquants si un terminal est
présent. Sans terminal, il échoue avec une commande de configuration ; il ne lit
jamais le flux MCP comme une réponse à l'assistant. Le lot de valeurs saisi est
écrit seulement si toutes les saisies réussissent. Les valeurs déjà enregistrées
ne sont pas redemandées.

L'injection se fait après `configure(secrets)` et avant les hooks RAG, les skills
et les handlers. Les plugins sans ces hooks restent inchangés. Les appels Python
peuvent fournir `create_server(config_values={...})` pour remplacer fichier et
environnement, ou un `ConfigStore` explicite ; ces deux options sont exclusives.

Le stockage utilise un verrou d'écriture et un remplacement atomique du fichier.
Les commandes de configuration ne sont pas des outils MCP. Les vues par plugin
limitent la lecture par nom mais ne sont pas une sandbox : les plugins restent
exécutés comme du code de confiance. Ne jamais enregistrer de token ou mot de
passe dans ce fichier, dans `--value` ou dans les exemples ; utiliser le vault.
