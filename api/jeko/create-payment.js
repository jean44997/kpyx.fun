import { db, json, methodNotAllowed, requireUser } from '../_lib.js';

const METHODS = new Set(['wave', 'orange', 'mtn', 'moov', 'djamo']);

export default async function handler(req, res) {
  if (req.method !== 'POST') return methodNotAllowed(req, res);
  try {
    const user = await requireUser(req);
    if (!user) return json(res, 401, { error: 'Connectez-vous pour recharger votre compte.' });
    const amount = Number(req.body?.amount);
    const method = String(req.body?.paymentMethod || '').toLowerCase();
    if (!Number.isSafeInteger(amount) || amount < 3000 || amount > 1000000 || amount % 100 !== 0) {
      return json(res, 400, { error: 'Le montant doit être compris entre 3 000 et 1 000 000 FCFA.' });
    }
    if (!METHODS.has(method)) return json(res, 400, { error: 'Moyen de paiement non accepté.' });
    const key = process.env.JEKO_API_KEY;
    const keyId = process.env.JEKO_API_KEY_ID;
    const storeId = process.env.JEKO_STORE_ID;
    if (!key || !keyId || !storeId) return json(res, 503, { error: 'Le paiement en ligne est en cours de configuration.' });

    const recent = await db(`payment_events?select=id&user_id=eq.${encodeURIComponent(user.id)}&event_type=eq.topup&status=eq.pending&created_at=gte.${encodeURIComponent(new Date(Date.now() - 10 * 60 * 1000).toISOString())}`);
    if (recent.length >= 3) return json(res, 429, { error: 'Trop de paiements en attente. Réessayez dans quelques minutes.' });

    const reference = `KPYX-${crypto.randomUUID()}`;
    await db('payment_events', {
      method: 'POST',
      headers: { Prefer: 'return=minimal' },
      body: JSON.stringify({ user_id: user.id, provider: 'jeko', provider_event_id: reference, event_type: 'topup', amount_xof: amount, status: 'pending', metadata: { payment_method: method } }),
    });
    const origin = `https://${req.headers.host}`;
    const jekoResponse = await fetch('https://api.jeko.africa/partner_api/payment_requests', {
      method: 'POST',
      headers: { 'X-API-KEY': key, 'X-API-KEY-ID': keyId, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        storeId, amountCents: amount * 100, currency: 'XOF', reference,
        paymentDetails: { type: 'redirect', data: { paymentMethod: method, successUrl: `${origin}/recharge?status=pending`, errorUrl: `${origin}/recharge?status=failed` } },
      }),
    });
    const result = await jekoResponse.json().catch(() => ({}));
    if (!jekoResponse.ok || !result.redirectUrl) {
      await db(`payment_events?provider=eq.jeko&provider_event_id=eq.${encodeURIComponent(reference)}`, { method: 'PATCH', body: JSON.stringify({ status: 'failed' }) });
      return json(res, 502, { error: 'Jèko n’a pas pu créer le paiement. Réessayez.' });
    }
    await db(`payment_events?provider=eq.jeko&provider_event_id=eq.${encodeURIComponent(reference)}`, {
      method: 'PATCH', body: JSON.stringify({ metadata: { payment_method: method, jeko_payment_request_id: result.id } }),
    });
    return json(res, 200, { redirectUrl: result.redirectUrl, reference });
  } catch (error) {
    console.error('Jeko checkout failed:', error.message);
    return json(res, 500, { error: 'Impossible de démarrer le paiement pour le moment.' });
  }
}
