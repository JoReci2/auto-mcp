---
name: extras-configure-agents
description: Créer ou mettre à jour les consignes AGENTS.md ou AGENT.md d'un dépôt yamcps ou d'un plugin, à partir de sa structure et de commandes vérifiées. Utiliser pour préparer un dépôt au travail d'un agent ou corriger des instructions obsolètes.
---

# Configurer les consignes du dépôt

1. Identifier le dépôt et le client ciblés. Relever les consignes existantes à la
   racine et dans les sous-dossiers concernés. Pour yamcps, conserver `AGENTS.md`.
   Si l'utilisateur demande `AGENT.md`, vérifier la convention de son client et
   son intention avant de créer un doublon ; ne pas supposer qu'un nom singulier
   sera découvert automatiquement.
2. Lire `pyproject.toml`, le README, `docs/design.md`, `contributing.md`, la CLI,
   les tests et le packaging présents. Ne décrire que les capacités observées.
   Ne pas supposer que les fonctionnalités d'une autre branche sont intégrées.
3. Relever les règles du projet : Python minimal, outils de qualité, conventions
   de noms, runner de tests, couverture, contrat des plugins et transports.
   Préserver les règles métier existantes ; résoudre les contradictions selon
   les instructions explicites de l'utilisateur et les fichiers applicables.
4. Adapter [le modèle](assets/AGENTS.template.md) avec les chemins et commandes
   réels. Remplacer tous les champs entre chevrons. Garder les détails dans les
   guides existants et des liens relatifs dans les consignes.
5. Inclure les invariants yamcps pertinents : `yamcps.connectors`, factory sans
   argument, `id` identique à l'entry point, `register` synchrone, absence de réseau
   à l'import, stdout réservé à stdio, secrets masqués et HTTP local par défaut.
   Ne pas transformer ces règles en autorisations nouvelles de déploiement,
   suppression de données ou publication de packages.
6. Vérifier les chemins, les liens et chaque commande indiquée. Distinguer ce
   qui a été exécuté de ce qui reste à vérifier. Ne pas affirmer que `unittest`
   couvre les fonctions pytest historiques. Ne pas désactiver un contrôle pour
   faire passer une validation.
7. Relire le diff : conserver les consignes utiles, supprimer les contradictions
   et éviter les règles génériques répétées. Livrer le fichier et résumer les
   changements et les vérifications.

## Résultat attendu

Un fichier de consignes court, applicable au dépôt inspecté, avec une carte des
fichiers, les invariants, les commandes vérifiées et les conditions de livraison.
Ne pas y inclure de secrets, de chemins personnels ni de résultats de tests inventés.
Le modèle est une aide à la rédaction, pas un fichier prêt à installer tel quel.
