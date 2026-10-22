# hmcp-rag-core

Bibliothèque Python partagée, sans entry point MCP. Fournit `Document`, `Passage`,
`SearchHit`, `Index` et un protocole `Embedder` pour les plugins métier.

SQLite conserve des snapshots atomiques par corpus et des citations stables tant
que contenu, métadonnées et découpage restent identiques. `Index.sync` attend la
liste **complète** des révisions à conserver ; une liste vide efface le corpus.
Les autres corpus sont préservés. Une erreur d'embedding annule la transaction.

Recherche lexicale par défaut ; embeddings optionnels via l'extra `semantic` et
`LocalSentenceTransformer(Path(...))`. Le modèle doit être présent localement :
aucun téléchargement automatique. L'empreinte des fichiers du modèle identifie
l'espace vectoriel ; un changement exige un nouvel index. Les fournisseurs
personnalisés doivent garantir une identité stable et des vecteurs de même taille.

La recherche hybride combine recouvrement lexical et cosinus à poids égaux.
Elle est exhaustive en mémoire et destinée aux petits corpus. Pas de moteur ANN,
BM25, reranker, cache de réponses, LLM générateur ni ACL multi-utilisateur dans
cette version. Les corpus constituent un filtre fonctionnel, pas une autorisation.
