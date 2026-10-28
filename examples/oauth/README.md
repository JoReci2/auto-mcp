# Exemple OAuth : yamcps, Traefik et Authelia

Cette stack autonome expose `https://mcp.example.com/mcp`. Traefik termine TLS,
Authelia authentifie l’utilisateur avec un second facteur et émet un jeton d’accès,
yamcps vérifie le jeton. L’image yamcps est construite depuis ce checkout et charge
uniquement le connecteur `demo`, sans accès à vos services métier.

## Préparer

Prérequis : Docker avec Compose v2, OpenSSL, deux noms DNS publics pointant sur
l’hôte Docker, ports 80 et 443 accessibles pour le challenge Let's Encrypt HTTP-01.
Lancer les commandes depuis ce dossier :

```sh
cd examples/oauth
cp .env.example .env
cp authelia/users_database.yml.example authelia/users_database.yml
```

Remplacer `example.com` par votre domaine dans :

- `.env` : adresse de contact ACME ;
- `traefik/dynamic.yml` : noms `auth` et `mcp` ;
- `authelia/configuration.yml` : domaine du cookie et audience MCP ;
- `authelia/users_database.yml` : adresse du compte de démonstration ;
- `yamcps/oauth.json` : émetteur et URL publique MCP.

Conserver les deux noms sous le domaine du cookie. L’émetteur est ici
`https://auth.example.com`, sans slash final, et l’audience est exactement
`https://mcp.example.com/mcp`. Ne pas remplacer le chemin `/mcp`.

Créer les secrets locaux et la paire de clés. À exécuter **une seule fois**, sans
écraser les fichiers d’une installation existante :

```sh
umask 077
mkdir secrets
openssl rand -hex 32 > secrets/session
openssl rand -hex 32 > secrets/storage
openssl rand -hex 32 > secrets/oidc_hmac
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out secrets/issuer-private.pem
openssl pkey -in secrets/issuer-private.pem -pubout -out yamcps/issuer-public.pem
chmod 644 yamcps/issuer-public.pem
```

La clé privée est montée uniquement dans Authelia via un secret Compose ; yamcps
reçoit uniquement la clé publique. Les secrets restent des fichiers locaux, à
protéger et sauvegarder avec les volumes de données. Ils sont exclus de Git et du
contexte de build Docker, tout comme le fichier des utilisateurs.

Créer un mot de passe avec une saisie interactive masquée :

```sh
docker run --rm -it authelia/authelia:4.39.28 authelia crypto hash generate argon2
```

Copier uniquement la valeur `Digest` dans le champ `password` de
`authelia/users_database.yml`, entre apostrophes. Remplacer ensuite le nom `demo`
et son adresse si nécessaire. Aucun mot de passe prédéfini n’est fourni.

## Enregistrer le client MCP

Dans `authelia/configuration.yml`, le client public `yamcps-example` utilise
Authorization Code, PKCE S256 et un consentement explicite. Remplacer
`http://localhost:8765/callback` par **l’URI de retour exacte de votre client MCP**.
Cette valeur est illustrative : elle ne prétend pas être celle de Codex, Claude
ou Zoocode. Aucun wildcard ni port variable n’est enregistré automatiquement.

Configurer le client MCP avec :

| Paramètre | Valeur de l’exemple |
| --- | --- |
| Serveur MCP | `https://mcp.example.com/mcp` |
| Client ID préenregistré | `yamcps-example` |
| Client secret | Aucun : client public avec PKCE |
| Scope requis | `mcp:access` |
| Scopes facultatifs | `openid`, `offline_access` pour le renouvellement |
| Resource demandé | `https://mcp.example.com/mcp` |
| Callback | Exactement l’URI enregistrée dans Authelia |

Authelia ne fournit pas d’enregistrement dynamique des clients dans cet exemple.
Le client MCP doit accepter un ID préenregistré et envoyer le paramètre `resource`
à l’autorisation et à l’échange du code. Pour plusieurs applications, ajouter une
entrée distincte par client et ses callbacks, avec la même audience et le même
scope. Un client qui impose l’enregistrement dynamique nécessite une adaptation.

