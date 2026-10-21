# Consignes du dépôt hmcp

## Projet et repères

hmcp (Home MCP) est un serveur MCP Python ≥ 3.12 distribué avec Hatchling.
Les connecteurs sont des packages indépendants nommés `hmcp-<nom>`.
Lire `docs/design.md` avant de modifier l’architecture ou le contrat des plugins,
`docs/user-manual.md` pour le comportement utilisateur et `contributing.md` pour
le workflow détaillé de contribution.

- `src/hmcp` : cœur, CLI, découverte des plugins, registre et catalogue de skills.
- `plugins/hmcp-demo` : exemple de distribution autonome et skill embarqué.
- `plugins/hmcp-demo-secrets` : démo du coffre interactif, token et Basic Auth sans API externe.
- `tests` : tests du cœur et intégrations MCP.
- `pyproject.toml` : versions Python, dépendances et configuration des outils.

## Règles d’implémentation

- Suivre PEP 8 et utiliser Ruff pour le formatage et le lint. Respecter la
  configuration du dépôt, notamment la longueur de ligne de 100 caractères.
- Fonctions et variables : `snake_case` ; classes : `PascalCase` ; constantes :
  `UPPER_CASE` ; modules : minuscules, avec underscores si nécessaire.
- Annoter les interfaces publiques et conserver la compatibilité avec mypy strict.
- Documenter chaque fonction et méthode publique avec une docstring au format
  Google. Décrire arguments, retour et exceptions lorsque pertinents ; ajouter
  des exemples quand utiles. Les docstrings du code sont en anglais ; les guides
  du projet sont en français.
- Utiliser Radon pour analyser la complexité et Bandit pour les contrôles de sécurité.
  Examiner les résultats et
  justifier toute exception ; ne pas masquer un diagnostic pour faire passer un contrôle.
- Ne pas introduire de dépendance sans nécessité et ne pas modifier le contrat
  public sans mettre à jour sa documentation et sa stratégie de compatibilité.

## Invariants du serveur

- Contrat minimal : `id: str`, `register(server: MCPServer) -> None` synchrone ;
  handlers synchrones ou asynchrones. `skill_roots()` et
  `configure(secrets: ConnectorSecrets)` sont facultatifs. Les connecteurs qui
  utilisent l’assistant déclarent `required_secrets() -> Iterable[SecretSpec]`.
- Découvrir via `hmcp.connectors` sans importer les plugins non sélectionnés.
  Une factory n’a pas d’argument ; son entry point et son identifiant correspondent.
- Convention : `hmcp-github` / `hmcp_github` / `github`, outils et prompts préfixés
  `github_`. Signaler explicitement doublons et erreurs de plugin.
- Préserver stdout pour le protocole stdio ; envoyer les logs sur stderr.
- Garder HTTP sur loopback par défaut. L’accès distant et l’authentification
  nécessitent un changement de périmètre explicite.
- Les skills sont des fichiers servis, pas des scripts à exécuter. Préserver
  l’indexation au démarrage, les empreintes, le refus des symlinks et des lectures
  hors racine. Inclure les fichiers des skills dans les distributions.
- Demander uniquement les secrets manquants au démarrage interactif. Sans terminal,
  échouer avec une commande de configuration, sans lire le flux MCP. Conserver
  les chemins par défaut et la commande `hmcp secrets set --connector <nom>`.
- Préserver le coffre AES-256-GCM, sa clé aléatoire séparée et les saisies masquées.
  Ne jamais exposer les secrets dans les outils MCP, arguments CLI ou logs.
  Ne pas présenter hmcp comme un produit qualifié ou certifié ANSSI.
- Les plugins sont du code de confiance ; ne pas ajouter d’appels réseau à l’import.
  Ne jamais afficher ou committer de secrets.

## Tests

- Écrire des tests pour toute nouvelle fonctionnalité et des tests de régression
  pour les corrections.
- Utiliser `unittest.TestCase` et `unittest.IsolatedAsyncioTestCase` pour les nouveaux
  tests, avec des fichiers `test_*.py` exécutables par le runner standard.
- La suite historique utilise pytest/pytest-asyncio : la conserver et l’exécuter
  pendant la transition. Ne pas prétendre que `unittest discover` couvre ses
  fonctions pytest. Ne pas convertir toute la suite sans demande liée à ce travail.
- Maintenir une couverture de lignes strictement supérieure à 80 % pour `hmcp`,
  `hmcp_demo` et `hmcp_demo_secrets` ; contrôler avec Coverage et `--fail-under=81`.
- Pour les changements de protocole, plugins ou packaging, vérifier les intégrations
  pertinentes : mémoire, stdio, HTTP local et installation du wheel hors du dépôt.

## Commandes de validation

Après installation selon `contributing.md` :

```sh
ruff format --check src plugins tests
ruff check src plugins tests
mypy src plugins/hmcp-demo/src plugins/hmcp-demo-secrets/src
radon cc src plugins/hmcp-demo/src plugins/hmcp-demo-secrets/src -s -a
bandit -r src plugins/hmcp-demo/src plugins/hmcp-demo-secrets/src
coverage run --source=hmcp,hmcp_demo,hmcp_demo_secrets -m pytest -q
coverage report --show-missing --fail-under=81
python -m unittest discover -s tests -p 'test_*.py'
python -m build
python -m build plugins/hmcp-demo --outdir plugins/hmcp-demo/dist
python -m build plugins/hmcp-demo-secrets --outdir plugins/hmcp-demo-secrets/dist
```

Adapter les vérifications au changement ; une modification documentaire seule
requiert surtout la validation des liens et des exemples. Signaler les contrôles
non exécutés, leurs raisons et les échecs restants. Radon, Bandit et
Coverage sont des exigences de validation locale et doivent être installés
séparément de l’extra `dev`. Ne pas mettre en place de GitHub Actions ; exécuter
les vérifications en local.

## Documentation et livraison

Garder le README bref : description, fonctionnalités, démarrage et liens.
Mettre les détails d’utilisation dans `docs/user-manual.md`, l’architecture et les
contrats dans `docs/design.md`, les règles de contribution dans `contributing.md`.
Mettre à jour les documents concernés lorsqu’un comportement change.

Avant livraison, relire le diff et résumer les changements, vérifications et
limites. Ne pas publier sur PyPI sans instruction explicite. Le nom `hmcp` est
déjà présent sur PyPI ; ne pas le renommer automatiquement.
