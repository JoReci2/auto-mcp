# RAG intégré au moteur yamcps

Le package de base `yamcps` inclut la capacité RAG dans `yamcps.rag`. Chaque plugin
peut y souscrire, comme il peut fournir des skills ou déclarer des secrets.
Il n'existe plus de distribution séparée `yamcps-rag-core` à installer.

| Composant | Responsabilité |
| --- | --- |
| `yamcps.rag` dans le moteur | Configuration, contexte par plugin, indexation SQLite et recherche |
| Plugin métier | Choisir les sources et corpus, extraire les textes et exposer les outils MCP |
| Client IA | Composer une réponse à partir des passages et de leurs références |

Le contrat minimal d'un connecteur reste `id` et `register()`. Le RAG est une
capacité optionnelle : les plugins existants n'ont pas à changer. Aucun index
n'est créé et aucun modèle n'est chargé au démarrage du serveur par le moteur.
Aucun outil RAG universel n'est ajouté automatiquement.

## Activer le RAG dans un plugin

Implémenter les deux hooks synchrones suivants :

```python
from mcp.server import MCPServer
from yamcps import RagConfig, RagContext


class MyConnector:
    id = "my-plugin"

    def rag_config(self) -> RagConfig:
        return RagConfig()

    def configure_rag(self, rag: RagContext) -> None:
        self.rag = rag

    def register(self, server: MCPServer) -> None:
        # Enregistrer les handlers métier ici. Dans un handler, utiliser
        # self.rag.index.search(...) ou self.rag.index.get_document(...).
        # L'ingestion appelle self.rag.index.sync(...) hors démarrage MCP.
        pass
```

Le serveur appelle les hooks après la configuration des secrets, avant les skills
et l'enregistrement des handlers. Il fournit une seule instance de `RagContext`
à chaque plugin sélectionné. Les deux hooks doivent être présents et synchrones ;
une déclaration invalide empêche le démarrage avec une erreur identifiant le plugin.
Le contexte conserve le même `Index` lors de ses accès successifs et concurrents.

Sans chemin explicite, l'index est situé sous
`~/.local/share/yamcps/rag/<identifiant-plugin>.sqlite3`. `YAMCPS_RAG_DIR` change le
répertoire de base. `RagConfig(index_path=Path(...), model_path=Path(...))` permet
au plugin de choisir une base et un modèle local. Un chemin d'index explicite
prévaut sur `YAMCPS_RAG_DIR`. Cette séparation par défaut évite les collisions,
sans constituer une sandbox ou un mécanisme d'autorisation.

Accéder à `rag.index` prépare l'objet et charge le modèle si demandé, mais ne crée
pas la base SQLite. Seule une synchronisation écrit les documents. Ne pas accéder
à l'index, aux sources ni au modèle dans les hooks ou dans `register()` : conserver
les traitements dans les handlers ou une commande d'ingestion séparée.
Pour un handler async, déporter les opérations bloquantes dans un thread.

## Utilisation directe en Python

Les primitives RAG sont aussi utilisables depuis un script Python avec le package de base :

```sh
python -m pip install -e .
```

Exemple complet, sans modèle d'embeddings ni accès réseau :

```python
from pathlib import Path

from yamcps.rag import Document, Index

index = Index(Path("data/example.sqlite3"))
corpus = "demo/specifications"

documents = [
    Document(
        corpus=corpus,
        document_id="SSS-DEMO",
        revision="1.2",
        text="SSS-REQ-0042 : le système doit sauvegarder sa configuration chaque soir.",
        metadata={"type": "SSS", "baseline": "v1", "status": "approved"},
    )
]

# Créer l'index et synchroniser la liste complète des révisions du corpus.
print(index.sync(corpus, documents))

hits = index.search(
    "SSS-REQ-0042",
    corpus,
    filters={"baseline": "v1", "status": "approved"},
    limit=5,
)
for hit in hits:
    print(hit.document_id, hit.revision, hit.source_uri)
    print(hit.text)
    print(index.get_passage(hit.passage_id).indexed_at)

source = index.get_document(corpus, "SSS-DEMO", "1.2")
print(source.text)
print(index.status(corpus))
```

