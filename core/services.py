from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from hmac import new as hmac_new
from secrets import token_hex

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import (
    AuditLog, Commission, Course, Enrollment, Member, Notification, Order,
    PaymentSubmission, SiteSettings, WalletEntry, WithdrawalRequest,
)


def daily_pack_discount(pack_slug, on_date=None):
    """Return one stable, pseudo-random 5–15% discount per pack and local day."""
    day = on_date or timezone.localdate()
    message = f"kpyx-daily-pack-discount:{day.isoformat()}:{pack_slug}".encode("utf-8")
    digest = hmac_new(settings.SECRET_KEY.encode("utf-8"), message, sha256).digest()
    return 5 + int.from_bytes(digest[:8], "big") % 11


def discounted_pack_price(base_price, discount_percent):
    return int((Decimal(base_price) * Decimal(100 - discount_percent) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def daily_service_pack_pricing(pack, service_prices, on_date=None):
    base_price = 0
    variable_services = []
    for service in pack.services.all():
        service_price = service_prices.get(service.slug)
        if service_price is None:
            variable_services.append(service.name)
        else:
            base_price += service_price
    discount = daily_pack_discount(pack.slug, on_date=on_date)
    return {
        "base_price_xof": base_price,
        "discount_percent": discount,
        "final_price_xof": discounted_pack_price(base_price, discount) if not variable_services else None,
        "variable_services": variable_services,
        "discounted_known_services_xof": discounted_pack_price(base_price, discount),
    }


def audit(actor, action, obj, details=None):
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        details=details or {},
    )


def make_order_number():
    return f"KX-{timezone.now():%y%m%d}-{token_hex(3).upper()}"


def wallet_balance(member):
    return sum(member.wallet_entries.values_list("amount", flat=True))


def reserved_withdrawals(member):
    return sum(member.withdrawals.filter(status__in=[WithdrawalRequest.Status.REQUESTED, WithdrawalRequest.Status.APPROVED]).values_list("amount", flat=True))


@transaction.atomic
def verify_payment(submission_id, reviewer):
    payment = PaymentSubmission.objects.select_for_update().select_related("member", "order").get(pk=submission_id)
    if payment.status != PaymentSubmission.Status.REVIEW:
        raise ValidationError("Ce paiement a déjà été traité.")
    if payment.purpose == PaymentSubmission.Purpose.REGISTRATION:
        settings = SiteSettings.get_solo()
        if payment.amount != settings.registration_fee:
            raise ValidationError("Le montant annoncé ne correspond pas aux frais de validation configurés.")
        member = Member.objects.select_for_update().get(pk=payment.member_id)
        if member.status not in [Member.Status.PENDING, Member.Status.PAYMENT_REVIEW]:
            raise ValidationError("Le statut du compte ne permet pas cette validation.")
        member.status = Member.Status.VALIDATED
        member.save(update_fields=["status"])
        if not WalletEntry.objects.filter(member=member, kind=WalletEntry.Kind.BONUS).exists():
            WalletEntry.objects.create(member=member, kind=WalletEntry.Kind.BONUS, amount=500, description="Bonus de bienvenue KPYX · 500 FCFA")
        Notification.objects.create(member=member, title="Compte validé", body="Votre paiement a été confirmé. Votre compte KPYX est actif et votre bonus de bienvenue de 500 FCFA a été crédité.")
    elif payment.purpose == PaymentSubmission.Purpose.ORDER:
        order = Order.objects.select_for_update().get(pk=payment.order_id)
        if order.status != Order.Status.PAYMENT_REVIEW or payment.amount != order.total:
            raise ValidationError("La commande ou le montant ne correspond pas à ce paiement.")
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])
        for item in order.items.select_related("product__course"):
            course = Course.objects.filter(product=item.product, published=True).first()
            if course and course.published:
                Enrollment.objects.get_or_create(member=order.member, course=course, defaults={"order": order})
        create_commissions(order)
        Notification.objects.create(member=order.member, title="Commande confirmée", body=f"Le paiement de la commande {order.number} est confirmé. Vos contenus achetés sont disponibles dans votre espace.")
    payment.status = PaymentSubmission.Status.VERIFIED
    payment.reviewed_by = reviewer
    payment.reviewed_at = timezone.now()
    payment.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    audit(reviewer, "payment.verified", payment, {"purpose": payment.purpose, "amount": payment.amount, "reference": payment.transaction_reference})
    return payment


