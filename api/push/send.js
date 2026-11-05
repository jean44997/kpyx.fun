import webpush from 'web-push';
import { timingSafeEqual } from 'node:crypto';
import { db, json, methodNotAllowed } from '../_lib.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ALLOWED_PUSH_HOSTS = ['fcm.googleapis.com', 'updates.push.services.mozilla.com', 'push.services.mozilla.com', 'web.push.apple.com', 'push.apple.com', 'notify.windows.com'];
function authorized(received, expected) {
  if (!received || !expected) return false;
  const a = Buffer.from(String(received));
  const b = Buffer.from(String(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}
function validSubscription(subscription) {
  try {
    const url = new URL(subscription?.endpoint);
    return url.protocol === 'https:' && ALLOWED_PUSH_HOSTS.some(host => url.hostname === host || url.hostname.endsWith('.' + host)) && typeof subscription?.keys?.p256dh === 'string' && typeof subscription?.keys?.auth === 'string';
  } catch { return false; }
}
function expiredStatus(error) { return error?.statusCode === 404 || error?.statusCode === 410; }

export default async function handler(req, res) {
  if (req.method !== 'POST') return methodNotAllowed(req, res);
  if (!authorized(req.headers['x-kpyx-push-secret'], process.env.PUSH_DELIVERY_SECRET)) return json(res, 401, { error: 'Non autorisé.' });
  const publicKey = process.env.VAPID_PUBLIC_KEY, privateKey = process.env.VAPID_PRIVATE_KEY, subject = process.env.VAPID_SUBJECT;
  if (!publicKey || !privateKey || !subject) return json(res, 503, { error: 'Configuration Web Push incomplète.' });
  const payload = req.body || {};
  const userIds = [...new Set(Array.isArray(payload.user_ids) ? payload.user_ids.filter(id => typeof id === 'string' && UUID.test(id)) : [])].slice(0, 500);
  const title = String(payload.title || 'KPYX').trim().slice(0, 80);
  const body = String(payload.body || '').trim().slice(0, 180);
  if (!userIds.length || !body) return json(res, 400, { error: 'Destinataires ou message manquants.' });
  try {
    webpush.setVapidDetails(subject, publicKey, privateKey);
    const ids = userIds.join(',');
    const subscriptions = await db('push_subscriptions?select=id,user_id,endpoint,subscription&user_id=in.(' + ids + ')');
    let delivered = 0, expired = 0, failed = 0;
    const message = JSON.stringify({ title, body, url: '/messages' });
    for (let i = 0; i < subscriptions.length; i += 50) {
      const results = await Promise.allSettled(subscriptions.slice(i, i + 50).map(async row => {
        if (!validSubscription(row.subscription)) { failed++; return; }
        try {
          await webpush.sendNotification(row.subscription, message, { TTL: 3600, urgency: 'normal' });
          delivered++;
        } catch (error) {
          if (expiredStatus(error)) {
            expired++;
            await db('push_subscriptions?id=eq.' + encodeURIComponent(row.id), { method: 'DELETE' });
          } else failed++;
        }
      }));
      for (const result of results) if (result.status === 'rejected') failed++;
    }
    return json(res, 200, { delivered, expired, failed, subscriptions: subscriptions.length });
  } catch (error) {
    console.error('Push delivery failed:', error?.message || 'unknown error');
    return json(res, 500, { error: 'Échec de livraison push.' });
  }
}
