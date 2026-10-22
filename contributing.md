# Contribuer à yamcps

## Préparer son environnement

Python 3.12 ou supérieur est requis. Depuis la racine du dépôt :

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -e plugins/yamcps-demo -e plugins/yamcps-demo-secrets -e plugins/yamcps-sonarr -e plugins/yamcps-radarr -e plugins/yamcps-prowlarr -e plugins/yamcps-extras
python -m pip install radon bandit coverage
```

Les dépendances de développement actuelles incluent Ruff, mypy, pytest et les
outils de construction. Radon, Bandit et Coverage doivent pour l’instant
être installés séparément. Les vérifications de développement sont exécutées en local. Le workflow de
release décrit ci-dessous publie uniquement la distribution de base.

## Style et conventions

- Suivre PEP 8 ; utiliser Ruff pour le formatage et le lint, avec la configuration
  du dépôt (Python 3.12, longueur de ligne de 100 caractères).
- Nommer fonctions et variables en `snake_case`, classes en `PascalCase`,
  constantes en `UPPER_CASE` et modules en minuscules.
- Ajouter des annotations de types aux interfaces publiques et conserver la
  vérification stricte de mypy.
- Documenter toutes les fonctions et méthodes publiques avec des docstrings au
  format Google (`Args`, `Returns`, `Raises` lorsque pertinents). Ajouter des
  exemples d’utilisation quand ils clarifient le comportement.
- Garder le contrat des connecteurs minimal ; respecter les noms `yamcps-<nom>`,
  `yamcps_<nom>` et les préfixes d’outils décrits dans le document d’architecture.

Exemple de docstring :

```python
def normalize_message(message: str) -> str:
    """Remove surrounding whitespace from a message.

    Args:
        message: Text supplied by the caller.

    Returns:
        The message without surrounding whitespace.
    """
    return message.strip()
```

## Tests et couverture

Écrire des tests pour toute nouvelle fonctionnalité et des tests de régression
pour les corrections. Utiliser `unittest.TestCase` pour les nouveaux tests
synchrones et `unittest.IsolatedAsyncioTestCase` pour les tests asynchrones.
Les modules de tests portent le nom `test_*.py`.

La suite existante repose sur pytest et pytest-asyncio. Elle reste exécutée pendant
la transition ; pytest sait aussi collecter les classes unittest. Ne pas supprimer
ses tests ni présenter la migration comme terminée. Les nouveaux tests unittest
doivent également être exécutables avec le runner standard.

Maintenir une couverture de lignes **strictement supérieure à 80 %** sur le cœur
et tous les plugins du dépôt :

```sh
coverage run --source=yamcps,yamcps_demo,yamcps_demo_secrets,yamcps_sonarr,yamcps_radarr,yamcps_prowlarr,yamcps_extras -m pytest -q
coverage report --show-missing --fail-under=81
python -m unittest discover -s tests -p 'test_*.py'
```

Le runner unittest seul ne collecte pas les fonctions pytest existantes : son
succès ne remplace pas celui de la suite complète. Le test HTTP nécessite de
pouvoir ouvrir un port loopback.

## Vérifications avant une pull request

```sh
ruff format src plugins scripts tests
ruff check src plugins scripts tests
mypy src plugins/*/src scripts
radon cc src plugins/*/src scripts -s -a
bandit -r src plugins/*/src scripts
coverage run --source=yamcps,yamcps_demo,yamcps_demo_secrets,yamcps_sonarr,yamcps_radarr,yamcps_prowlarr,yamcps_extras -m pytest -q
coverage report --show-missing --fail-under=81
python -m build
python -m build plugins/yamcps-demo --outdir plugins/yamcps-demo/dist
python -m build plugins/yamcps-demo-secrets --outdir plugins/yamcps-demo-secrets/dist
python -m build plugins/yamcps-sonarr --outdir plugins/yamcps-sonarr/dist
python -m build plugins/yamcps-radarr --outdir plugins/yamcps-radarr/dist
python -m build plugins/yamcps-prowlarr --outdir plugins/yamcps-prowlarr/dist
python -m build plugins/yamcps-extras --outdir plugins/yamcps-extras/dist
```

Radon sert à repérer la complexité : privilégier des fonctions simples et
expliquer dans la PR toute complexité élevée ajoutée. Aucun seuil bloquant Radon
n’est configuré actuellement. Examiner les résultats Bandit ; corriger
les problèmes ou documenter précisément les exceptions justifiées. Signaler les
vérifications non exécutées au lieu de les déclarer réussies.

## Proposer une modification

1. Créer une branche dédiée et garder la modification centrée sur un objectif.
2. Ajouter ou mettre à jour les tests et la documentation concernée.
3. Exécuter les vérifications applicables et consulter le diff.
4. Ouvrir une pull request décrivant le problème, le comportement obtenu et les
   validations effectuées, avec leurs éventuelles limites.

Mettre à jour `README.md` pour les fonctionnalités générales,
`docs/user-manual.md` pour l’utilisation et `docs/design.md` pour les changements
d’architecture ou de contrat. Les instructions aux agents sont dans `AGENTS.md`.
Ne jamais committer de secrets ni de fichiers de configuration contenant des tokens.

## Publication du package de base

Le nom `yamcps` est réservé pour le projet. Les plugins `yamcps-<nom>` sont des
packages indépendants, installables depuis le dépôt, et **ne sont pas publiés**
par `.github/workflows/workflow.yaml`.

Configurer une fois le Trusted Publisher du projet PyPI `yamcps` avec :

- propriétaire GitHub : `JoReci2` ;
- dépôt : `yamcps` ;
- nom du workflow : `workflow.yaml` ;
- environnement : `pypi`.

Créer également l'environnement GitHub `pypi` dans les paramètres du dépôt.
Aucun token PyPI n'est requis : seul le job de publication reçoit le droit OIDC
`id-token: write`. Les opérations de construction n'ont pas ce droit.
Référence : https://docs.pypi.org/trusted-publishers/adding-a-publisher/ .

Pour une release, après revue et intégration sur `main` :

1. Mettre à jour `project.version` dans `pyproject.toml` et synchroniser la version
   annoncée par le serveur dans `src/yamcps/server.py`.
2. Construire et vérifier le package de base localement :

   ```sh
   python -m pip install build twine
   python -m build --outdir dist/base .
   python scripts/verify_release.py dist/base --tag v0.1.0
   python -m twine check --strict dist/base/*
   ```

3. Créer un tag `v<version>` sur un commit intégré dans `main`, puis publier la
   release GitHub correspondante. Adapter `v0.1.0` à la version choisie.

Le workflow s'exécute uniquement sur une release publiée, jamais sur une PR ou
un simple push. Il vérifie l'appartenance du commit à l'historique de `main`,
construit uniquement le projet racine, puis exige exactement un wheel et un
sdist dont les métadonnées déclarent `yamcps` et la version du tag. Il transmet
uniquement ces deux archives au job de publication. Les plugins ne sont ni
construits ni téléversés par ce workflow. Le sdist de base conserve les sources
des plugins pour les tests et le développement, sans les installer comme packages.

Les versions PyPI sont immuables : augmenter la version pour chaque publication.
Cette branche ne configure pas le compte PyPI et ne déclenche aucune publication.