Le réglage `access_token_signed_response_alg: RS256` est essentiel : le format
opaque par défaut d’Authelia n’est pas accepté par le validateur JWT de yamcps.
Le jeton expire après cinq minutes. Le scope métier `mcp:access` peut produire un
avertissement Authelia sur les scopes non standards ; il est volontairement requis
et autorisé pour ce client.

## Valider et démarrer

```sh
docker compose config --quiet
docker compose run --rm authelia authelia config validate --config /config/configuration.yml
docker compose up -d --build
docker compose logs --tail 100 traefik authelia yamcps
```

Ouvrir `https://auth.example.com` et se connecter. Le fournisseur OAuth exige
`two_factor` : enregistrer un second facteur au premier accès. Le notifier fichier
est prévu pour cet exemple ; lire localement le message de vérification avec :

```sh
docker compose exec authelia cat /data/notification.txt
```

Ce fichier contient des liens de vérification sensibles. Pour une exploitation
régulière, remplacer le notifier fichier par votre SMTP Authelia.

Vérifier les métadonnées et le refus sans jeton :

```sh
curl --fail https://auth.example.com/.well-known/openid-configuration
curl --fail https://mcp.example.com/.well-known/oauth-protected-resource/mcp
curl -i -H 'Content-Type: application/json' -d '{}' https://mcp.example.com/mcp
```

La dernière commande doit répondre **401**, avec `WWW-Authenticate` et l’URL de
métadonnées. Lancer ensuite la connexion OAuth du client MCP, se connecter chez
Authelia, consentir et appeler l’outil de démonstration.
Un simple écran de connexion Authelia visible dans un navigateur ne valide pas
le parcours OAuth : vérifier aussi qu’un appel MCP authentifié réussit.

## Réseau et exploitation

Seul Traefik publie des ports sur l’hôte. Authelia et yamcps restent sur un réseau
Docker interne. Traefik utilise une configuration de fichiers et ne monte pas le
socket Docker. Il conserve `Host` et `Authorization`, route aussi les métadonnées
et transmet les réponses SSE sans mise en tampon ajoutée.

**Ne pas ajouter ForwardAuth au routeur MCP** : yamcps doit répondre lui-même aux
requêtes sans jeton pour annoncer OAuth. Les règles `access_control` d’Authelia
concernent ForwardAuth ; l’accès OAuth dépend ici de la politique du client OIDC.
Tous les comptes du backend peuvent autoriser ce client avec deux facteurs.
Adapter cette politique si seuls certains groupes doivent y accéder.

Les volumes conservent certificats, base Authelia et données yamcps. Ne pas lancer
`docker compose down -v` si vous souhaitez les garder. Une rotation de clé nécessite
le remplacement cohérent de la clé privée Authelia et du PEM public yamcps, puis
le redémarrage des deux services ; les anciens jetons cessent d’être valides.

L’image exemple porte une version locale `0.0.0+oauth.example`, sans publication.
Le plugin demo historique impose une ancienne plage de versions du moteur ; son
wheel est installé avec `--no-deps` après le moteur pour cet exemple uniquement.
Pour vos plugins métier, adapter le Dockerfile et la commande `--connector`, puis
préconfigurer leurs secrets et paramètres. Le réseau `backend` interne n’autorise
pas leurs appels sortants : ajouter un réseau de sortie dédié si nécessaire,
sans publier le port 8000.

Si vous avez déjà Traefik et Authelia, réutiliser seulement le bloc OIDC du client,
la clé publique, le service yamcps et son routeur dans vos réseaux existants.
Ne pas démarrer un second Traefik sur les ports déjà utilisés.

## Références

- [Clients OIDC Authelia](https://www.authelia.com/configuration/identity-providers/openid-connect/clients/)
- [Audiences et ressources Authelia](https://www.authelia.com/integration/openid-connect/introduction/#audiences)
- [Secrets et templates Authelia](https://www.authelia.com/configuration/methods/secrets/)
- [Traefik et ACME](https://doc.traefik.io/traefik/https/acme/)

Validation : syntaxe Compose et configuration Authelia 4.39.28 vérifiées avec des
clés temporaires. Le déploiement Docker complet, la délivrance des certificats ACME
et le parcours navigateur/client OAuth restent à vérifier sur votre hôte.
