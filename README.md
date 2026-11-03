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

The interface uses Supabase Auth and reads the catalog from Supabase. Phone + password
sign-in is backed by a deterministic non-routable email alias derived from the normalized
phone number, so the UI still uses phone numbers without sending SMS. Enable Supabase Email
Auth with email confirmations disabled on the hosted project; keep Phone Auth disabled unless
an SMS provider is configured. Phone ownership is not verified, so the user-provided number
is only a login identifier. Never put a Supabase service-role key or raw account passwords in
the browser or in this repository.

## Payments and account security

Apply the newest SQL migration in `supabase/migrations/` to the hosted Supabase project before enabling wallet requests. Configure these variables only in Vercel Project Settings → Environment Variables:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SERVICE_ROLE_KEY` (sensitive; server-side only)
- `JEKO_API_KEY` (sensitive; server-side only)
- `JEKO_API_KEY_ID`
- `JEKO_STORE_ID`
- `JEKO_WEBHOOK_SECRET` (sensitive; server-side only)

Set the Jèko webhook URL to `https://<production-domain>/api/jeko/webhook`. Checkout supports Wave, Orange Money, MTN, Moov, and Djamo. Withdrawals are manual and use the 7% fee. A signed Jèko webhook is the only event that credits a deposit.

Rotate any Jèko API key or webhook secret that has been pasted into a chat before placing the replacement in Vercel. Never commit the service-role key, payment credentials, or account passwords. Resale checkout stays disabled until real inventory and a secure delivery vault are connected; the database enforces a 25-customer cap per offer.
