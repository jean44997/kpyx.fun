from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from .models import (
    AuditLog, Commission, DigitalProduct, Order, OrderItem, PaymentChannel,
    PaymentSubmission, SiteSettings, WalletEntry, WithdrawalRequest,
)
from .services import approve_withdrawal, create_commissions, mark_withdrawal_paid, refund_order, verify_payment, wallet_balance

Member = get_user_model()


@override_settings(
    DEBUG=True,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class KpyxFlowTests(TestCase):
    def setUp(self):
        self.channel = PaymentChannel.objects.create(name="Wave", instructions="Réglez puis conservez la référence.", receiver_number="0700000000")
        self.admin = Member.objects.create_superuser(email="admin@kpyx.test", password="Admin-Strong-Pass-2026!", first_name="Admin", last_name="KPYX", phone="0700000001")

    def member(self, email, parent=None):
        return Member.objects.create_user(email=email, password="Member-Strong-Pass-2026!", first_name="Membre", last_name=email.split("@")[0], phone="0700000002", status=Member.Status.VALIDATED, referred_by=parent)

    def test_registration_payment_declaration_does_not_activate_member(self):
        client = Client()
        response = client.post("/inscription/", {
            "first_name": "Awa", "last_name": "Test", "email": "awa@example.test", "phone": "0701234567",
            "password1": "Awa-Secure-Password-2026!", "password2": "Awa-Secure-Password-2026!",
            "share_contact_with_network": "on",
        })
        self.assertEqual(response.status_code, 302)
        member = Member.objects.get(email="awa@example.test")
        self.assertEqual(member.status, Member.Status.PENDING)
        self.assertTrue(member.share_contact_with_network)
        response = client.post("/espace/paiement-inscription/", {
            "channel": self.channel.pk, "sender_phone": "0701234567", "transaction_reference": "WAVE-REF-001",
        })
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        payment = PaymentSubmission.objects.get(member=member)
        self.assertEqual(payment.status, PaymentSubmission.Status.REVIEW)
        self.assertEqual(member.status, Member.Status.PAYMENT_REVIEW)
        client.post("/espace/paiement-inscription/", {
            "channel": self.channel.pk, "sender_phone": "0701234567", "transaction_reference": "WAVE-REF-002",
        })
        self.assertEqual(PaymentSubmission.objects.filter(member=member).count(), 1)
        verify_payment(payment.pk, self.admin)
        member.refresh_from_db()
        self.assertEqual(member.status, Member.Status.VALIDATED)
        self.assertEqual(payment.__class__.objects.get(pk=payment.pk).status, PaymentSubmission.Status.VERIFIED)

    def test_paid_digital_order_creates_three_blocked_commission_rows_once(self):
        level3 = self.member("level3@example.test")
        level2 = self.member("level2@example.test", level3)
        level1 = self.member("level1@example.test", level2)
        buyer = self.member("buyer@example.test", level1)
        product = DigitalProduct.objects.create(title="Guide", category=DigitalProduct.Category.GUIDE, summary="Guide pratique", description="Contenu", price=100000, published=True)
        order = Order.objects.create(member=buyer, number="KX-TEST-01", status=Order.Status.PAYMENT_REVIEW, total=100000)
        OrderItem.objects.create(order=order, product=product, title_snapshot=product.title, unit_price=100000)
        payment = PaymentSubmission.objects.create(member=buyer, order=order, purpose=PaymentSubmission.Purpose.ORDER, channel=self.channel, amount=100000, sender_phone="0701234567", transaction_reference="WAVE-ORDER-1")
        verify_payment(payment.pk, self.admin)
        self.assertEqual(Commission.objects.filter(order=order).count(), 3)
        self.assertEqual(sum(Commission.objects.filter(order=order).values_list("amount", flat=True)), 78000)
        self.assertTrue(Commission.objects.filter(order=order, status=Commission.Status.BLOCKED).exists())
        with self.assertRaises(ValidationError):
            verify_payment(payment.pk, self.admin)
        self.assertEqual(Commission.objects.filter(order=order).count(), 3)

    def test_commission_base_percent_and_per_level_cap_are_applied(self):
        level3 = self.member("cap-level3@example.test")
        level2 = self.member("cap-level2@example.test", level3)
        level1 = self.member("cap-level1@example.test", level2)
        buyer = self.member("cap-buyer@example.test", level1)
        product = DigitalProduct.objects.create(title="Cap guide", category=DigitalProduct.Category.GUIDE, summary="Guide", description="Contenu", price=100000, published=True)
        order = Order.objects.create(member=buyer, number="KX-TEST-CAP", status=Order.Status.PAID, total=100000)
        OrderItem.objects.create(order=order, product=product, title_snapshot=product.title, unit_price=100000)
        settings = SiteSettings.get_solo()
        settings.commission_base_percent = 50
        settings.commission_cap_per_level = 10000
        settings.save()
        create_commissions(order)
        rows = list(Commission.objects.filter(order=order).order_by("level"))
        self.assertEqual([row.basis for row in rows], [50000] * 3)
        self.assertEqual([row.amount for row in rows], [10000, 10000, 6000])

    def test_withdrawal_is_not_paid_until_approved_and_recorded(self):
        member = self.member("wallet@example.test")
        WalletEntry.objects.create(member=member, kind=WalletEntry.Kind.ADJUSTMENT, amount=25000, description="Test credit")
        withdrawal = WithdrawalRequest.objects.create(member=member, amount=10000, channel="Wave", destination="0700000002")
        with self.assertRaises(ValidationError):
            mark_withdrawal_paid(withdrawal.pk, self.admin, "WAVE-PAYOUT-01")
        approve_withdrawal(withdrawal.pk, self.admin)
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.APPROVED)
        self.assertEqual(wallet_balance(member), 25000)
        mark_withdrawal_paid(withdrawal.pk, self.admin, "WAVE-PAYOUT-01")
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.PAID)
        self.assertEqual(wallet_balance(member), 15000)

    def test_refund_requires_reference_and_reverses_released_commission(self):
        beneficiary = self.member("sponsor@example.test")
        buyer = self.member("customer@example.test", beneficiary)
        product = DigitalProduct.objects.create(title="Workbook", category=DigitalProduct.Category.EBOOK, summary="PDF", description="Contenu", price=10000)
        order = Order.objects.create(member=buyer, number="KX-TEST-02", status=Order.Status.PAID, total=10000)
        OrderItem.objects.create(order=order, product=product, title_snapshot=product.title, unit_price=10000)
        commission = Commission.objects.create(order=order, seller=buyer, beneficiary=beneficiary, level=1, basis=10000, rate=44, amount=4400, status=Commission.Status.AVAILABLE)
        WalletEntry.objects.create(member=beneficiary, kind=WalletEntry.Kind.COMMISSION, amount=4400, commission=commission, description="Commission")
        with self.assertRaises(ValidationError):
            refund_order(order.pk, self.admin)
        order.refund_reference = "REFUND-CONFIRMED-01"
        order.save(update_fields=["refund_reference"])
        refund_order(order.pk, self.admin, "Remboursement exécuté")
        commission.refresh_from_db()
        self.assertEqual(commission.status, Commission.Status.REVERSED)
        self.assertEqual(wallet_balance(beneficiary), 0)

    def test_private_member_api_requires_authentication(self):
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 302)
        member = self.member("api@example.test")
        self.client.force_login(member)
        response = self.client.get("/api/v1/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], Member.Status.VALIDATED)

    def test_referral_tree_shares_contacts_only_with_opt_in_and_is_downline_scoped(self):
        root = self.member("tree-root@example.test")
        shared = self.member("tree-shared@example.test", root)
        shared.phone = "0701234567"
        shared.share_contact_with_network = True
        shared.save(update_fields=["phone", "share_contact_with_network"])
        private = self.member("tree-private@example.test", root)
        grandchild = self.member("tree-grandchild@example.test", shared)
        stranger = self.member("tree-stranger@example.test")

        self.client.force_login(root)
        response = self.client.get(f"/api/v1/parrainage/arbre/{root.pk}/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.json()["members"]}
        self.assertEqual(rows[shared.pk]["email"], shared.email)
        self.assertEqual(rows[shared.pk]["phone"], "0701234567")
        self.assertIsNone(rows[private.pk]["email"])
        self.assertIsNone(rows[private.pk]["phone"])

        response = self.client.get(f"/api/v1/parrainage/arbre/{shared.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["members"][0]["id"], grandchild.pk)
        self.assertEqual(response.json()["members"][0]["depth"], 2)
        self.assertEqual(self.client.get(f"/api/v1/parrainage/arbre/{stranger.pk}/").status_code, 404)

    def test_referral_tree_stops_at_level_100(self):
        root = self.member("deep-root@example.test")
        parent = root
        level_99 = None
        level_100 = None
        for level in range(1, 101):
            parent = self.member(f"deep-{level}@example.test", parent)
            if level == 99:
                level_99 = parent
            if level == 100:
                level_100 = parent

        self.client.force_login(root)
        response = self.client.get(f"/api/v1/parrainage/arbre/{level_99.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["limit_reached"])
        self.assertEqual(response.json()["members"][0]["id"], level_100.pk)
        self.assertEqual(response.json()["members"][0]["depth"], 100)
        response = self.client.get(f"/api/v1/parrainage/arbre/{level_100.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["members"], [])
        self.assertTrue(response.json()["limit_reached"])

    def test_member_can_change_contact_sharing_preference(self):
        member = self.member("sharing@example.test")
        self.client.force_login(member)
        response = self.client.post("/espace/reseau/coordonnees/", {"share_contact_with_network": "1"})
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertTrue(member.share_contact_with_network)
        self.assertTrue(AuditLog.objects.filter(actor=member, action="member.network_contact_sharing_changed").exists())
        response = self.client.post("/espace/reseau/coordonnees/", {})
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        self.assertFalse(member.share_contact_with_network)

    def test_cart_checkout_uses_server_prices_and_waits_for_review(self):
        member = self.member("cart@example.test")
        product = DigitalProduct.objects.create(title="Toolkit", category=DigitalProduct.Category.SOFTWARE, summary="Outils", description="Ressources", price=12500, published=True)
        self.client.force_login(member)
        self.client.post(f"/panier/ajouter/{product.slug}/")
        self.client.post("/panier/ajouter/" + product.slug + "/")
        response = self.client.post("/panier/commander/", {
            "channel": self.channel.pk, "sender_phone": "0700000002", "transaction_reference": "WAVE-CART-01",
        })
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(member=member)
        self.assertEqual(order.total, 25000)
        self.assertEqual(order.status, Order.Status.PAYMENT_REVIEW)
        self.assertFalse(order.commissions.exists())
        self.assertEqual(PaymentSubmission.objects.get(order=order).status, PaymentSubmission.Status.REVIEW)

    def test_public_pages_and_member_dashboard_render(self):
        for path in ["/", "/boutique/", "/academy/", "/packs/", "/opportunites/", "/a-propos/", "/blog/", "/contact/", "/faq/", "/panier/", "/inscription/", "/connexion/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
        member = self.member("page@example.test")
        self.client.force_login(member)
        self.assertEqual(self.client.get("/espace/").status_code, 200)
        product = DigitalProduct.objects.create(title="Public guide", category=DigitalProduct.Category.GUIDE, summary="Résumé", description="Description", price=2000, published=True)
        self.assertEqual(self.client.get(f"/boutique/{product.slug}/").status_code, 200)
