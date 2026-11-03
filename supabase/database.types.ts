export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.18"
  }
  public: {
    Tables: {
      access_inventory: {
        Row: {
          delivered_at: string | null
          id: string
          imported_at: string
          order_item_id: string | null
          product_id: string
          secret_vault_id: string
          status: string
        }
        Insert: {
          delivered_at?: string | null
          id?: string
          imported_at?: string
          order_item_id?: string | null
          product_id: string
          secret_vault_id: string
          status?: string
        }
        Update: {
          delivered_at?: string | null
          id?: string
          imported_at?: string
          order_item_id?: string | null
          product_id?: string
          secret_vault_id?: string
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "access_inventory_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: false
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "access_inventory_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "digital_products"
            referencedColumns: ["id"]
          },
        ]
      }
      digital_products: {
        Row: {
          access_count: number
          active: boolean
          category: string
          created_at: string
          id: string
          name: string
          price_xof: number
          sort_order: number
        }
        Insert: {
          access_count?: number
          active?: boolean
          category: string
          created_at?: string
          id: string
          name: string
          price_xof: number
          sort_order?: number
        }
        Update: {
          access_count?: number
          active?: boolean
          category?: string
          created_at?: string
          id?: string
          name?: string
          price_xof?: number
          sort_order?: number
        }
        Relationships: []
      }
      lottery_spins: {
        Row: {
          created_at: string
          id: string
          prize_xof: number | null
          qualifying_payment_event_id: string
          spun_at: string | null
          status: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          prize_xof?: number | null
          qualifying_payment_event_id: string
          spun_at?: string | null
          status?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          prize_xof?: number | null
          qualifying_payment_event_id?: string
          spun_at?: string | null
          status?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "lottery_spins_qualifying_payment_event_id_fkey"
            columns: ["qualifying_payment_event_id"]
            isOneToOne: true
            referencedRelation: "payment_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "lottery_spins_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      order_items: {
        Row: {
          access_count: number
          created_at: string
          id: string
          line_total_xof: number
          order_id: string
          product_id: string
          quantity: number
          unit_price_xof: number
        }
        Insert: {
          access_count: number
          created_at?: string
          id?: string
          line_total_xof: number
          order_id: string
          product_id: string
          quantity: number
          unit_price_xof: number
        }
        Update: {
          access_count?: number
          created_at?: string
          id?: string
          line_total_xof?: number
          order_id?: string
          product_id?: string
          quantity?: number
          unit_price_xof?: number
        }
        Relationships: [
          {
            foreignKeyName: "order_items_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_items_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "digital_products"
            referencedColumns: ["id"]
          },
        ]
      }
      orders: {
        Row: {
          created_at: string
          fulfilled_at: string | null
          id: string
          order_number: string
          paid_at: string | null
          payment_event_id: string | null
          promo_discount_xof: number
          referral_discount_xof: number
          status: string
          subtotal_xof: number
          total_xof: number
          user_id: string
        }
        Insert: {
          created_at?: string
          fulfilled_at?: string | null
          id?: string
          order_number: string
          paid_at?: string | null
          payment_event_id?: string | null
          promo_discount_xof?: number
          referral_discount_xof?: number
          status?: string
          subtotal_xof: number
          total_xof: number
          user_id: string
        }
        Update: {
          created_at?: string
          fulfilled_at?: string | null
          id?: string
          order_number?: string
          paid_at?: string | null
          payment_event_id?: string | null
          promo_discount_xof?: number
          referral_discount_xof?: number
          status?: string
          subtotal_xof?: number
          total_xof?: number
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "orders_payment_event_id_fkey"
            columns: ["payment_event_id"]
            isOneToOne: true
            referencedRelation: "payment_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "orders_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      pack_items: {
        Row: {
          pack_id: string
          product_id: string
          quantity: number
        }
        Insert: {
          pack_id: string
          product_id: string
          quantity?: number
        }
        Update: {
          pack_id?: string
          product_id?: string
          quantity?: number
        }
        Relationships: [
          {
            foreignKeyName: "pack_items_pack_id_fkey"
            columns: ["pack_id"]
            isOneToOne: false
            referencedRelation: "digital_products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "pack_items_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "digital_products"
            referencedColumns: ["id"]
          },
        ]
      }
      payment_events: {
        Row: {
          amount_xof: number
          confirmed_at: string | null
          created_at: string
          event_type: string
          id: string
          metadata: Json
          provider: string
          provider_event_id: string
          status: string
          user_id: string
        }
        Insert: {
          amount_xof: number
          confirmed_at?: string | null
          created_at?: string
          event_type: string
          id?: string
          metadata?: Json
          provider: string
          provider_event_id: string
          status: string
          user_id: string
        }
        Update: {
          amount_xof?: number
          confirmed_at?: string | null
          created_at?: string
          event_type?: string
          id?: string
          metadata?: Json
          provider?: string
          provider_event_id?: string
          status?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "payment_events_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          created_at: string
          display_name: string
          id: string
          phone_e164: string | null
          referral_code: string
          referred_by: string | null
          updated_at: string
        }
        Insert: {
          created_at?: string
          display_name?: string
          id: string
          phone_e164?: string | null
          referral_code: string
          referred_by?: string | null
          updated_at?: string
        }
        Update: {
          created_at?: string
          display_name?: string
          id?: string
          phone_e164?: string | null
          referral_code?: string
          referred_by?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "profiles_referred_by_fkey"
            columns: ["referred_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      referral_credits: {
        Row: {
          amount_xof: number
          created_at: string
          id: string
          invited_user_id: string
          qualifying_payment_event_id: string
          redeemed_at: string | null
          redeemed_order_id: string | null
          referrer_user_id: string
          status: string
        }
        Insert: {
          amount_xof?: number
          created_at?: string
          id?: string
          invited_user_id: string
          qualifying_payment_event_id: string
          redeemed_at?: string | null
          redeemed_order_id?: string | null
          referrer_user_id: string
          status?: string
        }
        Update: {
          amount_xof?: number
          created_at?: string
          id?: string
          invited_user_id?: string
          qualifying_payment_event_id?: string
          redeemed_at?: string | null
          redeemed_order_id?: string | null
          referrer_user_id?: string
          status?: string
        }
        Relationships: [
          {
            foreignKeyName: "referral_credits_invited_user_id_fkey"
            columns: ["invited_user_id"]
            isOneToOne: true
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "referral_credits_qualifying_payment_event_id_fkey"
            columns: ["qualifying_payment_event_id"]
            isOneToOne: true
            referencedRelation: "payment_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "referral_credits_redeemed_order_id_fkey"
            columns: ["redeemed_order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "referral_credits_referrer_user_id_fkey"
            columns: ["referrer_user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      wallet_transactions: {
        Row: {
          amount_xof: number
          created_at: string
          description: string
          direction: string
          id: string
          kind: string
          payment_event_id: string | null
          status: string
          user_id: string
        }
        Insert: {
          amount_xof: number
          created_at?: string
          description?: string
          direction: string
          id?: string
          kind: string
          payment_event_id?: string | null
          status?: string
          user_id: string
        }
        Update: {
          amount_xof?: number
          created_at?: string
          description?: string
          direction?: string
          id?: string
          kind?: string
          payment_event_id?: string | null
          status?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "wallet_transactions_payment_event_id_fkey"
            columns: ["payment_event_id"]
            isOneToOne: true
            referencedRelation: "payment_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "wallet_transactions_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      wallets: {
        Row: {
          balance_xof: number
          updated_at: string
          user_id: string
        }
        Insert: {
          balance_xof?: number
          updated_at?: string
          user_id: string
        }
        Update: {
          balance_xof?: number
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "wallets_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: true
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      is_kpyx_promo_active: { Args: { at_time?: string }; Returns: boolean }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
