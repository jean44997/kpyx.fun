import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const MAX_TEXT = 900;
const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const supabase = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

function sameSecret(actual: string | null, expected: string): boolean {
  if (!actual || actual.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < actual.length; i++) diff |= actual.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

async function telegram(token: string, method: string, body: Record<string, unknown>) {
  const response = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error('Telegram API request failed');
  return result;
}

async function reply(token: string, chatId: number, text: string) {
  await telegram(token, 'sendMessage', { chat_id: chatId, text, disable_web_page_preview: true });
}

async function sendPush(userIds: string[], title: string, body: string) {
  const url = Deno.env.get('PUSH_DELIVERY_URL');
  const secret = Deno.env.get('PUSH_DELIVERY_SECRET');
  if (!url || !secret) return { delivered: 0, failed: true };
  try {
    const response = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'x-kpyx-push-secret': secret },
      body: JSON.stringify({ user_ids: userIds, title, body }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`Push endpoint returned ${response.status}`);
    return { delivered: Number(result.delivered) || 0, failed: Number(result.failed) > 0 };
  } catch (error) {
    console.error('Push batch failed:', error instanceof Error ? error.message : 'unknown error');
    return { delivered: 0, failed: true };
  }
}

async function notifyOne(userId: string, title: string, body: string) {
  const adminBatchId = crypto.randomUUID();
  const { error } = await supabase.from('notifications').insert({ user_id: userId, title: title.slice(0, 80), body: body.slice(0, MAX_TEXT), kind: 'account', admin_batch_id: adminBatchId });
  if (error) throw error;
  return { adminBatchId, push: await sendPush([userId], title, body) };
}

async function broadcast(body: string) {
  const adminBatchId = crypto.randomUUID();
  let offset = 0, total = 0, pushDelivered = 0, pushFailed = false;
  for (;;) {
    const { data: users, error } = await supabase.from('profiles').select('id').order('id').range(offset, offset + 499);
    if (error) throw error;
    if (!users?.length) break;
    for (let i = 0; i < users.length; i += 100) {
      const rows = users.slice(i, i + 100).map(({ id }) => ({ user_id: id, title: 'Annonce KPYX', body: body.slice(0, MAX_TEXT), kind: 'account', admin_batch_id: adminBatchId }));
      const { error: insertError } = await supabase.from('notifications').insert(rows);
      if (insertError) throw insertError;
      total += rows.length;
      const push = await sendPush(rows.map(({ user_id }) => user_id), 'Annonce KPYX', body);
      pushDelivered += push.delivered;
      pushFailed ||= push.failed;
    }
    if (users.length < 500) break;
    offset += 500;
    if (offset >= 50000) throw new Error('Broadcast recipient safety limit reached');
  }
  return { total, pushDelivered, pushFailed, adminBatchId };
}

