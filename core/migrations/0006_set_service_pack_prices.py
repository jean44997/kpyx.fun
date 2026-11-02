from django.db import migrations


def set_pack_prices(apps, schema_editor):
    ServicePack = apps.get_model("core", "ServicePack")
    database = schema_editor.connection.alias
    offers = {
        "spotify": {"price_xof": 6500},
        "crunchyroll": {"price_xof": 8000},
        "apple-music": {"price_xof": 3000},
        "netflix": {
            "title": "Netflix · 20 accès",
            "summary": "20 accès inclus dans cette offre Netflix.",
            "price_xof": 10000,
        },
        "iptv-multi-ecran": {
            "title": "IPTV multi-écran · 3 comptes",
            "summary": "3 comptes inclus. Téléviseur, PC, téléphone Android et Apple selon l’offre du fournisseur.",
            "price_xof": 5000,
        },
        "vpn": {"price_xof": None},
    }
    for slug, values in offers.items():
        ServicePack.objects.using(database).filter(slug=slug).update(**values)


def clear_pack_prices(apps, schema_editor):
    ServicePack = apps.get_model("core", "ServicePack")
    database = schema_editor.connection.alias
    previous = {
        "spotify": ("Spotify", "Le service Spotify seul."),
        "crunchyroll": ("Crunchyroll", "Le service Crunchyroll seul."),
        "apple-music": ("Apple Music", "Le service Apple Music seul."),
        "netflix": ("Netflix", "Le service Netflix seul."),
        "iptv-multi-ecran": ("IPTV multi-écran", "Téléviseur, PC, téléphone Android et Apple, selon l’offre autorisée du fournisseur."),
        "vpn": ("VPN", "Le service VPN seul; fournisseur et compatibilités à confirmer."),
    }
    for slug, (title, summary) in previous.items():
        ServicePack.objects.using(database).filter(slug=slug).update(title=title, summary=summary, price_xof=None)


class Migration(migrations.Migration):
    dependencies = [("core", "0005_alter_digitalservice_logo")]

    operations = [
        migrations.RunPython(set_pack_prices, clear_pack_prices),
        migrations.RemoveField(model_name="servicepack", name="billing_interval_days"),
    ]
