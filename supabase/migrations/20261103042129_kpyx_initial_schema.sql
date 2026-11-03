-- KPYX initial data model. Payment, fulfillment and account secrets are server-only.

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  phone_e164 text,
  display_name text not null default '',
  referral_code text not null unique,
  referred_by uuid references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profiles_no_self_referral check (referred_by is distinct from id)
);

create table if not exists public.wallets (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  balance_xof bigint not null default 0 check (balance_xof >= 0),
  updated_at timestamptz not null default now()
);

create table if not exists public.digital_products (
  id text primary key,
  name text not null,
  category text not null check (category in ('service', 'pack')),
  price_xof bigint not null check (price_xof > 0),
  access_count integer not null default 10 check (access_count > 0),
  active boolean not null default true,
  sort_order smallint not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.pack_items (
  pack_id text not null references public.digital_products(id) on delete cascade,
  product_id text not null references public.digital_products(id) on delete restrict,
  quantity integer not null default 10 check (quantity > 0),
  primary key (pack_id, product_id),
  constraint pack_item_not_self check (pack_id <> product_id)
);

create table if not exists public.payment_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  provider text not null,
  provider_event_id text not null,
  event_type text not null check (event_type in ('topup', 'order_payment', 'withdrawal')),
  amount_xof bigint not null check (amount_xof > 0),
  status text not null check (status in ('pending', 'confirmed', 'failed', 'refunded')),
  metadata jsonb not null default '{}'::jsonb,
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (provider, provider_event_id)
);

create table if not exists public.wallet_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  payment_event_id uuid unique references public.payment_events(id) on delete restrict,
  kind text not null check (kind in ('topup', 'purchase', 'refund', 'referral_credit', 'withdrawal', 'lottery_prize')),
  direction text not null check (direction in ('credit', 'debit')),
  amount_xof bigint not null check (amount_xof > 0),
  status text not null default 'confirmed' check (status in ('pending', 'confirmed', 'failed', 'reversed')),
  description text not null default '',
  created_at timestamptz not null default now()
);

create table if not exists public.orders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  order_number text not null unique,
  status text not null default 'awaiting_payment' check (status in ('awaiting_payment', 'paid', 'fulfilling', 'fulfilled', 'cancelled', 'refunded')),
  subtotal_xof bigint not null check (subtotal_xof > 0),
  promo_discount_xof bigint not null default 0 check (promo_discount_xof >= 0),
  referral_discount_xof bigint not null default 0 check (referral_discount_xof >= 0),
  total_xof bigint not null check (total_xof >= 0),
  payment_event_id uuid unique references public.payment_events(id) on delete restrict,
  paid_at timestamptz,
  fulfilled_at timestamptz,
  created_at timestamptz not null default now(),
  constraint orders_amounts_valid check (subtotal_xof - promo_discount_xof - referral_discount_xof = total_xof)
);

create table if not exists public.order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  product_id text not null references public.digital_products(id) on delete restrict,
  quantity integer not null check (quantity > 0),
  unit_price_xof bigint not null check (unit_price_xof > 0),
  access_count integer not null check (access_count > 0),
  line_total_xof bigint not null check (line_total_xof > 0),
  created_at timestamptz not null default now(),
  constraint order_item_total_valid check (quantity * unit_price_xof = line_total_xof)
);

-- The table stores only an opaque vault reference; never place account passwords here.
create table if not exists public.access_inventory (
  id uuid primary key default gen_random_uuid(),
  product_id text not null references public.digital_products(id) on delete restrict,
  secret_vault_id text not null unique,
  status text not null default 'available' check (status in ('available', 'reserved', 'delivered', 'disabled')),
  order_item_id uuid references public.order_items(id) on delete restrict,
  imported_at timestamptz not null default now(),
  delivered_at timestamptz,
  constraint inventory_delivery_state check ((status <> 'delivered') or (order_item_id is not null and delivered_at is not null))
);

create table if not exists public.referral_credits (
  id uuid primary key default gen_random_uuid(),
  referrer_user_id uuid not null references public.profiles(id) on delete restrict,
  invited_user_id uuid not null unique references public.profiles(id) on delete restrict,
  qualifying_payment_event_id uuid not null unique references public.payment_events(id) on delete restrict,
  amount_xof bigint not null default 1000 check (amount_xof = 1000),
  status text not null default 'available' check (status in ('available', 'redeemed', 'expired')),
  redeemed_order_id uuid references public.orders(id) on delete restrict,
  created_at timestamptz not null default now(),
  redeemed_at timestamptz,
  constraint referral_credit_redemption_valid check ((status <> 'redeemed') or (redeemed_order_id is not null and redeemed_at is not null))
);

create index if not exists referral_credits_available_idx
  on public.referral_credits (referrer_user_id, created_at)
  where status = 'available';

create table if not exists public.lottery_spins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete restrict,
  qualifying_payment_event_id uuid not null unique references public.payment_events(id) on delete restrict,
  status text not null default 'available' check (status in ('available', 'used', 'void')),
  prize_xof bigint check (prize_xof is null or prize_xof >= 0),
  created_at timestamptz not null default now(),
  spun_at timestamptz,
  constraint spin_result_state check ((status <> 'used') or (spun_at is not null and prize_xof is not null))
);

