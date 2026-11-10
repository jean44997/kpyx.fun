import { json, methodNotAllowed, requireUser, rpc } from '../_lib.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') return methodNotAllowed(req, res);
  try {
    const user = await requireUser(req);
    if (!user) return json(res, 401, { error: 'Connectez-vous pour actualiser vos crédits VIP.' });
    const settledXof = await rpc('kpyx_settle_matured_vips', { p_user_id: user.id });
    return json(res, 200, { ok: true, settledXof: Number(settledXof || 0) });
  } catch (error) {
    console.error('VIP maturity settlement failed:', error.message);
    return json(res, 500, { error: 'Impossible d’actualiser les crédits VIP pour le moment.' });
  }
}

