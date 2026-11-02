from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    AuditLog, BlogPost, Commission, ContactMessage, Course, CourseModule,
    DigitalProduct, DigitalService, Enrollment, Lesson, LessonProgress, Member, Notification,
    Order, OrderItem, PaymentChannel, PaymentSubmission, SiteSettings,
    ServicePack, WalletEntry, WithdrawalRequest,
)
from .services import (
    activate_blocked_commissions, approve_withdrawal, mark_withdrawal_paid,
    refund_order, reject_withdrawal, release_matured_commissions, verify_payment,
)


admin.site.site_header = "KPYX · Administration"
admin.site.site_title = "Administration KPYX"
admin.site.index_title = "Gestion de la plateforme"


class MemberCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Member
        fields = ("email", "first_name", "last_name", "phone")


class MemberChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = Member
        fields = "__all__"


class AuditedAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AuditLog.objects.create(actor=request.user, action="admin.updated" if change else "admin.created", object_type=obj.__class__.__name__, object_id=str(obj.pk), details={"fields": list(form.changed_data)})

    def delete_model(self, request, obj):
        AuditLog.objects.create(actor=request.user, action="admin.deleted", object_type=obj.__class__.__name__, object_id=str(obj.pk))
        super().delete_model(request, obj)


@admin.register(Member)
class MemberAdmin(UserAdmin):
    form = MemberChangeForm
    add_form = MemberCreationForm
    ordering = ("email",)
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "phone", "password1", "password2")}),)
    list_display = ("email", "first_name", "last_name", "phone", "status", "referred_by", "share_contact_with_network", "date_joined", "is_staff")
    list_filter = ("status", "share_contact_with_network", "is_staff", "date_joined")
    search_fields = ("email", "first_name", "last_name", "phone", "referral_code")
    readonly_fields = ("referral_code", "last_login", "date_joined")
    fieldsets = (
        ("Compte", {"fields": ("email", "password", "first_name", "last_name", "phone", "status")}),
        ("Parrainage", {"fields": ("referral_code", "referred_by")}),
        ("Confidentialité", {"fields": ("share_contact_with_network",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )

    def save_model(self, request, obj, form, change):
        obj.is_active = obj.status not in [Member.Status.REJECTED, Member.Status.SUSPENDED]
        super().save_model(request, obj, form, change)
        AuditLog.objects.create(actor=request.user, action="admin.updated" if change else "admin.created", object_type="Member", object_id=str(obj.pk), details={"fields": list(form.changed_data)})


@admin.action(description="Vérifier les paiements sélectionnés (après contrôle du compte de réception)")
def verify_payments(modeladmin, request, queryset):
    done = 0
    for payment in queryset:
        try:
            verify_payment(payment.pk, request.user)
            done += 1
        except ValidationError as exc:
            modeladmin.message_user(request, f"{payment}: {exc}", level=messages.ERROR)
    if done:
        modeladmin.message_user(request, f"{done} paiement(s) confirmé(s), après action de l'administrateur.", level=messages.SUCCESS)


@admin.action(description="Refuser les paiements sélectionnés")
def reject_payments(modeladmin, request, queryset):
    changed = 0
    for payment in queryset.filter(status=PaymentSubmission.Status.REVIEW):
        payment.status = PaymentSubmission.Status.REJECTED
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        if payment.purpose == PaymentSubmission.Purpose.REGISTRATION:
            payment.member.status = Member.Status.REJECTED
            payment.member.is_active = False
            payment.member.save(update_fields=["status", "is_active"])
            Notification.objects.create(member=payment.member, title="Paiement non confirmé", body="Nous n'avons pas pu confirmer la réception. Contactez le support si vous pensez qu'il s'agit d'une erreur.")
        elif payment.order_id:
            payment.order.status = Order.Status.CANCELLED
            payment.order.save(update_fields=["status", "updated_at"])
        AuditLog.objects.create(actor=request.user, action="payment.rejected", object_type="PaymentSubmission", object_id=str(payment.pk), details={"reference": payment.transaction_reference})
        changed += 1
    modeladmin.message_user(request, f"{changed} paiement(s) refusé(s).", level=messages.SUCCESS)


@admin.register(PaymentSubmission)
class PaymentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "member", "purpose", "amount", "channel", "sender_phone", "transaction_reference", "status", "reviewed_by")
    list_filter = ("status", "purpose", "channel", "created_at")
    search_fields = ("member__email", "member__phone", "transaction_reference", "sender_phone", "order__number")
    readonly_fields = ("member", "order", "purpose", "channel", "amount", "sender_phone", "transaction_reference", "created_at", "reviewed_by", "reviewed_at")
    actions = (verify_payments, reject_payments)


@admin.action(description="Rembourser les commandes sélectionnées et annuler les commissions liées")
def refund_orders(modeladmin, request, queryset):
    changed = 0
    for order in queryset.filter(status=Order.Status.PAID):
        try:
            if not order.refund_reference.strip():
                modeladmin.message_user(request, f"{order.number}: ajoutez d'abord la référence du remboursement exécuté.", level=messages.ERROR)
                continue
            refund_order(order.pk, request.user, "Remboursement effectué par l'administrateur")
            changed += 1
        except ValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
    modeladmin.message_user(request, f"{changed} commande(s) marquée(s) comme remboursée(s) à partir d'une référence de versement enregistrée. Cette action ne déclenche pas le remboursement auprès du prestataire.", level=messages.SUCCESS)


@admin.register(Order)
class OrderAdmin(AuditedAdmin):
    list_display = ("number", "member", "total", "status", "created_at", "paid_at")
    list_filter = ("status", "created_at")
    search_fields = ("number", "member__email", "member__phone")
    readonly_fields = ("number", "member", "total", "currency", "created_at", "paid_at")
    actions = (refund_orders,)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "title_snapshot", "unit_price", "quantity")
    can_delete = False


@admin.register(DigitalProduct)
class DigitalProductAdmin(AuditedAdmin):
    list_display = ("title", "category", "price", "published", "featured", "updated_at")
    list_filter = ("category", "published", "featured")
    search_fields = ("title", "summary", "description")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0


class CourseModuleInline(admin.TabularInline):
    model = CourseModule
    extra = 0


@admin.register(Course)
class CourseAdmin(AuditedAdmin):
    list_display = ("title", "category", "level", "published", "product")
    list_filter = ("category", "level", "published")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (CourseModuleInline,)


@admin.register(CourseModule)
class CourseModuleAdmin(admin.ModelAdmin):
    list_display = ("title", "course", "order")
    inlines = (LessonInline,)


@admin.register(SiteSettings)
class SiteSettingsAdmin(AuditedAdmin):
    fieldsets = (
        ("Inscription", {"fields": ("registration_fee", "referral_code_required")}),
        ("Commissions — réglage et blocage", {"fields": ("commission_enabled", "economics_reviewed", "commission_base_percent", "commission_cap_per_level", "level_1_rate", "level_2_rate", "level_3_rate", "commission_delay_days")}),
        ("Contrôle", {"fields": ("updated_at",)}),
    )
    readonly_fields = ("updated_at",)
    actions = ("activate_previously_blocked",)

    @admin.action(description="Activer les commissions bloquées des ventes confirmées")
    def activate_previously_blocked(self, request, queryset):
        try:
            count = activate_blocked_commissions(request.user)
            self.message_user(request, f"{count} commission(s) passée(s) en attente après validation de la configuration.", level=messages.SUCCESS)
        except ValidationError as exc:
            self.message_user(request, str(exc), level=messages.ERROR)


@admin.action(description="Approuver les demandes sélectionnées")
def approve_withdrawals(modeladmin, request, queryset):
    count = 0
    for withdrawal in queryset:
        try:
            approve_withdrawal(withdrawal.pk, request.user)
            count += 1
        except ValidationError as exc:
            modeladmin.message_user(request, f"{withdrawal}: {exc}", level=messages.ERROR)
    modeladmin.message_user(request, f"{count} retrait(s) approuvé(s). Aucun n'est marqué payé.", level=messages.SUCCESS)


@admin.action(description="Marquer payé après versement effectif (référence obligatoire)")
def pay_withdrawals(modeladmin, request, queryset):
    count = 0
    for withdrawal in queryset:
        try:
            mark_withdrawal_paid(withdrawal.pk, request.user, withdrawal.payout_reference)
            count += 1
        except ValidationError as exc:
            modeladmin.message_user(request, f"{withdrawal}: {exc}", level=messages.ERROR)
    modeladmin.message_user(request, f"{count} retrait(s) enregistré(s) comme payé(s).", level=messages.SUCCESS)


@admin.action(description="Refuser les demandes sélectionnées et libérer leur réservation")
def reject_withdrawals(modeladmin, request, queryset):
    count = 0
    for withdrawal in queryset:
        try:
            reject_withdrawal(withdrawal.pk, request.user, "La demande a été refusée par l'administration.")
            count += 1
        except ValidationError as exc:
            modeladmin.message_user(request, f"{withdrawal}: {exc}", level=messages.ERROR)
    modeladmin.message_user(request, f"{count} demande(s) de retrait refusée(s).", level=messages.SUCCESS)


@admin.register(WithdrawalRequest)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ("member", "amount", "channel", "destination", "status", "created_at", "payout_reference")
    list_filter = ("status", "channel", "created_at")
    search_fields = ("member__email", "member__phone", "destination", "payout_reference")
    readonly_fields = ("member", "amount", "channel", "destination", "created_at", "reviewed_by", "reviewed_at")
    actions = (approve_withdrawals, pay_withdrawals, reject_withdrawals)


@admin.action(description="Libérer les commissions arrivées à échéance")
def release_commissions(modeladmin, request, queryset):
    count = release_matured_commissions(request.user)
    modeladmin.message_user(request, f"{count} commission(s) créditée(s) au portefeuille.", level=messages.SUCCESS)


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ("order", "seller", "beneficiary", "level", "basis", "rate", "amount", "status", "available_at")
    list_filter = ("status", "level", "created_at")
    search_fields = ("order__number", "seller__email", "beneficiary__email")
    readonly_fields = ("order", "seller", "beneficiary", "level", "basis", "rate", "amount", "created_at")
    actions = (release_commissions,)


@admin.register(WalletEntry)
class WalletEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "member", "kind", "amount", "description")
    list_filter = ("kind", "created_at")
    search_fields = ("member__email", "description")
    readonly_fields = ("member", "kind", "amount", "commission", "withdrawal", "description", "created_at")


@admin.register(PaymentChannel)
class PaymentChannelAdmin(AuditedAdmin):
    list_display = ("name", "receiver_label", "receiver_number", "active", "sort_order")
    list_editable = ("active", "sort_order")


@admin.register(BlogPost)
class BlogPostAdmin(AuditedAdmin):
    list_display = ("title", "published", "published_at")
    list_filter = ("published",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "email", "subject", "handled")
    list_filter = ("handled", "created_at")
    search_fields = ("name", "email", "subject", "message")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id")
    list_filter = ("action", "object_type", "created_at")
    search_fields = ("actor__email", "object_type", "object_id", "action")
    readonly_fields = ("actor", "action", "object_type", "object_id", "details", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register((Enrollment, LessonProgress, Notification))


@admin.register(DigitalService)
class DigitalServiceAdmin(AuditedAdmin):
    list_display = ("name", "category", "active", "sort_order")
    list_filter = ("category", "active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ServicePack)
class ServicePackAdmin(AuditedAdmin):
    list_display = ("title", "tier", "price_xof", "active", "sales_open", "sort_order")
    list_filter = ("tier", "active", "sales_open")
    search_fields = ("title", "summary", "services__name")
    filter_horizontal = ("services",)
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("sales_open",)
