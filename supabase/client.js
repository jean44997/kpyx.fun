// Browser client: only the publishable key belongs here. Never use a service-role key in the UI.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = "https://vxjxgehyyzwxxqbstalx.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_V4chFq87bPP13cjp9Hg4lw_mp-VT37n";

try {
  window.kpyxSupabase = createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  window.dispatchEvent(new Event("kpyx:supabase-ready"));
} catch (error) {
  window.kpyxSupabaseError = error;
  window.dispatchEvent(new Event("kpyx:supabase-ready"));
}
