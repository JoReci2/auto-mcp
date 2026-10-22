# Contribuer à hmcp

## Préparer son environnement

Python 3.12 ou supérieur est requis. Depuis la racine du dépôt :

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]' -e plugins/hmcp-demo -e plugins/hmcp-demo-secrets -e plugins/hmcp-sonarr -e plugins/hmcp-radarr -e plugins/hmcp-prowlarr
python -m pip install -e packages/hmcp-rag-core -e 'plugins/hmcp-docs[formats]'
python -m pip install radon bandit coverage
```

Les dépendances de développement actuelles incluent Ruff, mypy, pytest et les
outils de construction. Radon, Bandit et Coverage doivent pour l’instant
être installés séparément. Les vérifications sont exécutées en local ; ne pas
mettre en place de GitHub Actions.

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
- Garder le contrat des connecteurs minimal ; respecter les noms `hmcp-<nom>`,
  `hmcp_<nom>` et les préfixes d’outils décrits dans le document d’architecture.

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
coverage run --source=hmcp,hmcp_demo,hmcp_demo_secrets,hmcp_sonarr,hmcp_radarr,hmcp_prowlarr,hmcp_rag_core,hmcp_docs -m pytest -q
coverage report --show-missing --fail-under=81
python -m unittest discover -s tests -p 'test_*.py'
```

Le runner unittest seul ne collecte pas les fonctions pytest existantes : son
succès ne remplace pas celui de la suite complète. Le test HTTP nécessite de
pouvoir ouvrir un port loopback.

## Vérifications avant une pull request

```sh
ruff format src plugins packages tests
ruff check src plugins packages tests
mypy src plugins/*/src packages/*/src
radon cc src plugins/*/src packages/*/src -s -a
bandit -r src plugins/*/src packages/*/src
coverage run --source=hmcp,hmcp_demo,hmcp_demo_secrets,hmcp_sonarr,hmcp_radarr,hmcp_prowlarr,hmcp_rag_core,hmcp_docs -m pytest -q
coverage report --show-missing --fail-under=81
python -m build
python -m build plugins/hmcp-demo --outdir plugins/hmcp-demo/dist
python -m build plugins/hmcp-demo-secrets --outdir plugins/hmcp-demo-secrets/dist
python -m build plugins/hmcp-sonarr --outdir plugins/hmcp-sonarr/dist
python -m build plugins/hmcp-radarr --outdir plugins/hmcp-radarr/dist
python -m build plugins/hmcp-prowlarr --outdir plugins/hmcp-prowlarr/dist
python -m build packages/hmcp-rag-core --outdir packages/hmcp-rag-core/dist
python -m build plugins/hmcp-docs --outdir plugins/hmcp-docs/dist
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

## Publication

Les noms prévus sont `hmcp`, `hmcp-demo`, `hmcp-demo-secrets`, `hmcp-sonarr`, `hmcp-radarr` et `hmcp-prowlarr`. Vérification du 21 octobre 2026 :
`hmcp` existe déjà sur PyPI (HTTP 200), tandis que `hmcp-demo` renvoie HTTP 404.
La publication de `hmcp` nécessite des droits sur ce projet existant ou une décision
de renommer la distribution. Aucun nom n’a été changé automatiquement.
Avant chaque première publication,
vérifier leur disponibilité et les droits du compte sur PyPI et TestPyPI ; une
réponse 404 ne réserve pas un nom. Ne jamais embarquer de token dans le dépôt.

Après validation et construction :

```sh
python -m pip install twine
python -m twine check dist/* plugins/hmcp-demo/dist/* plugins/hmcp-demo-secrets/dist/* plugins/hmcp-sonarr/dist/* plugins/hmcp-radarr/dist/* plugins/hmcp-prowlarr/dist/*
python -m twine upload --repository testpypi dist/* plugins/hmcp-demo/dist/* plugins/hmcp-demo-secrets/dist/* plugins/hmcp-sonarr/dist/* plugins/hmcp-radarr/dist/* plugins/hmcp-prowlarr/dist/*
```

Tester les wheels TestPyPI dans un environnement vierge (installer les dépendances
SDK depuis PyPI puis les six packages TestPyPI avec `--no-deps`). Une fois validés :

```sh
python -m twine upload dist/* plugins/hmcp-demo/dist/* plugins/hmcp-demo-secrets/dist/* plugins/hmcp-sonarr/dist/* plugins/hmcp-radarr/dist/* plugins/hmcp-prowlarr/dist/*
```

Aucune publication automatique n’est configurée. Versions initiales `0.1.0` ; le
SDK est borné à `mcp>=2.3,<3`. Toute évolution incompatible du contrat doit faire
évoluer sa version et les contraintes des plugins.
