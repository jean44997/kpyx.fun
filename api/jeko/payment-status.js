import { db, json, requireUser, rpc } from '../_lib.js';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return json(res, 405, { error: 'Méthode non autorisée.' });
  }
  try {
    const user = await requireUser(req);
    if (!user) return json(res, 401, { error: 'Connectez-vous pour vérifier cette recharge.' });

    const url = new URL(req.url, 'https://kpyx.fun');
    const reference = url.searchParams.get('reference') || '';
    if (!/^KPYX-[0-9a-f-]{36}$/i.test(reference)) return json(res, 400, { error: 'Référence de recharge invalide.' });

    const rows = await db(`payment_events?select=id,user_id,provider_event_id,amount_xof,status,metadata&provider=eq.jeko&provider_event_id=eq.${encodeURIComponent(reference)}&user_id=eq.${encodeURIComponent(user.id)}&limit=1`);
    const payment = rows?.[0];
    if (!payment) return json(res, 404, { error: 'Recharge introuvable.' });
    if (payment.status === 'confirmed') return json(res, 200, { status: 'confirmed' });
    if (payment.status === 'failed') return json(res, 200, { status: 'failed' });

    const requestId = payment.metadata?.jeko_payment_request_id;
    const apiKey = process.env.JEKO_API_KEY;
    const keyId = process.env.JEKO_API_KEY_ID;
    if (!requestId || !apiKey || !keyId) return json(res, 503, { error: 'Vérification du paiement momentanément indisponible.' });

    const response = await fetch(`https://api.jeko.africa/partner_api/payment_requests/${encodeURIComponent(requestId)}`, {
      headers: { 'X-API-KEY': apiKey, 'X-API-KEY-ID': keyId },
    });
    if (!response.ok) return json(res, 502, { error: 'Jèko ne peut pas encore confirmer cette recharge.' });
    const request = await response.json();
    if (request?.storeId !== process.env.JEKO_STORE_ID || request?.reference !== reference) {
      return json(res, 502, { error: 'La demande de paiement ne correspond pas à cette recharge.' });
    }

    if (request.status === 'success') {
      const amountCents = Number(request.transaction?.amount?.amount);
      const currency = request.transaction?.amount?.currency;
      const transactionId = request.transaction?.id || request.id;
      if (currency !== 'XOF' || !Number.isSafeInteger(amountCents) || amountCents <= 0 || amountCents % 100 !== 0 || amountCents / 100 !== Number(payment.amount_xof)) {
        return json(res, 502, { error: 'Le montant confirmé ne correspond pas à la recharge.' });
      }
      await rpc('kpyx_apply_jeko_topup', {
        p_reference: reference,
        p_transaction_id: String(transactionId),
        p_status: 'confirmed',
        p_amount_xof: amountCents / 100,
      });
      return json(res, 200, { status: 'confirmed' });
    }

    if (request.status === 'error') {
      await rpc('kpyx_apply_jeko_topup', {
        p_reference: reference,
        p_transaction_id: String(request.id),
        p_status: 'failed',
        p_amount_xof: Number(payment.amount_xof),
      });
      return json(res, 200, { status: 'failed' });
    }

    const retryAfter = Math.max(5, Math.min(3600, Number(response.headers.get('retry-after')) || 5));
    return json(res, 200, { status: 'pending', retryAfter });
  } catch (error) {
    console.error('Jeko payment status check failed:', error.message);
    return json(res, 500, { error: 'Impossible de vérifier le paiement pour le moment.' });
  }
}
