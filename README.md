# KPYX

This repository contains the KPYX member site and its Supabase schema migrations.

## Local preview

Run a static server from the repository root:

```powershell
python -m http.server 4174 --bind 127.0.0.1
```

Then open `http://127.0.0.1:4174/`.

## Supabase

The Supabase project reference is `vxjxgehyyzwxxqbstalx` (EU West, organization MIENTHY).
The initial schema and seed data are in `supabase/migrations/`. Apply future changes as new
migrations; do not edit already-applied migrations. Customer-facing tables use RLS, while
payment confirmation and access fulfillment are reserved for trusted server-side code.

The interface uses Supabase Auth and reads the catalog from Supabase. Phone and email
confirmations are disabled in the local Supabase configuration. The hosted project's Auth
provider setting still needs to be switched off in its dashboard. No SMS provider, payment
provider, or real account inventory is connected yet. Never put a Supabase service-role key
or raw account passwords in the browser or in this repository.
