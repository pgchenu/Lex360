# Installation de l'extension lex360 pour Claude Desktop

## Prérequis

- [Claude Desktop](https://claude.ai/download) installé
- Un compte [Lexis 360 Intelligence](https://www.lexis360intelligence.fr/) actif

## Étape 1 — Télécharger le fichier `.mcpb`

Récupérez `lex360-0.3.0.mcpb` depuis les [releases](https://github.com/pgchenu/Lex360/releases).

## Étape 2 — Ouvrir les extensions Claude Desktop

Dans Claude Desktop, allez dans **Paramètres > Extensions**. Vous verrez la zone de dépôt en bas de la page :

> *Glisser les fichiers .MCPB ou .DXT ici pour les installer.*

![Page Extensions de Claude Desktop](screenshots/screenshot3.png)

## Étape 3 — Installer l'extension

Glissez le fichier `lex360-0.2.0.mcpb` dans la zone de dépôt. Claude Desktop affiche un aperçu de l'extension avec ses 12 outils. Cliquez **Installer**.

![Aperçu de l'extension avec le bouton Installer](screenshots/screenshot4.png)

## Étape 4 — Configurer le token JWT

Après l'installation, Claude Desktop vous demande le token JWT. Pour le récupérer :

1. Connectez-vous sur [lexis360intelligence.fr](https://www.lexis360intelligence.fr/)
2. Ouvrez la console du navigateur (`F12` > onglet **Console**)
3. Collez cette commande :
   ```js
   localStorage.getItem('access_token')
   ```
4. Copiez la valeur retournée (les guillemets éventuels en début et fin sont retirés automatiquement)

Collez le token dans le champ et cliquez **Enregistrer**.

![Boîte de dialogue de configuration du token](screenshots/screenshot5.png)

### Astuce — Bookmarklet de récupération du token

Pour éviter d'ouvrir la console à chaque renouvellement :

1. Créez un nouveau favori dans votre navigateur, nommez-le « Lex360 token ».
2. Comme URL, collez exactement le code ci-dessous (également disponible dans [`bookmarklet.txt`](bookmarklet.txt)) :
   ```js
   javascript:(()=>{const H='lexis360intelligence.fr';if(!location.hostname.endsWith(H)){if(confirm('Ouvrir Lexis 360 ? (connectez-vous via votre portail puis recliquez sur ce favori)'))location.href='https://www.'+H+'/';return;}const t=localStorage.getItem('access_token');if(!t){alert('Aucun token. Connectez-vous d\'abord (portail universitaire le cas échéant), puis recliquez sur ce favori.');location.href='https://www.'+H+'/';return;}const c=t.replace(/^"|"$/g,'');navigator.clipboard.writeText(c).then(()=>alert('Token copié ('+c.length+' chars, finit par …'+c.slice(-12)+')'),()=>prompt('Copiez le token :',c));})();
   ```
3. Connectez-vous une fois sur lexis360intelligence.fr (directement ou via votre portail universitaire / SSO Shibboleth / ENT).
4. Une fois la page Lexis 360 chargée, cliquez sur le favori : le token est copié dans le presse-papier.
5. Collez-le (`Cmd+V` / `Ctrl+V`) dans le champ de configuration de l'extension.

Si le bookmarklet est cliqué hors d'une session connectée, il vous redirige vers Lexis 360 pour vous reconnecter.

## Étape 5 — Vérifier l'activation

L'extension doit afficher **Activé** avec le toggle bleu. Vous pouvez maintenant utiliser les outils lex360 dans vos conversations Claude.

![Extension activée](screenshots/screenshot6.png)

> N'oubliez pas de cocher Lex360 dans les connecteurs disponibles dans votre conversation avec Claude

---

## Renouveler le token

Le token JWT expire après **24 heures**. Quand les outils retournent une erreur « Token expiré », il faut le mettre à jour.

### 1. Accéder à la configuration

Dans **Paramètres > Extensions**, cliquez **Configurer** à côté de Lexis 360 Intelligence.

![Bouton Configurer dans la liste des extensions](screenshots/screenshot7.png)

### 2. Coller le nouveau token

Récupérez un nouveau token depuis la console du navigateur (même procédure qu'à l'étape 4), collez-le dans le champ et cliquez **Enregistrer**.

![Mise à jour du token](screenshots/screenshot8.png)
