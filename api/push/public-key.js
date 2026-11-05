import { json, methodNotAllowed } from '../_lib.js';

export default function handler(req, res) {
  if (req.method !== 'GET') return methodNotAllowed(req, res, 'GET');
  const publicKey = process.env.VAPID_PUBLIC_KEY;
  if (!publicKey) return json(res, 503, { error: 'Notifications push non configurées.' });
  res.setHeader('Access-Control-Allow-Origin', 'https://kpyx.fun');
  return json(res, 200, { publicKey });
}
