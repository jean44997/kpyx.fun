from django.core.management.base import BaseCommand

from core.services import release_matured_commissions


class Command(BaseCommand):
    help = "Crédite au portefeuille les commissions arrivées à échéance sur des commandes confirmées."

    def handle(self, *args, **options):
        count = release_matured_commissions()
        self.stdout.write(self.style.SUCCESS(f"{count} commission(s) libérée(s)."))
