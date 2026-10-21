# hmcp-demo-secrets

Plugin autonome pour tester la déclaration, la saisie interactive et le chargement
des secrets du coffre hmcp. Aucun appel réseau n’est effectué : utiliser des
valeurs fictives, par exemple un token `demo-token`, un utilisateur `demo-user`
et un mot de passe de démonstration.

Depuis la racine du dépôt :

```sh
python -m pip install -e . -e plugins/hmcp-demo-secrets
hmcp serve --connector demo-secrets
```

Le premier lancement dans un terminal demande `token`, `username` et `password`.
Les lancements suivants réutilisent le coffre. Pour reconfigurer les champs :

```sh
hmcp secrets set --connector demo-secrets
```

Pour supprimer puis redemander uniquement le token au prochain lancement :

```sh
hmcp secrets delete --connector demo-secrets --name token
hmcp serve --connector demo-secrets
```

Depuis un client MCP sans terminal, configurer d’abord les valeurs avec la commande
`secrets set`, puis lancer `hmcp serve --connector demo-secrets` sous le même compte.
Les options `--vault` et `--key-file` permettent d’isoler un coffre de test.

L’outil `demo_secrets_status`, sans argument, retourne uniquement :

```json
{"configured": true, "token_auth": "Bearer", "basic_auth": "Basic"}
```

Il vérifie la construction locale des en-têtes d’authentification. Il ne vérifie
pas les identifiants auprès d’une API et ne retourne ni token, ni nom d’utilisateur,
ni mot de passe, ni en-tête. Le skill `demo-secrets-check` est inclus dans le package.
