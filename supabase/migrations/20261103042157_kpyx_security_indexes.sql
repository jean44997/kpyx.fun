-- Tighten the auth trigger's callable surface and document intentional server-only tables.
revoke execute on function public.handle_new_kpyx_user() from public, anon, authenticated;

create policy "payment_events_server_only"
  on public.payment_events for all to anon, authenticated
  using (false) with check (false);

create policy "access_inventory_server_only"
  on public.access_inventory for all to anon, authenticated
  using (false) with check (false);

create index if not exists profiles_referred_by_idx on public.profiles (referred_by);
create index if not exists order_items_order_id_idx on public.order_items (order_id);
create index if not exists order_items_product_id_idx on public.order_items (product_id);
create index if not exists pack_items_product_id_idx on public.pack_items (product_id);
create index if not exists payment_events_user_id_idx on public.payment_events (user_id);
create index if not exists access_inventory_order_item_id_idx on public.access_inventory (order_item_id);
create index if not exists lottery_spins_user_id_idx on public.lottery_spins (user_id);
create index if not exists referral_credits_redeemed_order_id_idx on public.referral_credits (redeemed_order_id);
