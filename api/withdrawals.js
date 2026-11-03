import { json, methodNotAllowed, requireUser, rpc } from './_lib.js';

const METHODS = new Set(['wave', 'orange', 'mtn', 'moov', 'djamo']);

export default async function handler(req, res) {
  if (req.method !== 'POST') return methodNotAllowed(req, res);
  try {
    const user = await requireUser(req);
    if (!user) return json(res, 401, { error: 'Connectez-vous pour demander un retrait.' });
    const amount = Number(req.body?.amount);
    const method = String(req.body?.method || '').toLowerCase();
    const account = String(req.body?.account || '').trim();
    if (!Number.isSafeInteger(amount) || amount < 1200 || amount > 1000000 || amount % 100 !== 0) return json(res, 400, { error: 'Montant minimum de retrait : 1 200 FCFA.' });
    if (!METHODS.has(method) || account.length < 6 || account.length > 80) return json(res, 400, { error: 'Renseignez un moyen de paiement et son numéro.' });
    const result = await rpc('kpyx_request_withdrawal', { p_user_id: user.id, p_amount_xof: amount, p_method: method, p_destination: account });
    return json(res, 202, { status: 'pending', fee: Math.round(amount * 0.07), net: amount - Math.round(amount * 0.07), requestId: result });
  } catch (error) {
    console.error('Withdrawal request failed:', error.message);
    return json(res, 400, { error: 'Demande impossible. Vérifiez le solde disponible et réessayez.' });
  }
}