create index if not exists orders_user_created_idx on public.orders (user_id, created_at desc);
create index if not exists transactions_user_created_idx on public.wallet_transactions (user_id, created_at desc);
create index if not exists inventory_available_idx on public.access_inventory (product_id, imported_at) where status = 'available';

insert into public.digital_products (id, name, category, price_xof, access_count, sort_order) values
  ('apple', 'Apple Music Famille', 'service', 8000, 10, 10),
  ('spotify', 'Spotify Famille', 'service', 6000, 10, 20),
  ('crunchyroll', 'Crunchyroll', 'service', 5000, 10, 30),
  ('iptv', 'IPTV Smarters', 'service', 10000, 10, 40),
  ('vpn', 'VPN aléatoire', 'service', 13000, 10, 50),
  ('netflix', 'Netflix Ultra Quality', 'service', 15000, 10, 60),
  ('duo', 'Pack Duo', 'pack', 11000, 10, 110),
  ('triple', 'Pack Triple', 'pack', 19000, 10, 120),
  ('four', 'Pack de 4', 'pack', 29000, 10, 130),
  ('maxi', 'Maxi pack', 'pack', 57000, 10, 140)
on conflict (id) do nothing;

insert into public.pack_items (pack_id, product_id, quantity) values
  ('duo', 'spotify', 10), ('duo', 'crunchyroll', 10),
  ('triple', 'apple', 10), ('triple', 'spotify', 10), ('triple', 'crunchyroll', 10),
  ('four', 'apple', 10), ('four', 'spotify', 10), ('four', 'crunchyroll', 10), ('four', 'iptv', 10),
  ('maxi', 'apple', 10), ('maxi', 'spotify', 10), ('maxi', 'crunchyroll', 10),
  ('maxi', 'iptv', 10), ('maxi', 'vpn', 10), ('maxi', 'netflix', 10)
on conflict (pack_id, product_id) do nothing;

create or replace function public.is_kpyx_promo_active(at_time timestamptz default now())
returns boolean
language sql
stable
set search_path = ''
as $$
  select extract(hour from (at_time at time zone 'Africa/Abidjan')) >= 11
     and extract(hour from (at_time at time zone 'Africa/Abidjan')) < 16;
$$;

create or replace function public.handle_new_kpyx_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  inviter uuid;
begin
  if coalesce(new.raw_user_meta_data ->> 'referral_code', '') <> '' then
    select p.id into inviter
      from public.profiles p
     where upper(p.referral_code) = upper(new.raw_user_meta_data ->> 'referral_code')
     limit 1;
  end if;

  insert into public.profiles (id, phone_e164, display_name, referral_code, referred_by)
  values (
    new.id,
    new.phone,
    coalesce(new.raw_user_meta_data ->> 'display_name', ''),
    'KPYX-' || upper(substr(replace(new.id::text, '-', ''), 1, 8)),
    case when inviter = new.id then null else inviter end
  )
  on conflict (id) do nothing;

  insert into public.wallets (user_id) values (new.id) on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_kpyx on auth.users;
create trigger on_auth_user_created_kpyx
  after insert on auth.users
  for each row execute function public.handle_new_kpyx_user();

alter table public.profiles enable row level security;
alter table public.wallets enable row level security;
alter table public.digital_products enable row level security;
alter table public.pack_items enable row level security;
alter table public.payment_events enable row level security;
alter table public.wallet_transactions enable row level security;
alter table public.orders enable row level security;
alter table public.order_items enable row level security;
alter table public.access_inventory enable row level security;
alter table public.referral_credits enable row level security;
alter table public.lottery_spins enable row level security;

create policy "profiles_read_own" on public.profiles for select to authenticated using ((select auth.uid()) = id);
create policy "wallets_read_own" on public.wallets for select to authenticated using ((select auth.uid()) = user_id);
create policy "products_read_active" on public.digital_products for select to anon, authenticated using (active = true);
create policy "pack_items_read" on public.pack_items for select to anon, authenticated using (
  exists (select 1 from public.digital_products p where p.id = pack_id and p.active = true)
);
create policy "transactions_read_own" on public.wallet_transactions for select to authenticated using ((select auth.uid()) = user_id);
create policy "orders_read_own" on public.orders for select to authenticated using ((select auth.uid()) = user_id);
create policy "order_items_read_own" on public.order_items for select to authenticated using (
  exists (select 1 from public.orders o where o.id = order_id and o.user_id = (select auth.uid()))
);
create policy "referral_credits_read_own" on public.referral_credits for select to authenticated using ((select auth.uid()) = referrer_user_id);
create policy "lottery_spins_read_own" on public.lottery_spins for select to authenticated using ((select auth.uid()) = user_id);

-- No client policies are intentionally defined for payment_events or access_inventory.
-- Use trusted edge functions/service-role code for payment confirmation, price calculation,
-- credit redemption, inventory reservation, and delivery. Never expose the service-role key.

revoke all on public.payment_events, public.access_inventory from anon, authenticated;
revoke insert, update, delete on public.profiles, public.wallets, public.digital_products,
  public.pack_items, public.wallet_transactions, public.orders, public.order_items,
  public.referral_credits, public.lottery_spins from anon, authenticated;

grant select on public.digital_products, public.pack_items to anon, authenticated;
grant select on public.profiles, public.wallets, public.wallet_transactions, public.orders,
  public.order_items, public.referral_credits, public.lottery_spins to authenticated;
