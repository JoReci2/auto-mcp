# Séparation des plugins

La migration part de `JoReci2/yamcps` au commit
`d444e3ae014a552edada3e4a7641e9d3b6fea54e`. Le code des plugins et leurs tests
métier sont extraits vers des dépôts autonomes ; l'historique antérieur reste
consultable dans le dépôt du moteur à ce commit.

| Distributions conservées | Dépôt | Chemin du package |
| --- | --- | --- |
| `yamcps-docs` | [yamcps-docs](https://github.com/JoReci2/yamcps-docs) | racine |
| `yamcps-sonarr`, `yamcps-radarr`, `yamcps-prowlarr` | [yamcps-arr](https://github.com/JoReci2/yamcps-arr) | `plugins/yamcps-<nom>` |
| `yamcps-extras` | [yamcps-extras](https://github.com/JoReci2/yamcps-extras) | racine |

Les noms de modules, entry points, identifiants, outils et URI MCP sont conservés.
Le package `yamcps-arr` n'est pas une nouvelle distribution : ce dépôt regroupe
les trois packages indépendants. `yamcps.rag`, les configs, le vault et le catalogue
restent dans le moteur. Seuls `yamcps-demo` et `yamcps-demo-secrets` restent locaux.

## Préparer et intégrer les branches

Les quatre dépôts utilisent la branche `refactor/plugins` pour cette migration.
Cloner cette branche pour les essais avant intégration :

```sh
git clone --branch refactor/plugins https://github.com/JoReci2/yamcps.git
git clone --branch refactor/plugins https://github.com/JoReci2/yamcps-docs.git
git clone --branch refactor/plugins https://github.com/JoReci2/yamcps-arr.git
git clone --branch refactor/plugins https://github.com/JoReci2/yamcps-extras.git
```

Intégrer les trois dépôts de plugins avant la branche du moteur. Après intégration,
les branches `main` deviennent les sources habituelles. Aucun sous-module, import
par chemin relatif ou clonage implicite n'est ajouté au démarrage du serveur.
Les sources du moteur ne sont pas nécessaires pour utiliser un plugin : son wheel
et une distribution compatible de yamcps suffisent. Pour développer l'ensemble,
installer depuis des clones voisins dans le même environnement Python :

```sh
python -m venv .venv
# Activer cet environnement selon le système.
python -m pip install -e './yamcps[dev]' -e ./yamcps/plugins/yamcps-demo -e ./yamcps/plugins/yamcps-demo-secrets
python -m pip install -e './yamcps-docs[dev,formats]' -e './yamcps-extras[dev]'
python -m pip install -e ./yamcps-arr/plugins/yamcps-sonarr -e ./yamcps-arr/plugins/yamcps-radarr -e ./yamcps-arr/plugins/yamcps-prowlarr
```

Une ancienne installation editable pointant sur `yamcps/plugins/yamcps-<nom>` doit
être réinstallée depuis sa nouvelle source. Ne pas changer les identifiants côté
client : `--connector docs`, `extras`, `sonarr`, `radarr`, `prowlarr` restent valides.
Sans sélection explicite, tous les plugins installés sont chargés comme auparavant.

## Configuration et données

Ne pas copier de vault, de secrets, d'index ou de modèle dans Git. Le fichier de
configuration et les chemins des données ne sont pas déplacés par cette migration.
Les clés `YAMCPS_*`, l'index par défaut et les commandes de configuration restent
identiques. Vérifier les chemins absolus si l'environnement ou le compte change.

## Tests et distributions

Chaque dépôt fournit ses propres instructions de contribution. Le moteur doit
passer ses tests sans installation de Docs, Extras ou ARR. Docs et ARR simulent
leurs API ; aucune infrastructure externe n'est nécessaire pour leurs tests.
Extras conserve un test croisé Docs optionnel : l'installer dans le même runtime
pour exercer cette intégration, en plus de sa suite autonome.

Construire et installer les wheels depuis un dossier hors des sources pour
vérifier découverte, handlers et ressources. Les cinq plugins ne sont plus présents
dans les archives du moteur. Le workflow de publication du moteur reste limité
à yamcps ; cette migration n'ajoute aucune publication ou release automatique.
