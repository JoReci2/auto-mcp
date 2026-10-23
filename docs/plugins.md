# Installation des extensions

Les extensions sont des distributions Python indépendantes. Leurs instructions
d’installation et d’utilisation sont maintenues avec leurs sources respectives.

Installer chaque distribution dans le même environnement Python que `yamcps`,
puis vérifier sa découverte :

```sh
yamcps connectors list
yamcps serve
```

Sans sélection explicite, le serveur charge les connecteurs installés par ordre
alphabétique. Pour limiter la sélection, répéter `--connector <identifiant>`.

Ne pas copier de coffre, de clé ou de données locales dans Git. Utiliser des
chemins absolus et redémarrer le serveur après une installation ou un changement
de configuration.

Voir le [manuel utilisateur](user-manual.md) pour les transports et les secrets,
et le [guide de configuration](configuration.md) pour les paramètres non secrets.
