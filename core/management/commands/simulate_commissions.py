from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand

from core.models import SiteSettings


class Command(BaseCommand):
    help = "Affiche une simulation hypothétique des commissions configurées; ne crée aucune écriture financière."

    def add_arguments(self, parser):
        parser.add_argument("--base", type=int, default=100000, help="Base hypothétique en XOF (défaut : 100 000).")

    def handle(self, *args, **options):
        base = options["base"]
        if base <= 0:
            self.stderr.write("La base doit être strictement positive.")
            return
        settings = SiteSettings.get_solo()
        rates = [settings.level_1_rate, settings.level_2_rate, settings.level_3_rate]
        basis = int((Decimal(base) * settings.commission_base_percent / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        amounts = [int((Decimal(basis) * rate / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) for rate in rates]
        if settings.commission_cap_per_level is not None:
            amounts = [min(amount, settings.commission_cap_per_level) for amount in amounts]
        self.stdout.write(self.style.WARNING("SIMULATION HYPOTHÉTIQUE — aucun paiement, commission ou solde n'est créé."))
        for level, rate, amount in zip((1, 2, 3), rates, amounts):
            self.stdout.write(f"Niveau {level}: {rate}% = {amount:,} XOF".replace(",", " "))
        total = sum(amounts)
        self.stdout.write(f"Base retenue: {settings.commission_base_percent}% de {base:,} = {basis:,} XOF".replace(",", " "))
        if settings.commission_cap_per_level is not None:
            self.stdout.write(f"Plafond par niveau: {settings.commission_cap_per_level:,} XOF".replace(",", " "))
        self.stdout.write(self.style.SUCCESS(f"Taux cumulés définis: {settings.total_commission_rate}% · total simulé: {total:,} XOF".replace(",", " ")))
        self.stdout.write(f"Reste avant frais, impôts, support, remboursements et marge: {base-total:,} XOF".replace(",", " "))
        self.stdout.write(f"Base de calcul: {settings.commission_base_percent}% du montant des produits, avant plafonds éventuels.")
