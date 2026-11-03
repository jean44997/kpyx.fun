# KPYX — plateforme e-commerce et formation

Socle applicatif V1 en français pour les produits numériques, KPYX Academy, les inscriptions et validations manuelles, le parrainage, le portefeuille, l’administration et les journaux d’audit.

## Architecture retenue

- **Django 5.2 LTS + Python 3.14** : monolithe modulaire et rendu serveur, avec authentification, permissions, formulaires CSRF et console d’administration.
- **PostgreSQL en production**, SQLite pour l’installation locale et les tests.
- **HTML/CSS responsive** sans dépendance JavaScript d’exécution; API JSON de lecture sous `/api/v1/` pour les intégrations futures.
- **Affichage multi-écran** : navigation compacte pour téléphone/tablette, grilles fluides pour mobile, tablette et ordinateur, zones tactiles plus grandes, prise en compte des encoches iOS et champs à 16 px pour éviter le zoom automatique sur iPhone. Animations d’apparition progressives pendant le défilement, désactivées si l’appareil demande moins d’animation; le contenu reste utilisable sans JavaScript.
- **Fichiers privés** : les achats et supports sont servis par des vues qui vérifient le membre, la commande payée ou l’inscription au cours. `private-media/` n’est pas exposé comme répertoire public.
- **Paiements** : le socle enregistre une déclaration avec moyen, numéro émetteur et référence. Seul un membre du personnel peut la confirmer après contrôle dans le compte de réception. Aucun prestataire mobile money n’est présenté comme intégré et aucun webhook ou faux paiement n’est simulé.
- **Commissions** : calculées exclusivement lors de la confirmation d’une commande numérique payée. La base retenue (100 % par défaut), le plafond par niveau et commande, les taux et le délai sont configurables. Les lignes restent bloquées par défaut; l’activation nécessite les deux indicateurs `Commissions activées` et `Simulation et validation juridique/financière effectuées`.

## Données et accès

- **Données métier** : `Member` et son parrain, `DigitalProduct`, `Order`/`OrderItem`, `PaymentSubmission`, `Course`/`Lesson`/`Enrollment`, `Commission`, `WalletEntry`, `WithdrawalRequest`, `Notification`, `ContactMessage` et `AuditLog`.
- **Arbre de parrainage** : exploration progressive et paginée jusqu’à 100 niveaux; chaque membre voit son parrain, ses filleuls, leurs niveaux et leur parrain direct. E-mail et téléphone sont affichés seulement si la personne a choisi de les partager; chacun peut modifier ce choix depuis son tableau de bord.
- **Catalogue de packs** : six services à l’unité, quatre combinaisons et une formule Premium sont initialisés dans `/packs/`. Les six logos transmis par KPYX sont associés aux services et inclus dans l’archive du projet. Les futures images raster peuvent se gérer dans `/admin/`; tarifs et ventes restent désactivés tant que les conditions, les fournisseurs et l’accès autorisé ne sont pas validés. L’image IPTV fournie est celle de l’application Smarters Player; le fournisseur d’accès IPTV reste à définir.
- **Public** : catalogue, formations publiées, blog, FAQ et formulaire de contact. Une déclaration de paiement ne valide jamais un membre et ne délivre pas un achat.
- **Membre connecté** : accès limité à son profil, ses commandes et téléchargements payés, ses cours inscrits, ses filleuls sur trois niveaux, ses notifications, son portefeuille et ses retraits. Les fichiers privés sont servis par des vues avec contrôle d’accès.
- **Personnel** : `/admin/` utilise les permissions Django (`is_staff`, groupes et permissions). Le personnel peut vérifier les paiements, examiner les retraits, gérer le catalogue et consulter les journaux; les actions financières nécessitent des références de paiement effectif. `/gestion/` est réservé au personnel.

Le code de parrainage reste facultatif à l’inscription par défaut. Les coordonnées des filleuls ne sont pas exposées automatiquement : chaque membre peut choisir et révoquer leur partage dans son espace. Les packs apparaissent avec un tarif à confirmer et une période prévue de trois jours; aucune souscription ni livraison d’identifiants n’est activée dans cette version.

Le code de parrainage est facultatif par défaut et peut être rendu obligatoire dans les réglages. Le lien WhatsApp n’apparaît qu’après configuration de `KPYX_WHATSAPP_NUMBER` dans l’environnement, au format international sans `+`. Le catalogue et les cours ne sont pas préremplis avec de faux produits : ils sont créés depuis `/admin/`.

## Structure

```text
config/                 Paramètres et routes Django
core/models.py          Membres, produits, cours, commandes, wallet, commissions, audit
core/services.py        Validation des paiements et règles financières atomiques
core/admin.py           Gestion du catalogue et opérations réservées au personnel
core/management/        Simulation et libération des commissions arrivées à échéance
core/tests.py           Tests des flux et invariants financiers
templates/              Pages publiques, membre et administration
static/core/site.css    Interface responsive KPYX
```

## Installation locale

