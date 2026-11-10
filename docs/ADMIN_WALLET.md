# Correction manuelle d’un solde KPYX

Les membres ne peuvent pas modifier `wallets.balance_xof` directement : les droits d’écriture sont coupés par RLS pour éviter les changements de solde sans journal financier.

Pour corriger un solde, utiliser le SQL Editor Supabase avec le compte administrateur du projet et la fonction auditée ci-dessous. Elle fixe le nouveau solde, écrit le delta dans `wallet_transactions` et conserve le motif, l’ancien solde, le nouveau solde et l’acteur dans `wallet_admin_adjustments`. Ne pas éditer la table `wallets` directement.

```sql
select public.kpyx_admin_set_wallet_balance(
  'UUID_DU_MEMBRE'::uuid,
  12500,
  'Correction après vérification du dépôt du 10 novembre'
);
```

Le second argument est le solde final en FCFA, pas le montant du delta. La fonction est inaccessible aux rôles `anon` et `authenticated`; elle est réservée au serveur et aux opérations du propriétaire du projet.