L'exemple crée `data/example.sqlite3` dans le répertoire courant. `Document.text`
contient le **texte déjà extrait** : la bibliothèque ne lit pas elle-même les PDF,
DOCX, API ou dépôts. Cette extraction appartient au plugin ou au script appelant.
Le nom du corpus est une chaîne de classement, pas un chemin de dossier.

### Synchronisation et conservation des versions

**`Index.sync(corpus, documents)` reçoit un snapshot complet du corpus, pas une
liste de documents à ajouter.** Une révision absente de cette liste est supprimée.
Une liste vide efface tous les documents de ce corpus. Les autres corpus restent
inchangés. Pour conserver plusieurs révisions, les fournir toutes à chaque appel.

La synchronisation retourne `updated`, `unchanged` et `deleted`. L'empreinte tient
compte du contenu, des métadonnées et du découpage ; un document identique évite
le recalcul de ses passages et embeddings. Les changements d'un corpus sont
transactionnels : une erreur d'embedding annule les mises à jour de l'appel.

Le découpage par défaut fait au plus 1200 caractères par passage, sans
chevauchement. `chunk_size` accepte une valeur de 64 à 16000 dans `sync()`.
Une modification du contenu, des métadonnées ou du découpage change les
identifiants des passages concernés : relancer la recherche pour obtenir leurs
nouvelles références.

### Résultats et références

Chaque `SearchHit` fournit notamment `passage_id`, `corpus`, `document_id`,
`revision`, `source_uri`, `text`, `start`, `end`, `indexed_at`, `metadata` et `score`.
Les offsets `start` inclus et `end` exclu désignent des caractères du texte extrait,
pas les pages du fichier d'origine. Le score sert au classement, sans représenter
une probabilité de vérité.

Les filtres sont des égalités sur les métadonnées, combinées par ET. La recherche
exige un corpus explicite, une requête non vide de 4000 caractères maximum et une
limite de 1 à 20 résultats. Sans passage correspondant, elle retourne une liste vide.

## Télécharger un modèle pour l'utiliser localement

Le moteur propose une commande explicite de téléchargement depuis Hugging Face.
Elle n'est pas exposée au modèle comme outil MCP et ne s'exécute jamais au démarrage.

Installer l’extra `rag` pour télécharger les modèles, les charger localement
et calculer les embeddings :

```sh
python -m pip install -e '.[rag]'
```

Exemple avec un modèle Sentence Transformers multilingue :

```sh
yamcps models download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

La commande affiche le chemin absolu du dossier local. Par défaut, il se trouve
sous `~/.local/share/yamcps/models/<organisation>--<modele>/<commit>`. Définir
`YAMCPS_MODELS_DIR` pour changer la racine. Une destination explicite permet de
choisir le dossier à transférer sur une machine hors ligne :

```sh
yamcps models download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --revision main --destination /chemin/vers/un-nouveau-dossier
```

`--revision` accepte une branche, un tag ou un commit ; la commande résout cette
révision en commit avant de télécharger. `yamcps-model.json` conserve le dépôt,
la révision demandée et le commit obtenu. Le téléchargement préfère les poids
Safetensors lorsqu'ils sont disponibles, avec un repli sur les poids binaires.
Les exports ONNX/OpenVINO et fichiers Python ne sont pas téléchargés.
Le format attendu est un pipeline de modules standards Sentence Transformers
avec `modules.json` ; les modules Python personnalisés ne sont pas pris en charge.
La validation vérifie sa structure et la présence de poids ; elle ne charge pas
le modèle et ne mesure pas sa qualité sémantique.

Les fichiers sont préparés dans un dossier temporaire, puis publiés sous leur
chemin final seulement après validation. Une destination existante n'est pas
écrasée. En cas d'erreur, les fichiers partiels de cet essai sont retirés. Cette
V1 ne propose pas de reprise des téléchargements interrompus, de mise à jour ou
de suppression automatique des modèles.

Pour un dépôt privé ou à accès restreint, fournir `HF_TOKEN` dans l'environnement
et disposer des droits nécessaires sur Hugging Face. Aucun token n'est accepté
comme argument CLI ou écrit dans le manifeste. Sans `HF_TOKEN`, la requête est
anonyme. Les erreurs affichées n'incluent pas les diagnostics bruts du fournisseur.

Fournir le dossier dans `RagConfig(model_path=Path(...))` pour utiliser le modèle.
Télécharger un modèle ne l’active pas automatiquement et ne réindexe aucun
corpus. Après copie du dossier vers une machine hors ligne, utiliser son nouveau
chemin local et installer aussi les dépendances Python de l'extra `rag` sur cette
machine. Le chargement reste en mode local, sans code distant ni téléchargement
implicite. Un nouveau modèle exige un nouvel index.

Références : [API de téléchargement Hugging Face](https://huggingface.co/docs/huggingface_hub/en/package_reference/file_download)
et [fiche du modèle d'exemple](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).

## Recherche lexicale ou hybride

Sans fournisseur d'embeddings, le mode est **lexical** : classement par recouvrement
de tokens, utile notamment pour les identifiants d'exigences. Il ne comprend pas
les synonymes. SQLite stocke alors documents et passages sans vecteurs.

Pour activer les embeddings, installer l'extra optionnel :

```sh
python -m pip install -e '.[rag]'
```

Avec un modèle Sentence Transformers déjà disponible localement, remplacer la
construction de l'index Python par :

```python
from pathlib import Path

