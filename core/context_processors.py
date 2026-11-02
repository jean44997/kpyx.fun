import os

from .models import SiteSettings


def site_context(request):
    cart = request.session.get("kpyx_cart", {}) if hasattr(request, "session") else {}
    return {
        "site_settings": SiteSettings.get_solo(),
        "whatsapp_number": os.getenv("KPYX_WHATSAPP_NUMBER", "").strip(),
        "cart_count": sum(cart.values()) if cart else 0,
    }
