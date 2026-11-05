-- Tag notifications created from the Telegram admin bot so they can be
-- removed without touching payment, withdrawal, or other account alerts.
alter table public.notifications
  add column if not exists admin_batch_id uuid;

create index if not exists notifications_admin_batch_idx
  on public.notifications(admin_batch_id)
  where admin_batch_id is not null;
