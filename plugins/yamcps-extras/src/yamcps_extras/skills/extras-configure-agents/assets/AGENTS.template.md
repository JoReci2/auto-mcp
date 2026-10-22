# Consignes de <nom-du-projet>

## Repères

- Objectif : <objectif-observé>.
- Environnement : Python <version-vérifiée>, installation <commande-vérifiée>.
- Structure : <chemins-réels-et-responsabilités>.
- Références : <liens-relatifs-vers-architecture-et-contribution>.

## Implémentation

- Respecter les conventions et le contrat public du dépôt.
- Suivre PEP 8, typer les interfaces publiques et documenter les fonctions publiques
  au format Google en anglais ; rédiger les guides en français si le projet le prévoit.
- <invariants-spécifiques-observés>.
- Protéger les secrets ; garder les logs hors de stdout pour le transport MCP stdio.
- Ne pas ajouter de dépendance sans nécessité ni étendre le périmètre réseau implicite.

## Vérification

- Ajouter un test pour une fonctionnalité ou une régression.
- Runner(s) : <commandes-réellement-validées>.
- Qualité et couverture : <commandes-et-seuils-du-projet>.
- Pour un changement de protocole/packaging : <intégrations-et-build-pertinents>.
- Signaler les contrôles non exécutés et leurs raisons ; ne pas masquer les échecs.

## Livraison

- Relire le diff et mettre à jour les guides concernés.
- Résumer le comportement, la validation et les limites.
- Respecter les autorisations de l'utilisateur pour toute publication ou action externe.
