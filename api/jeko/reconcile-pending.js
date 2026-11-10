import { db, json, requireUser, rpc } from '../_lib.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return json(res, 405, { error: 'Méthode non autorisée.' });
  }
  try {
    const user = await requireUser(req);
    if (!user) return json(res, 401, { error: 'Connectez-vous pour actualiser vos recharges.' });
    const apiKey = process.env.JEKO_API_KEY;
    const keyId = process.env.JEKO_API_KEY_ID;
    const storeId = process.env.JEKO_STORE_ID;
    if (!apiKey || !keyId || !storeId) return json(res, 503, { error: 'Vérification Jèko momentanément indisponible.' });

    const since = new Date(Date.now() - 30 * 86400000).toISOString();
    const payments = await db(`payment_events?select=id,provider_event_id,amount_xof,metadata&provider=eq.jeko&event_type=eq.topup&status=eq.pending&user_id=eq.${encodeURIComponent(user.id)}&created_at=gte.${encodeURIComponent(since)}&order=created_at.desc&limit=5`);
    let confirmed = 0, failed = 0, checked = 0;

    // Bound provider calls per signed-in member and reconcile sequentially to avoid rate spikes.
    for (const payment of payments || []) {
      const reference = String(payment.provider_event_id || '');
      const requestId = String(payment.metadata?.jeko_payment_request_id || '');
      if (!/^KPYX-[0-9a-f-]{36}$/i.test(reference) || !requestId || requestId.length > 160) continue;
      const response = await fetch(`https://api.jeko.africa/partner_api/payment_requests/${encodeURIComponent(requestId)}`, {
        headers: { 'X-API-KEY': apiKey, 'X-API-KEY-ID': keyId },
      });
      if (!response.ok) continue;
      const request = await response.json();
      if (request?.storeId !== storeId || request?.reference !== reference) continue;
      checked++;
      if (request.status === 'success') {
        const amountCents = Number(request.transaction?.amount?.amount);
        if (request.transaction?.amount?.currency !== 'XOF' || !Number.isSafeInteger(amountCents) || amountCents <= 0 || amountCents % 100 !== 0 || amountCents / 100 !== Number(payment.amount_xof)) continue;
        await rpc('kpyx_apply_jeko_topup', {
          p_reference: reference,
          p_transaction_id: String(request.transaction?.id || request.id),
          p_status: 'confirmed',
          p_amount_xof: amountCents / 100,
        });
        confirmed++;
      } else if (request.status === 'error') {
        await rpc('kpyx_apply_jeko_topup', {
          p_reference: reference,
          p_transaction_id: String(request.transaction?.id || request.id),
          p_status: 'failed',
          p_amount_xof: Number(payment.amount_xof),
        });
        failed++;
      }
    }
    return json(res, 200, { checked, confirmed, failed, stillPending: Math.max(0, (payments?.length || 0) - confirmed - failed) });
  } catch (error) {
    console.error('Pending Jeko reconciliation failed:', error.message);
    return json(res, 500, { error: 'Impossible d’actualiser les recharges pour le moment.' });
  }
}