1. Créer un environnement Python 3.14 et installer les dépendances :

   ```powershell
   py -3.14 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

2. Générer une clé secrète dédiée dans `.env`. En local, conserver `DJANGO_DEBUG=True`. La base SQLite est créée automatiquement à la racine du projet.

3. Créer les tables et le compte administrateur :

   ```powershell
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver
   ```

4. Dans `/admin/`, configurer d’abord les moyens et instructions de paiement, puis publier des produits et des cours. Ne renseignez les coordonnées de réception qu’après vérification de leur propriété et de leur sécurité.

   Si vous souhaitez afficher un contact WhatsApp, renseignez `KPYX_WHATSAPP_NUMBER` dans `.env` avec le numéro international sans signe `+`.

Les URL publiques sont `/`, `/boutique/`, `/academy/`, `/packs/`, `/opportunites/`, `/a-propos/`, `/blog/`, `/contact/`, `/faq/`, `/inscription/` et `/connexion/`. Les vues de gestion sont dans `/gestion/` et `/admin/`.

## Paiements et mise en production

La référence saisie par le membre est une demande de rapprochement, jamais une preuve suffisante. Depuis l’administration, vérifier la réception réelle auprès de l’opérateur puis utiliser l’action « Vérifier les paiements ». La confirmation d’une commande crée les droits de téléchargement et, le cas échéant, les commissions. La confirmation des frais d’inscription ne crée aucune commission.

La V1 n’inclut pas encore de contrat API avec Orange Money, MTN Money, Moov Money, Wave ou un agrégateur. Il faut choisir un prestataire, obtenir un compte marchand et ses secrets, puis développer et éprouver son adaptateur serveur/webhook avant d’afficher un paiement automatisé. Les instructions manuelles ne remplacent pas cette intégration.

Pour PostgreSQL, définir `DATABASE_URL` avec une URL PostgreSQL, par exemple `postgresql://kpyx:mot-de-passe@localhost:5432/kpyx`. Avant le déploiement :

- définir une clé secrète aléatoire, `DJANGO_DEBUG=False`, les domaines autorisés et origines CSRF dans `.env`;
- terminer `python manage.py collectstatic` et `python manage.py check --deploy`;
- configurer TLS, sauvegardes PostgreSQL, supervision, limitation de débit et stockage objet privé avec URLs signées pour les fichiers;
- conserver les secrets du prestataire hors de la base, du dépôt et de l’interface d’administration;
- faire examiner le modèle de frais, le plan de rémunération à trois niveaux, la protection des données et les obligations locales par des professionnels qualifiés avant le lancement.

La base configurée par défaut est la somme des prix des articles enregistrés dans la commande confirmée. Un pourcentage de cette base est retenu, puis les taux par niveau s’appliquent avec un éventuel plafond par niveau et commande. Les taux fournis totalisent **78 %** de la base retenue; la commande suivante permet une simulation hypothétique sans écrire de mouvement financier :

```powershell
python manage.py simulate_commissions --base 100000
```

Les commissions arrivées à échéance peuvent être libérées par la commande `python manage.py release_matured_commissions`, à planifier après le délai configuré. L’administration peut aussi libérer les lignes mûres manuellement.

## Plan de développement

### Packs numériques

Les prix individuels communiqués sont des paiements uniques : Spotify 6 500 FCFA, Crunchyroll 8 000 FCFA, Apple Music 3 000 FCFA, Netflix 10 000 FCFA pour 20 accès, et IPTV 5 000 FCFA pour 3 comptes. Les packs combinés et Premium additionnent leurs services puis appliquent à chaque pack une remise pseudo-aléatoire distincte de 5 à 15 %, stable pour la journée et recalculée à minuit, heure d’Abidjan. Une page Packs restée ouverte se recharge après le changement de jour. Le prix du VPN reste variable selon le fournisseur choisi avec l’assistant; les totaux finaux du Quadri et du Premium seront calculés après ce devis. La barre de navigation des packs est fixe au défilement et s’adapte aux écrans mobiles. Les boutons « Obtenir le pack » créent seulement une demande de contact préremplie; les ventes et la livraison d’identifiants restent désactivées jusqu’à validation des droits fournisseurs et du mode de distribution.

1. **Lot livré** : vitrine, catalogue, comptes et statuts, revue manuelle des paiements, commandes numériques, accès protégé, Academy et suivi de progression, trois niveaux de parrainage, commissions bloquées par défaut, portefeuille, retraits, administration et audit.
2. **À finaliser avant lancement public** : prestataire de paiement réel et webhooks signés, stockage privé de production, emails transactionnels, politique de remboursement, validation juridique/financière, règles de commission (base, plafond, délai) et contrôle de sécurité indépendant.
3. **V2** : produits physiques, inventaire, logistique; l’architecture actuelle garde le catalogue et les commandes séparés pour ne pas activer ces flux dans la V1.
4. **V3** : devises multiples, internationalisation et application mobile éventuelle.

## Tests

```powershell
python manage.py test
```

Les tests couvrent les pages publiques et le tableau de bord, la non-activation sur simple déclaration, le blocage d’une seconde déclaration, les commissions sur commandes confirmées, l’absence de double génération, le pourcentage de base et le plafond, le retrait après approbation, l’annulation des commissions après remboursement référencé, l’authentification de l’API, le panier calculé côté serveur, l’arbre limité au 100ᵉ niveau et le partage optionnel des coordonnées.

## Compte KPYX

Les formulaires d’inscription acceptent les indicatifs ouest-africains avec leurs drapeaux; le numéro est stocké avec l’indicatif sélectionné. Le bonus de bienvenue de 500 FCFA est crédité une seule fois après vérification effective du paiement d’activation. Le lien « Mot de passe oublié » utilise le flux sécurisé de réinitialisation Django. Pour envoyer les e-mails en production, renseigner les variables SMTP `DJANGO_EMAIL_*` dans l’environnement du serveur; elles ne doivent pas être enregistrées dans Git.
