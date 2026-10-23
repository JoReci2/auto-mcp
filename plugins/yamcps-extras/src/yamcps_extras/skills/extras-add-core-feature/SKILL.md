---
name: extras-add-core-feature
description: Ajouter une fonctionnalité dans le moteur yamcps en respectant le contrat des connecteurs, les transports MCP, les secrets et le packaging. Utiliser pour faire évoluer le cœur, la CLI, le registre ou le catalogue de skills.
---

# Ajouter une fonctionnalité au moteur

1. Lire les consignes applicables, `docs/design.md`, `contributing.md` et les tests.
   Examiner la branche et le diff existant ; préserver les changements de l'utilisateur.
   Reformuler le comportement attendu avec un exemple observable avant/après.
2. Vérifier que le besoin appartient au moteur : composition, découverte, registre,
   CLI, secrets, configurations en clair, RAG ou catalogue de skills. Garder les appels métier et leurs dépendances
   dans un plugin. Ne pas généraliser le cœur pour un unique besoin sans justification.
3. Identifier les modules et le chemin d'exécution réel :
   - `connectors.py` : découverte sans import et contrat des plugins ;
   - `server.py`, `registry.py` : composition et refus des collisions ;
   - `skills.py` : catalogue immuable, empreintes et ressources ;
   - `cli.py` : commandes et transports ;
   - `configs.py` : `ConfigSpec`, `ConnectorConfigs`, résolution et stockage JSON ;
   - `rag/` : contexte paresseux, index SQLite, embeddings et téléchargement explicite ;
   - `secrets.py`, `onboarding.py`, `vault.py` : injection et coffre.
   Adapter cette carte si les sources ont évolué.
   Lire aussi `docs/configuration.md` et `docs/rag.md` si ces capacités sont touchées.
   Préserver l'ordre secrets → configs → RAG → skills → handlers ; aucun accès à
   l'index, aux sources ou aux modèles dans les hooks de démarrage. Garder les
   configurations non secrètes en JSON et les identifiants dans le vault.
4. Définir l'API et la compatibilité. Préserver les plugins existants et privilégier
   une capacité optionnelle lorsque c'est adapté. Pour une rupture nécessaire,
   documenter migration, version et contraintes des plugins concernés avant livraison.
5. Implémenter le plus petit changement cohérent. Préserver stdout pour stdio,
   les logs stderr, HTTP loopback par défaut, la sélection explicite des plugins,
   les erreurs de doublons et l'absence de secrets dans les réponses. Ne pas étendre
   implicitement le serveur à un service distant ou multi-utilisateur.
6. Écrire des tests du comportement attendu : réussite, entrées invalides, erreurs
   et compatibilité. Utiliser les classes unittest selon les consignes du dépôt,
   tout en conservant la suite pytest historique. Tester un plugin antérieur si le
   contrat change. Ne pas modifier les assertions pour contourner un échec réel.
7. Exécuter les contrôles qualité et couverture prescrits. Pour un changement MCP,
   vérifier les clients en mémoire, stdio et HTTP local. Pour le packaging,
   construire wheel/sdist et installer hors du dépôt. Choisir les vérifications
   en fonction du changement et signaler celles qui n'ont pas pu être exécutées.
8. Mettre à jour le manuel pour le comportement, l'architecture pour les contrats,
   le README pour les capacités générales et la contribution pour les commandes.
   Conserver le périmètre du workflow de release : seul le package de base est
   publié, sauf demande explicite de changement de cette politique.
9. Relire le diff et livrer le comportement obtenu, les tests, la compatibilité
   et les limites. Suivre le workflow de branche/PR du dépôt. Ne pas déclencher
   une release ou une publication du seul fait d'avoir terminé la fonctionnalité.

## Résultat attendu

Une modification du moteur accompagnée de tests et de documentation, dont les
conséquences sur les plugins et transports sont explicites. Si la demande vise
uniquement un connecteur, suivre plutôt le skill de développement de plugin.
