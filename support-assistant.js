(() => {
  const knowledge = [
    { keys:['inscription','creer un compte','créer un compte','inscrire','numero','numéro','telephone','téléphone'], answer:'Pour créer un compte, indiquez votre numéro avec son indicatif, choisissez un nom d’utilisateur disponible et définissez votre mot de passe. Si le nom est déjà pris, essayez-en un autre.' },
    { keys:['nom utilisateur','username','profil','modifier nom','changer nom','photo profil','photo de profil'], answer:'Votre nom d’utilisateur sert de nom de profil. Vous pouvez compléter votre profil (prénom, nom, date de naissance et photo) dans « Mon compte ». Le changement de nom est soumis au délai affiché par le site.' },
    { keys:['mot de passe','mot passe','connexion','connecter','oublié','oublie','incorrect'], answer:'Depuis « Mot de passe oublié », suivez la procédure avec le numéro associé à votre compte. Si la connexion échoue, vérifiez le numéro et le mot de passe, puis réessayez.' },
    { keys:['recharge','depot','dépôt','deposer','déposer','recharger','wave','orange','mtn','moov','djamo','paiement'], answer:'Les moyens de recharge proposés sont Orange Money, MTN Money, Wave et Moov Money. Le dépôt minimum indiqué sur le site est de 3 000 FCFA. Consultez « Historique des recharges » pour suivre le statut.' },
    { keys:['retrait','retirer','frais','commission retrait'], answer:'Les retraits sont traités après demande et soumis à des frais de 7 %. Vérifiez le montant net et le moyen de paiement avant de confirmer, puis suivez la demande dans « Historique des retraits ».' },
    { keys:['vip1','vip 1','forfait','vip','abonnement','souscrire'], answer:'Les forfaits VIP s’achètent dans « Forfaits membres ». Le prix affiché sur la fiche au moment de l’achat fait foi. Pour VIP 1, le tarif communiqué est de 5 000 FCFA.' },
    { keys:['achat revente','revente','revendre','pack','netflix','spotify','crunchyroll','crunchy roll','iptv','vpn','apple music','apple musique'], answer:'La section « Achat et revente » présente les packs de comptes numériques et leurs prix. Les tarifs indiqués pour 10 accès sont : Apple Music famille 8 000 FCFA, Spotify famille 6 000 FCFA, Crunchyroll 5 000 FCFA, IPTV 10 000 FCFA, VPN 13 000 FCFA et Netflix 15 000 FCFA. Le stock dépend des disponibilités affichées.' },
    { keys:['code cadeau','code promo','cadeau','bonus code','utiliser code'], answer:'Pour activer un code cadeau, ouvrez « Code cadeau » et saisissez-le. Un compte doit avoir effectué au moins 3 000 FCFA de recharge pour être éligible ; chaque compte ne peut utiliser le même code qu’une seule fois, dans la limite des utilisations prévues.' },
    { keys:['bonus bienvenue','bienvenue','700','bonus inscription'], answer:'Le bonus de bienvenue prévu pour un nouveau compte est de 700 FCFA. Il est crédité à la création du compte lorsque celle-ci aboutit correctement.' },
    { keys:['parrain','inviter','lien invitation','lien promo','filleul'], answer:'Votre lien et votre code de parrainage se trouvent dans « Réseau ». Le bonus de remise lié à une invitation dépend des conditions affichées sur cette page, notamment la première recharge qualifiante du filleul.' },
    { keys:['presence','présence','pointage','100f','100 fcfa'], answer:'La présence quotidienne permet de recevoir 100 FCFA une fois par jour. Ouvrez « Présence quotidienne » et validez le pointage.' },
    { keys:['roue','tour gratuit','tour','loterie'], answer:'Les conditions de déblocage des tours sont indiquées dans « Roue de la chance ». Une recharge vérifiée d’au moins 3 000 FCFA peut débloquer les tours selon les règles de la page.' },
    { keys:['notification','notifications','message reçu','messages'], answer:'Les notifications de compte apparaissent dans la rubrique « Notifications » et dans la bulle de votre navigation. Activez les notifications de cet appareil dans « Réglages des notifications » pour recevoir une alerte navigateur lorsque l’application est ouverte ou en arrière-plan.' },
    { keys:['whatsapp','telegram','conseiller','humain','service client','assistance'], answer:'Vous pouvez contacter l’équipe via la rubrique Assistance, le groupe WhatsApp officiel ou le canal Telegram KPYX. Pour un suivi lié à votre compte, indiquez votre nom d’utilisateur et la date de l’opération, sans envoyer votre mot de passe ni un code secret.' },
    { keys:['historique','transaction','statut','en attente','reçu','recu'], answer:'Consultez « Historique des recharges », « Historique des retraits » ou « Mouvements du compte » selon l’opération. Si elle n’apparaît pas ou reste en attente, contactez l’assistance avec la référence et l’heure de l’opération.' }
  ];
  const normalize = value => String(value || '').toLocaleLowerCase('fr').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
  function answer(question) {
    const q = normalize(question); let best = null, score = 0;
    for (const item of knowledge) { const points = item.keys.reduce((n, key) => n + (q.includes(normalize(key)) ? Math.max(2, normalize(key).split(' ').length) : 0), 0); if (points > score) { best = item; score = points; } }
    return score ? best.answer : 'Je n’ai pas assez d’informations fiables pour répondre à cette question. Consultez la rubrique concernée ou choisissez « Parler à un conseiller » pour obtenir une vérification par l’équipe.';
  }
  function appendMessage(kind, label, text) {
    const box = document.querySelector('#chat-messages'); if (!box) return;
    const article = document.createElement('article'); article.className = 'chat-message ' + kind;
    const small = document.createElement('small'); small.textContent = label;
    const p = document.createElement('p'); p.textContent = text; article.append(small, p); box.append(article);
    article.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  window.KPYXAskSupport = question => { const q = String(question || '').trim(); if (!q) return; appendMessage('user', 'Vous', q); appendMessage('assistant', 'Assistant KPYX', answer(q)); };
  function decodeApplicationKey(value) { const padded = value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '='); return Uint8Array.from(atob(padded), c => c.charCodeAt(0)); }
  window.KPYXNotificationPermission = async button => {
    const db = window.kpyxSupabase;
    if (!db || !('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) { toast('Les notifications Push ne sont pas prises en charge ici. Ouvrez KPYX dans un navigateur récent.'); return; }
    button.disabled = true;
    try {
      const { data: { session } } = await db.auth.getSession();
      if (!session) { button.disabled = false; go('login'); return; }
      const permission = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
      if (permission !== 'granted') throw new Error(permission === 'denied' ? 'Autorisation bloquée dans les réglages du navigateur.' : 'Autorisation non accordée.');
      const response = await fetch('/api/push/public-key', { cache: 'no-store' });
      const config = await response.json();
      if (!response.ok || !config.publicKey) throw new Error(config.error || 'Configuration Push indisponible.');
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription() || await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: decodeApplicationKey(config.publicKey) });
      const { error } = await db.from('push_subscriptions').upsert({ user_id: session.user.id, endpoint: subscription.endpoint, subscription: subscription.toJSON(), updated_at: new Date().toISOString() }, { onConflict: 'endpoint' });
      if (error) throw error;
      button.textContent = 'Notifications Push activées ✓';
      toast('Cet appareil recevra les alertes KPYX, même lorsque l’application est fermée.');
    } catch (error) {
      button.disabled = false;
      toast(error?.message || 'Activation Push impossible. Réessayez.');
    }
  };
  window.KPYXShowSystemNotification = n => {
    if (!('Notification' in window) || Notification.permission !== 'granted' || !document.hidden) return;
    const options = { body: String(n.body || '').slice(0, 180), icon: '/assets/kpyx-192.png', badge: '/assets/kpyx-192.png', tag: 'kpyx-' + String(n.id || Date.now()), data: { url: '/messages' } };
    if (navigator.serviceWorker?.controller) navigator.serviceWorker.ready.then(reg => reg.showNotification(n.title || 'KPYX', options)).catch(() => {});
    else try { new Notification(n.title || 'KPYX', options); } catch {}
  };
  window.addEventListener('load', () => { if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {}); });
})();
