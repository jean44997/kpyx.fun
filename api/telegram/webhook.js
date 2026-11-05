import { randomBytes, timingSafeEqual } from 'node:crypto';
import { db, json, methodNotAllowed } from '../_lib.js';

const MAX_TEXT = 900;

function sameSecret(actual, expected) {
  if (!actual || !expected) return false;
  const a = Buffer.from(String(actual));
  const b = Buffer.from(String(expected));
  return a.length === b.length && timingSafeEqual(a, b);
}

async function reply(chatId, text) {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: true }),
  });
  if (!response.ok) throw new Error('Telegram reply failed');
}

function safeTitle(value) {
  return String(value || '').trim().slice(0, 80) || 'Message de KPYX';
}

async function sendNotification(userId, title, body) {
  await db('notifications', {
    method: 'POST', headers: { Prefer: 'return=minimal' },
    body: JSON.stringify({ user_id: userId, title: safeTitle(title), body: body.slice(0, MAX_TEXT), kind: 'account' }),
  });
}

async function broadcast(title, body) {
  let offset = 0, sent = 0;
  for (;;) {
    const users = await db(`profiles?select=id&order=id.asc&limit=500&offset=${offset}`);
    if (!Array.isArray(users) || users.length === 0) break;
    for (let i = 0; i < users.length; i += 100) {
      const batch = users.slice(i, i + 100).map(({ id }) => ({ user_id: id, title: safeTitle(title), body: body.slice(0, MAX_TEXT), kind: 'account' }));
      await db('notifications', { method: 'POST', headers: { Prefer: 'return=minimal' }, body: JSON.stringify(batch) });
      sent += batch.length;
    }
    if (users.length < 500) break;
    offset += users.length;
  }
  return sent;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return methodNotAllowed(req, res);
  const expectedSecret = process.env.TELEGRAM_WEBHOOK_SECRET;
  const expectedAdmin = process.env.TELEGRAM_ADMIN_CHAT_ID;
  if (!process.env.TELEGRAM_BOT_TOKEN || !expectedSecret || !expectedAdmin) return json(res, 503, { error: 'Bot Telegram non configuré.' });
  if (!sameSecret(req.headers['x-telegram-bot-api-secret-token'], expectedSecret)) return json(res, 401, { error: 'Webhook non autorisé.' });

  const update = req.body || {};
  const message = update.message;
  const chatId = message?.chat?.id;
  if (!message || String(chatId) !== String(expectedAdmin) || String(message.from?.id) !== String(expectedAdmin)) return json(res, 200, { ok: true });

  try {
    if (Number.isSafeInteger(update.update_id)) {
      const previous = await db(`telegram_admin_updates?update_id=eq.${update.update_id}&select=update_id`);
      if (previous?.length) return json(res, 200, { ok: true, duplicate: true });
      await db('telegram_admin_updates', { method: 'POST', headers: { Prefer: 'return=minimal' }, body: JSON.stringify({ update_id: update.update_id }) });
    }

    const input = String(message.text || '').trim();
    const command = input.replace(/^\/([a-z_]+)(?:@\w+)?/i, '/$1').split(/\s+/)[0].toLowerCase();
    const rest = input.replace(/^\/[^\s]+\s*/i, '').trim();

    if (command === '/start' || command === '/help') {
      await reply(chatId, 'Commandes admin KPYX:\n/code <montant> <utilisations> [CODE]\n/send <UUID utilisateur> <message>\n/broadcast <message>');
    } else if (command === '/code') {
      const [amountText, usesText, requestedCode] = rest.split(/\s+/);
      const amount = Number(amountText), uses = Number(usesText);
      const code = String(requestedCode || `KPYX-${randomBytes(5).toString('hex').toUpperCase()}`).toUpperCase();
      if (!Number.isSafeInteger(amount) || amount < 1 || amount > 100000000 || !Number.isSafeInteger(uses) || uses < 1 || uses > 1000000 || !/^[A-Z0-9_-]{4,40}$/.test(code)) {
        await reply(chatId, 'Format invalide. Exemple : /code 500 25 KPYX500');
      } else {
        await db('gift_codes', { method: 'POST', headers: { Prefer: 'return=minimal' }, body: JSON.stringify({ code, amount_xof: amount, max_uses: uses }) });
        await reply(chatId, `Code créé : ${code}\nBonus : ${amount.toLocaleString('fr-FR')} FCFA\nUtilisations : ${uses}`);
      }
    } else if (command === '/send') {
      const match = rest.match(/^([0-9a-f-]{36})\s+([\s\S]+)$/i);
      if (!match || match[2].trim().length > MAX_TEXT) await reply(chatId, 'Format : /send <UUID utilisateur> <message> (900 caractères maximum).');
      else {
        const users = await db(`profiles?id=eq.${match[1]}&select=id&limit=1`);
        if (!users?.length) await reply(chatId, 'Utilisateur introuvable. Utilise son UUID de profil.');
        else { await sendNotification(users[0].id, 'Message de KPYX', match[2].trim()); await reply(chatId, 'Notification envoyée dans le site.'); }
      }
    } else if (command === '/broadcast') {
      if (!rest || rest.length > MAX_TEXT) await reply(chatId, 'Format : /broadcast <message> (900 caractères maximum).');
      else { const count = await broadcast('Annonce KPYX', rest); await reply(chatId, `Notification envoyée à ${count} compte(s).`); }
    } else {
      await reply(chatId, 'Commande inconnue. Envoie /help pour voir les commandes.');
    }
    return json(res, 200, { ok: true });
  } catch (error) {
    console.error('Telegram admin webhook failed:', error.message);
    try { await reply(chatId, 'Action non terminée. Vérifie la configuration puis réessaie.'); } catch {}
    return json(res, 500, { error: 'Action du bot impossible.' });
  }
}
