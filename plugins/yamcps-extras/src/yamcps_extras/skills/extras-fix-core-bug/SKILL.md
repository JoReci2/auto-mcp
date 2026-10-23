---
name: extras-fix-core-bug
description: Diagnostiquer et corriger un bug dans le moteur yamcps avec reproduction, cause racine et test de non-régression. Utiliser pour une erreur de démarrage, découverte de plugin, CLI, protocole, skills, secrets ou packaging du cœur.
---

# Corriger un bug du moteur

1. Lire les consignes du dépôt et les modules concernés. Collecter le comportement
   observé et attendu, la commande, le transport, les versions Python/yamcps/SDK,
   les plugins sélectionnés et les logs utiles. Utiliser des données anonymisées ;
   ne pas demander ou recopier de secret. Rechercher ces éléments avant de demander
   des précisions déjà disponibles.
2. Reproduire avec le plus petit scénario local possible. Isoler configuration,
   plugin, SDK et moteur ; pour les configs/RAG, inspecter `configs.py`, `rag/`,
   `docs/configuration.md` et `docs/rag.md`. Vérifier le fichier JSON réellement
   résolu, la priorité fichier/environnement/défaut, les chemins absolus et l'ordre
   secrets → configs → RAG → skills → handlers. Distinguer un modèle téléchargé
   d'un modèle activé ; vérifier la cohérence du modèle et de l'index sans effacer
   ni réingérer un corpus existant pour établir le diagnostic. Comparer avec un plugin de démonstration
   ou un index de skills minimal. Ne pas utiliser une API de production pour reproduire une
   mutation ; simuler le service ou employer une fixture locale.
3. Identifier le premier point de divergence. Distinguer symptôme et cause racine,
   puis confirmer l'hypothèse par une trace ciblée ou un test. Si la reproduction
   échoue, présenter les faits et l'hypothèse restante ; ne pas annoncer une cause
   certaine ni une correction validée sans preuve.
4. Ajouter un test de régression observable et montrer qu'il échoue sur le code
   antérieur pour la cause attendue. Préférer unittest selon les consignes du dépôt
   et conserver les tests pytest historiques. Éviter un test couplé aux détails
   internes qui accepterait le même comportement incorrect.
5. Corriger la cause avec un diff ciblé ; garder les refactorings sans lien hors
   périmètre. Préserver le contrat des plugins, la sélection sans import inutile,
   les erreurs de collisions, les empreintes et restrictions des skills, stdout
   stdio, HTTP local et le masquage des secrets. Ne pas avaler une exception pour
   masquer un échec et ne pas désactiver un contrôle.
6. Faire passer le nouveau test, les tests proches puis les vérifications prescrites
   par le dépôt. Vérifier mémoire/stdio/HTTP si le protocole est touché ; vérifier
   l'installation du wheel hors du dépôt pour un bug de packaging. Ne pas prétendre
   que `unittest discover` remplace les fonctions pytest.
7. Corriger la documentation si le comportement documenté était erroné ; ajouter
   une note de migration si une compatibilité doit changer. Relire le diff pour
   vérifier qu'il ne contient ni secret, ni fixture personnelle, ni changement annexe.
8. Livrer le scénario de reproduction, la cause confirmée, le changement et la
   preuve de non-régression. Indiquer les tests non exécutés et les limites. Suivre
   le workflow de branche/PR sans lancer implicitement une release ou une publication.

## Résultat attendu

Une correction limitée, avec un test qui échoue avant et passe après. Si le problème
appartient à un service externe ou à sa configuration, expliquer la frontière et
ne pas modifier arbitrairement le moteur pour contourner le symptôme.