Deno.serve(async (req: Request) => {
  if (req.method !== 'POST') return new Response('Method not allowed', { status: 405, headers: { Allow: 'POST' } });
  const botToken = Deno.env.get('TELEGRAM_BOT_TOKEN');
  const adminId = Deno.env.get('TELEGRAM_ADMIN_CHAT_ID');
  const webhookSecret = Deno.env.get('TELEGRAM_WEBHOOK_SECRET');
  if (!botToken || !adminId || !webhookSecret) return Response.json({ error: 'Bot is not configured' }, { status: 503 });
  if (!sameSecret(req.headers.get('x-telegram-bot-api-secret-token'), webhookSecret)) return Response.json({ error: 'Unauthorized' }, { status: 401 });

  let update: any;
  try { update = await req.json(); } catch { return Response.json({ error: 'Invalid JSON' }, { status: 400 }); }
  const message = update?.message;
  const chatId = message?.chat?.id;
  // Authorize by the sender, not the destination chat: in a group, chat.id is
  // the group ID while from.id remains the configured administrator ID.
  if (!message || String(message.from?.id) !== adminId) return Response.json({ ok: true });

  try {
    if (Number.isSafeInteger(update.update_id)) {
      const { data: previous, error: lookupError } = await supabase.from('telegram_admin_updates').select('update_id').eq('update_id', update.update_id).maybeSingle();
      if (lookupError) throw lookupError;
      if (previous) return Response.json({ ok: true, duplicate: true });
      const { error: insertError } = await supabase.from('telegram_admin_updates').insert({ update_id: update.update_id });
      if (insertError) throw insertError;
    }

    const input = String(message.text || '').trim();
    const command = (input.match(/^\/[a-z_]+(?:@\w+)?/i)?.[0] || '').replace(/@\w+$/, '').toLowerCase();
    const rest = input.replace(/^\/[^\s]+\s*/i, '').trim();
    if (command === '/start' || command === '/help') {
      await reply(botToken, chatId, 'Commandes admin KPYX:\n/code <montant> <utilisations> [CODE]\n/send <UUID utilisateur> <message>\n/all <message> (tous les comptes)\n/delete <ID notification> (retire une notification / annonce du site)');
    } else if (command === '/code') {
      const [amountText, usesText, requestedCode] = rest.split(/\s+/);
      const amount = Number(amountText), uses = Number(usesText);
      const generated = new Uint8Array(5); crypto.getRandomValues(generated);
      const code = String(requestedCode || `KPYX-${Array.from(generated, x => x.toString(16).padStart(2, '0')).join('')}`).toUpperCase();
      if (!Number.isSafeInteger(amount) || amount < 1 || amount > 100000000 || !Number.isSafeInteger(uses) || uses < 1 || uses > 1000000 || !/^[A-Z0-9_-]{4,40}$/.test(code)) {
        await reply(botToken, chatId, 'Format invalide. Exemple : /code 500 25 KPYX500');
      } else {
        const { error } = await supabase.from('gift_codes').insert({ code, amount_xof: amount, max_uses: uses });
        if (error) throw error;
        await reply(botToken, chatId, `Code créé : ${code}\nBonus : ${amount.toLocaleString('fr-FR')} FCFA\nUtilisations : ${uses}`);
      }
    } else if (command === '/send') {
      const match = rest.match(/^([0-9a-f-]{36})\s+([\s\S]+)$/i);
      if (!match || match[2].trim().length > MAX_TEXT) await reply(botToken, chatId, 'Format : /send <UUID utilisateur> <message> (900 caractères maximum).');
      else {
        const { data: user, error } = await supabase.from('profiles').select('id').eq('id', match[1]).maybeSingle();
        if (error) throw error;
        if (!user) await reply(botToken, chatId, 'Utilisateur introuvable. Utilise son UUID de profil.');
        else {
          const result = await notifyOne(user.id, 'Message de KPYX', match[2].trim());
          await reply(botToken, chatId, `${result.push.failed ? 'Notification ajoutée à la boîte KPYX ; la livraison Push serveur a échoué.' : `Notification enregistrée. Push envoyé à ${result.push.delivered} appareil(s).`}\nID à utiliser avec /delete : ${result.adminBatchId}`);
        }
      }
    } else if (command === '/all' || command === '/broadcast') {
      if (!rest || rest.length > MAX_TEXT) await reply(botToken, chatId, 'Format : /all <message> (900 caractères maximum).' );
      else {
        const result = await broadcast(rest);
        await reply(botToken, chatId, `Notification enregistrée pour ${result.total} compte(s). Push envoyé à ${result.pushDelivered} appareil(s).${result.pushFailed ? '\nCertains envois Push ont échoué ; la notification reste dans la boîte KPYX.' : ''}\nID à utiliser avec /delete : ${result.adminBatchId}`);
      }
    } else if (command === '/delete') {
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(rest)) {
        await reply(botToken, chatId, 'Format : /delete <ID notification>. Utilise l’ID donné après /send ou /all.');
      } else {
        const { data, error } = await supabase.from('notifications').delete().eq('admin_batch_id', rest).select('id');
        if (error) throw error;
        const deleted = data?.length || 0;
        await reply(botToken, chatId, deleted ? `${deleted} notification(s) supprimée(s) de la boîte KPYX.` : 'Aucune notification trouvée pour cet ID ; elle a peut-être déjà été supprimée.');
      }
    } else {
      await reply(botToken, chatId, 'Commande inconnue. Envoie /help pour voir les commandes.');
    }
    return Response.json({ ok: true });
  } catch (error) {
    console.error('Telegram admin command failed:', error instanceof Error ? error.message : 'unknown error');
    try { await reply(botToken, chatId, 'Action non terminée. Vérifie la configuration puis réessaie.'); } catch { /* Telegram may be temporarily unavailable. */ }
    return Response.json({ error: 'Command failed' }, { status: 500 });
  }
});
