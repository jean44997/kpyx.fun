import { json, methodNotAllowed } from '../_lib.js';

const EDGE_FUNCTION = 'https://vxjxgehyyzwxxqbstalx.supabase.co/functions/v1/kpyx-telegram-admin';

export default async function handler(req, res) {
  if (req.method !== 'POST') return methodNotAllowed(req, res);
  try {
    const response = await fetch(EDGE_FUNCTION, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-telegram-bot-api-secret-token': String(req.headers['x-telegram-bot-api-secret-token'] || ''),
      },
      body: JSON.stringify(req.body || {}),
    });
    const body = await response.json().catch(() => ({ error: 'Réponse du service bot invalide.' }));
    return json(res, response.status, body);
  } catch (error) {
    console.error('Telegram webhook proxy failed:', error?.message || 'unknown error');
    return json(res, 502, { error: 'Service Telegram temporairement indisponible.' });
  }
}
