import { json, methodNotAllowed, requireUser, rpc } from '../_lib.js';

const OPEN_VIP_PLANS = new Set(['VIP1', 'VIP2', 'VIP3', 'VIP4']);

export default async function handler(req, res) {
  if (req.method !== 'POST') return methodNotAllowed(req, res);
  try {
    const user = await requireUser(req);
    if (!user) return json(res, 401, { error: 'Connectez-vous pour souscrire à un forfait.' });

    const planId = String(req.body?.planId || '').toUpperCase();
    if (!OPEN_VIP_PLANS.has(planId)) return json(res, 400, { error: 'Ce forfait VIP n’est pas encore ouvert.' });

    const result = await rpc('kpyx_purchase_vip', { p_user_id: user.id, p_plan_id: planId });
    if (!result?.ok) {
      if (result?.error === 'insufficient_balance') {
        return json(res, 409, { error: 'Solde insuffisant.', balanceXof: result.balance_xof, priceXof: result.price_xof });
      }
      if (result?.error === 'plan_unavailable') return json(res, 400, { error: 'Ce forfait VIP n’est pas encore ouvert.' });
      return json(res, 500, { error: 'La souscription n’a pas pu être finalisée. Votre solde n’a pas été débité.' });
    }

    return json(res, 200, { ok: true, planId: result.plan_id, balanceXof: result.balance_xof, subscriptionId: result.subscription_id });
  } catch (error) {
    console.error('VIP purchase failed:', error.message);
    return json(res, 500, { error: 'La souscription n’a pas pu être finalisée. Réessayez.' });
  }
}

