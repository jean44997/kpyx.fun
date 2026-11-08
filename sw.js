const CACHE='kpyx-shell-v16-network-recharges';
const CORE=['/','/index.html','/support-assistant.js?v=support-push-20261106','/app.js?v=network-recharges-20261108','/style.css?v=pwa-20261105-notifications','/manifest.webmanifest','/assets/kpyx-favicon.svg','/assets/kpyx-180.png','/assets/kpyx-192.png','/assets/kpyx-512.png','/assets/whatsapp.svg','/assets/telegram.svg'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
  if(event.request.mode==='navigate'){
    event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put('/index.html',copy));return response}).catch(()=>caches.match('/index.html')));
    return;
  }
  event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request).then(response=>{if(response.ok)caches.open(CACHE).then(cache=>cache.put(event.request,response.clone()));return response})));
});

self.addEventListener('notificationclick',event=>{event.notification.close();event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{const existing=list.find(client=>new URL(client.url).origin===self.location.origin);if(existing){existing.navigate('/messages');return existing.focus()}return clients.openWindow('/messages')}))});
self.addEventListener('push',event=>{let data={};try{data=event.data?.json()||{}}catch{data={body:event.data?.text()||''}}event.waitUntil(self.registration.showNotification(data.title||'KPYX', {body:data.body||'Vous avez une nouvelle notification.',icon:'/assets/kpyx-192.png',badge:'/assets/kpyx-192.png',data:{url:'/messages'}}))});