from yamcps.rag import Index, LocalSentenceTransformer

embedder = LocalSentenceTransformer(Path("/chemin/absolu/vers/modele-local"))
index = Index(Path("data/example-hybrid.sqlite3"), embedder=embedder)
```

Appeler ensuite `sync()` et `search()` comme dans l'exemple précédent, avec la même
configuration. Le mode hybride combine recouvrement lexical et cosinus des vecteurs
à poids égaux. Aucun modèle n'est fourni ou téléchargé automatiquement ; le dossier
local doit contenir un modèle compatible. Le chargement de code distant est désactivé.
La qualité sémantique dépend du modèle choisi et reste à évaluer sur vos questions.

Un index possède **une seule configuration d'embeddings**, partagée entre ses
corpus. Utiliser le même modèle pour ingestion et recherche. L'adaptateur calcule
une empreinte des fichiers du modèle ; changer de modèle ou passer du lexical à
l'hybride exige un nouvel index et une réindexation. Le protocole `Embedder` permet
un autre fournisseur avec `identity: str` et `embed(text) -> list[float]` ; son identité
doit changer avec son modèle/prétraitement, et ses vecteurs doivent être finis,
non nuls et de dimension constante.

## Limites et erreurs courantes

- **Index absent** : appeler `sync()` en Python avant toute lecture.
  Les opérations de lecture ne créent pas la base.
- **Configuration incompatible** : vérifier le mode et le modèle utilisés. Choisir
  une nouvelle base pour un autre modèle plutôt que de mélanger les espaces vectoriels.
- **Ancien passage introuvable** : sa source a pu changer ou être retirée ; refaire
  une recherche et consulter les nouvelles références.
- **Recherche lente** : la V1 parcourt les passages du corpus en mémoire. Elle vise
  les petits corpus, sans moteur ANN, BM25, reranker ou cache de réponses.
- **Source et permissions** : SQLite conserve les contenus en clair. Les corpus et
  filtres ne constituent pas des autorisations multi-utilisateur. L'index est une
  copie ; la date des passages ne certifie pas la fraîcheur du référentiel source.

Le module RAG n'ajoute aucun traitement OCR ni génération de réponse. Il est
inclus dans le wheel de base `yamcps` publié par le workflow PyPI. Les plugins
et les dépendances de l'extra `rag` ne sont pas embarqués dans ce wheel.

## Migration de la première version de la branche RAG

Remplacer les imports `yamcps_rag_core` par `yamcps.rag` et installer `yamcps`
au lieu de la distribution séparée. Pour réutiliser un ancien index, fournir son
chemin à `Index` ou `RagConfig.index_path` : le format SQLite reste inchangé.
Utiliser un environnement virtuel neuf ou retirer l’ancienne distribution.

Le [guide de configuration](configuration.md) décrit `required_configs()`,
`configure_configs()`, le fichier JSON et les priorités de résolution.