def create_commissions(order):
    """Create one auditable commission row per eligible sale and upline level."""
    settings = SiteSettings.get_solo()
    rates = [settings.level_1_rate, settings.level_2_rate, settings.level_3_rate]
    release_ready = settings.commission_enabled and settings.economics_reviewed and settings.total_commission_rate <= 100
    ancestor = order.member.referred_by
    product_subtotal = sum(item.unit_price * item.quantity for item in order.items.all())
    basis = int((Decimal(product_subtotal) * settings.commission_base_percent / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    for level, rate in enumerate(rates, start=1):
        if ancestor is None:
            break
        amount = int((Decimal(basis) * rate / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if settings.commission_cap_per_level is not None:
            amount = min(amount, settings.commission_cap_per_level)
        Commission.objects.get_or_create(
            order=order,
            level=level,
            defaults={
                "seller": order.member,
                "beneficiary": ancestor,
                "basis": basis,
                "rate": rate,
                "amount": amount,
                "status": Commission.Status.PENDING if release_ready else Commission.Status.BLOCKED,
                "available_at": timezone.now() + timedelta(days=settings.commission_delay_days) if release_ready else None,
            },
        )
        ancestor = ancestor.referred_by


@transaction.atomic
def activate_blocked_commissions(actor):
    settings = SiteSettings.get_solo()
    if not (settings.commission_enabled and settings.economics_reviewed and settings.total_commission_rate <= 100):
        raise ValidationError("Les commissions restent bloquées jusqu'à l'activation ET la validation de la simulation économique.")
    count = 0
    commissions = Commission.objects.select_for_update().filter(status=Commission.Status.BLOCKED, order__status=Order.Status.PAID)
    for commission in commissions:
        commission.status = Commission.Status.PENDING
        commission.available_at = timezone.now() + timedelta(days=settings.commission_delay_days)
        commission.save(update_fields=["status", "available_at"])
        count += 1
    audit(actor, "commission.activate_blocked", settings, {"count": count})
    return count


@transaction.atomic
def release_matured_commissions(actor=None):
    settings = SiteSettings.get_solo()
    if not (settings.commission_enabled and settings.economics_reviewed and settings.total_commission_rate <= 100):
        return 0
    now = timezone.now()
    released = 0
    rows = Commission.objects.select_for_update().filter(status=Commission.Status.PENDING, available_at__lte=now, order__status=Order.Status.PAID)
    for commission in rows:
        WalletEntry.objects.get_or_create(
            commission=commission,
            defaults={"member": commission.beneficiary, "kind": WalletEntry.Kind.COMMISSION, "amount": commission.amount, "description": f"Commission niveau {commission.level} · {commission.order.number}"},
        )
        commission.status = Commission.Status.AVAILABLE
        commission.save(update_fields=["status"])
        audit(actor, "commission.released", commission, {"amount": commission.amount})
        released += 1
    return released


@transaction.atomic
def refund_order(order_id, actor, reason=""):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAID:
        raise ValidationError("Seule une commande payée peut être remboursée.")
    if not order.refund_reference.strip():
        raise ValidationError("Saisissez la référence du remboursement réellement exécuté avant de confirmer.")
    order.status = Order.Status.REFUNDED
    order.save(update_fields=["status", "updated_at"])
    for commission in Commission.objects.select_for_update().filter(order=order).exclude(status=Commission.Status.REVERSED):
        entry = WalletEntry.objects.filter(commission=commission).first()
        if entry:
            WalletEntry.objects.create(member=commission.beneficiary, kind=WalletEntry.Kind.ADJUSTMENT, amount=-commission.amount, description=f"Annulation commission commande remboursée {order.number}")
        commission.status = Commission.Status.REVERSED
        commission.save(update_fields=["status"])
    audit(actor, "order.refunded", order, {"reason": reason, "refund_reference": order.refund_reference})
    return order


@transaction.atomic
def approve_withdrawal(withdrawal_id, reviewer):
    request = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_id)
    if request.status != WithdrawalRequest.Status.REQUESTED:
        raise ValidationError("Cette demande ne peut pas être approuvée dans son état actuel.")
    Member.objects.select_for_update().get(pk=request.member_id)
    balance = wallet_balance(request.member)
    other_reserved = reserved_withdrawals(request.member) - request.amount
    if request.amount > balance - other_reserved:
        raise ValidationError("Le solde disponible ne couvre plus cette demande.")
    request.status = WithdrawalRequest.Status.APPROVED
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    Notification.objects.create(member=request.member, title="Retrait approuvé", body="Votre demande est approuvée et attend encore le versement effectif.")
    audit(reviewer, "withdrawal.approved", request, {"amount": request.amount})
    return request


@transaction.atomic
def mark_withdrawal_paid(withdrawal_id, reviewer, payout_reference):
    request = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_id)
    if request.status != WithdrawalRequest.Status.APPROVED:
        raise ValidationError("Un retrait doit être approuvé avant d'être marqué payé.")
    if not payout_reference.strip():
        raise ValidationError("La référence de paiement effectif est obligatoire.")
    Member.objects.select_for_update().get(pk=request.member_id)
    if request.amount > wallet_balance(request.member):
        raise ValidationError("Le solde disponible ne couvre plus ce paiement.")
    request.status = WithdrawalRequest.Status.PAID
    request.payout_reference = payout_reference.strip()
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.save(update_fields=["status", "payout_reference", "reviewed_by", "reviewed_at"])
    WalletEntry.objects.create(member=request.member, kind=WalletEntry.Kind.WITHDRAWAL, amount=-request.amount, withdrawal=request, description=f"Retrait payé · réf. {request.payout_reference}")
    Notification.objects.create(member=request.member, title="Retrait payé", body=f"Le versement a été enregistré avec la référence {request.payout_reference}.")
    audit(reviewer, "withdrawal.paid", request, {"amount": request.amount, "reference": request.payout_reference})
    return request


@transaction.atomic
def reject_withdrawal(withdrawal_id, reviewer, reason=""):
    request = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_id)
    if request.status not in [WithdrawalRequest.Status.REQUESTED, WithdrawalRequest.Status.APPROVED]:
        raise ValidationError("Seule une demande non payée peut être refusée.")
    request.status = WithdrawalRequest.Status.REJECTED
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    request.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    Notification.objects.create(member=request.member, title="Demande de retrait refusée", body=reason[:280] or "Contactez le support si vous avez besoin d'informations complémentaires.")
    audit(reviewer, "withdrawal.rejected", request, {"reason": reason})
    return request
