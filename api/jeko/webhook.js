import { createHmac, timingSafeEqual } from 'node:crypto';
import { json, rpc } from '../_lib.js';

export const config = { api: { bodyParser: false } };

async function rawBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'Méthode non autorisée.' });
  try {
    const body = await rawBody(req);
    const secret = process.env.JEKO_WEBHOOK_SECRET;
    const received = String(req.headers['jeko-signature'] || '').toLowerCase();
    if (!secret || !/^[a-f0-9]{64}$/.test(received)) return json(res, 401, { error: 'Signature invalide.' });
    const expected = createHmac('sha256', secret).update(body).digest();
    const actual = Buffer.from(received, 'hex');
    if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) return json(res, 401, { error: 'Signature invalide.' });

    const event = JSON.parse(body.toString('utf8'));
    if (!process.env.JEKO_STORE_ID || event?.storeId !== process.env.JEKO_STORE_ID) return json(res, 401, { error: 'Magasin Jèko invalide.' });
    const reference = event?.transactionDetails?.reference;
    if (!reference || event?.transactionType !== 'payment') return json(res, 200, { received: true, ignored: true });
    const status = event.status === 'success' ? 'confirmed' : event.status === 'error' ? 'failed' : 'pending';
    if (status === 'pending') return json(res, 200, { received: true });
    // Jèko's amountCents and MoneyModel.amount fields are in 1/100 XOF.
    const amountCents = Number(event?.amount?.amount);
    if (!Number.isSafeInteger(amountCents) || amountCents <= 0 || amountCents % 100 !== 0 || event?.amount?.currency !== 'XOF') return json(res, 400, { error: 'Montant invalide.' });
    const amountXof = amountCents / 100;
    await rpc('kpyx_apply_jeko_topup', { p_reference: reference, p_transaction_id: String(event.id || event.transactionDetails?.id), p_status: status, p_amount_xof: amountXof });
    return json(res, 200, { received: true });
  } catch (error) {
    console.error('Jeko webhook failed:', error.message);
    return json(res, 500, { error: 'Webhook non traité.' });
  }
}
