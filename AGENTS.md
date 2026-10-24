# Consignes du dépôt yamcps

## Projet et repères

yamcps (Yet Another Model Context Protocole Server) est un serveur MCP Python ≥ 3.12 distribué avec Hatchling.
Les connecteurs sont des packages indépendants nommés `yamcps-<nom>`.
Lire `CONTRIBUTING.md` avant de modifier l’architecture ou le contrat des plugins
et pour le workflow de contribution ; lire `README.md` pour le comportement utilisateur.

- `src/yamcps/rag` : capacité RAG native facultative pour les connecteurs.
- `src/yamcps` : cœur, CLI, découverte des plugins, registre et catalogue de skills.
- `plugins/yamcps-demo` : exemple de distribution autonome et skill embarqué.
- `plugins/yamcps-demo-rag` : démo autonome du contrat de backend RAG extensible.
- `plugins/yamcps-demo-secrets` : démo du coffre interactif, token et Basic Auth sans API externe.
- `tests` : tests du cœur et intégrations MCP.
- `pyproject.toml` : versions Python, dépendances et configuration des outils.

Les plugins métier et leurs tests sont maintenus dans les dépôts externes référencés
dans le `README.md`. Ne pas les réintroduire dans ce dépôt.

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
- Configurations facultatives : `required_configs()` et `configure_configs()`
  synchrones ; champs non secrets en JSON, secrets uniquement dans le vault.
- RAG facultatif : déclarer ensemble `rag_config() -> RagConfig` et
  `configure_rag(context: RagContext) -> None`, synchrones. Garder les modèles,
  sources et écritures hors du démarrage ; le moteur injecte un contexte paresseux.
- Sans `--connector`, charger tous les plugins installés par ordre alphabétique.
  Répéter `--connector` pour sélectionner plusieurs plugins.
- Découvrir via `yamcps.connectors` sans importer les plugins non sélectionnés.
  Une factory n’a pas d’argument ; son entry point et son identifiant correspondent.
- Convention : `yamcps-github` / `yamcps_github` / `github`, outils et prompts préfixés
  `github_`. Signaler explicitement doublons et erreurs de plugin.
- Préserver stdout pour le protocole stdio ; envoyer les logs sur stderr.
- Garder HTTP sur loopback par défaut. L’accès distant et l’authentification
  nécessitent un changement de périmètre explicite.
- Les skills sont des fichiers servis, pas des scripts à exécuter. Préserver
  l’indexation au démarrage, les empreintes, le refus des symlinks et des lectures
  hors racine. Inclure les fichiers des skills dans les distributions.
- Demander uniquement les secrets manquants au démarrage interactif. Sans terminal,
  échouer avec une commande de configuration, sans lire le flux MCP. Conserver
  les chemins par défaut et la commande `yamcps secrets set --connector <nom>`.
- Préserver le coffre AES-256-GCM, sa clé aléatoire séparée et les saisies masquées.
  Ne jamais exposer les secrets dans les outils MCP, arguments CLI ou logs.
  Ne pas présenter yamcps comme un produit qualifié ou certifié ANSSI.
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
- Maintenir une couverture de lignes strictement supérieure à 80 % pour `yamcps`,
  `yamcps_demo`, `yamcps_demo_secrets` et `yamcps_demo_rag` ; contrôler avec Coverage et `--fail-under=81`.
- Pour les changements de protocole, plugins ou packaging, vérifier les intégrations
  pertinentes : mémoire, stdio, HTTP local et installation du wheel hors du dépôt.

## Commandes de validation

Après installation selon `CONTRIBUTING.md` :

```sh
ruff format --check src plugins .github/workflows tests
ruff check src plugins .github/workflows tests
mypy src plugins/*/src .github/workflows
radon cc src plugins/*/src .github/workflows -s -a
bandit -r src plugins/*/src .github/workflows
coverage run --source=yamcps,yamcps_demo,yamcps_demo_secrets,yamcps_demo_rag -m pytest -q
coverage report --show-missing --fail-under=81
python -m unittest discover -s tests -p 'test_*.py'
python -m build
python -m build plugins/yamcps-demo --outdir plugins/yamcps-demo/dist
python -m build plugins/yamcps-demo-secrets --outdir plugins/yamcps-demo-secrets/dist
python -m build plugins/yamcps-demo-rag --outdir plugins/yamcps-demo-rag/dist
```

Adapter les vérifications au changement ; une modification documentaire seule
requiert surtout la validation des liens et des exemples. Signaler les contrôles
non exécutés, leurs raisons et les échecs restants. Radon, Bandit et
Coverage sont des exigences de validation locale et doivent être installés
séparément de l’extra `dev`. Le workflow `.github/workflows/workflow.yaml` publie uniquement le package de base
`yamcps` à la publication d’une release. Exécuter les contrôles de développement
en local ; ne pas ajouter de publication automatique des plugins.

## Documentation et livraison

Réserver `README.md` aux utilisateurs : présentation, quickstart et utilisation.
Regrouper l’architecture, les contrats et les règles de contribution dans
`CONTRIBUTING.md`, destiné aux développeurs et aux personnes techniques.
Mettre à jour les documents concernés lorsqu’un comportement change.

Avant livraison, relire le diff et résumer les changements, vérifications et
limites. Ne pas publier sur PyPI sans instruction explicite. Le nom `yamcps` est réservé pour le projet. Ne jamais déclencher de release
ou publier une version sans instruction explicite.

