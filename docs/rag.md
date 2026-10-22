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
Pour un handler async, déporter les opérations bloquantes dans un thread, comme
le fait `yamcps-docs`.

## Choisir son mode d'utilisation

- **Consulter des fichiers depuis un client IA** : installer `yamcps-docs` avec
  le moteur, puis suivre le démarrage MCP ci-dessous.
- **Développer un plugin ou un script Python** : utiliser `yamcps.rag.Document`
  et `yamcps.rag.Index`, ou le contexte injecté dans le plugin. Le plugin garde la responsabilité de lire sa source, de choisir
  les données indexables et d'enregistrer ses outils MCP.

Python 3.12 ou supérieur est requis. Les commandes suivantes s'exécutent depuis
la racine du dépôt, sur la branche contenant ces packages.

## Démarrage via MCP avec yamcps-docs

Dans un environnement virtuel activé :

```sh
python -m pip install -e . -e 'plugins/yamcps-docs[formats]'
export YAMCPS_DOCS_INDEX="$HOME/.local/share/yamcps/docs.sqlite3"
yamcps-docs ingest plugins/yamcps-docs/examples/manifest.json
yamcps serve --connector docs
```

L'extra `formats` du plugin permet de lire les PDF texte et DOCX ; TXT et Markdown
sont disponibles sans cet extra. L'exemple fourni est fictif.

Depuis le client MCP connecté à ce serveur, demander une recherche de
`SSS-REQ-0042` dans le corpus `demo/specifications`. Le plugin expose :

| Outil MCP | Usage |
| --- | --- |
| `docs_search` | Retrouver des passages, avec filtres de métadonnées facultatifs |
| `docs_get_passage` | Relire un passage cité par son identifiant |
| `docs_get_document` | Lire une révision précise du texte extrait |
| `docs_index_status` | Consulter le mode de recherche, les compteurs et la date des passages modifiés |

L'ingestion se fait **avant la consultation**, avec une commande séparée. Le
serveur ne lance aucune indexation au démarrage. Pour un client stdio, transmettre
`YAMCPS_DOCS_INDEX` dans son bloc `env` et utiliser un chemin absolu.

Voir le [guide yamcps-docs](../plugins/yamcps-docs/README.md) pour le manifeste,
les formats, les ressources MCP et les limites de l'extraction.

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

Pour le plugin MCP, définir `YAMCPS_DOCS_MODEL` avec ce dossier et utiliser un
nouveau chemin `YAMCPS_DOCS_INDEX`, puis ingérer les sources avant de lancer le
serveur. Ces variables appartiennent à `yamcps-docs` : l’API Python
reçoit directement le chemin et le fournisseur dans `Index(...)`.

Un index possède **une seule configuration d'embeddings**, partagée entre ses
corpus. Utiliser le même modèle pour ingestion et recherche. L'adaptateur calcule
une empreinte des fichiers du modèle ; changer de modèle ou passer du lexical à
l'hybride exige un nouvel index et une réindexation. Le protocole `Embedder` permet
un autre fournisseur avec `identity: str` et `embed(text) -> list[float]` ; son identité
doit changer avec son modèle/prétraitement, et ses vecteurs doivent être finis,
non nuls et de dimension constante.

## Limites et erreurs courantes

- **Index absent** : appeler `sync()` en Python ou `yamcps-docs ingest` via le plugin.
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
au lieu de la distribution séparée. Les plugins intégrés utilisent les deux hooks
ci-dessus. Pour réutiliser un ancien index documentaire, garder son chemin via
`YAMCPS_DOCS_INDEX` : le format SQLite reste inchangé. Le nouveau chemin par défaut
est `~/.local/share/yamcps/rag/docs.sqlite3`. Utiliser un environnement virtuel neuf
ou retirer l’ancienne distribution pour éviter un module obsolète inutilisé.
