import secrets
import string

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def referral_code():
    alphabet = string.ascii_uppercase + string.digits
    return "KX" + "".join(secrets.choice(alphabet) for _ in range(8))


class MemberManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Une adresse e-mail est nécessaire.")
        email = self.normalize_email(email).lower()
        extra_fields.setdefault("phone", "")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True or extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superutilisateur doit avoir les deux permissions activées.")
        return self._create_user(email, password, **extra_fields)


class Member(AbstractUser):
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        PAYMENT_REVIEW = "payment_review", "Paiement à vérifier"
        VALIDATED = "validated", "Validé"
        REJECTED = "rejected", "Refusé"
        SUSPENDED = "suspended", "Suspendu"

    username = None
    objects = MemberManager()
    email = models.EmailField(unique=True)
    phone = models.CharField("Téléphone", max_length=32)
    referral_code = models.CharField("Code de parrainage", max_length=12, unique=True, default=referral_code)
    referred_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="direct_referrals")
    share_contact_with_network = models.BooleanField("Partager mes coordonnées avec mon réseau", default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name", "phone"]

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def clean(self):
        super().clean()
        parent = self.referred_by
        visited = set()
        while parent is not None:
            if self.pk and parent.pk == self.pk:
                from django.core.exceptions import ValidationError
                raise ValidationError({"referred_by": "Un membre ne peut pas être parrainé par lui-même ni par un membre de son propre réseau."})
            if parent.pk in visited:
                break
            visited.add(parent.pk)
            parent = parent.referred_by


class DigitalService(models.Model):
    class Category(models.TextChoices):
        MUSIC = "music", "Musique"
        ANIME = "anime", "Anime"
        VIDEO = "video", "Films et séries"
        IPTV = "iptv", "IPTV"
        VPN = "vpn", "VPN"

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    category = models.CharField(max_length=12, choices=Category.choices)
    description = models.CharField(max_length=240, blank=True)
    compatibility = models.CharField(max_length=240, blank=True)
    logo = models.ImageField(upload_to="service-logos/", blank=True, help_text="Logo fourni par KPYX, image raster PNG, JPG ou WebP.")
    active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class ServicePack(models.Model):
    class Tier(models.TextChoices):
        INDIVIDUAL = "individual", "Service individuel"
        BUNDLE = "bundle", "Pack combiné"
        PREMIUM = "premium", "Premium"

    title = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    tier = models.CharField(max_length=12, choices=Tier.choices)
    summary = models.CharField(max_length=280)
    services = models.ManyToManyField(DigitalService, related_name="packs")
    price_xof = models.PositiveIntegerField("Prix ponctuel (XOF)", null=True, blank=True, validators=[MinValueValidator(1)])
    active = models.BooleanField(default=True)
    sales_open = models.BooleanField("Vente autorisée", default=False, help_text="Laisser décoché tant que tarif, logos, droits de revente et mode de délivrance ne sont pas validés.")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["tier", "sort_order", "title"]

    def __str__(self):
        return self.title


class SiteSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    registration_fee = models.PositiveIntegerField("Frais d'activation (XOF)", default=5000)
    referral_code_required = models.BooleanField("Code de parrainage obligatoire", default=False)
    commission_enabled = models.BooleanField("Commissions activées", default=False)
    economics_reviewed = models.BooleanField("Simulation et validation juridique/financière effectuées", default=False)
    commission_base_percent = models.DecimalField("Part de la base produit retenue (%)", max_digits=5, decimal_places=2, default=100, validators=[MinValueValidator(0), MaxValueValidator(100)])
    commission_cap_per_level = models.PositiveIntegerField("Plafond par niveau et commande (XOF)", null=True, blank=True, validators=[MinValueValidator(1)])
    level_1_rate = models.DecimalField(max_digits=5, decimal_places=2, default=44, validators=[MinValueValidator(0), MaxValueValidator(100)])
    level_2_rate = models.DecimalField(max_digits=5, decimal_places=2, default=22, validators=[MinValueValidator(0), MaxValueValidator(100)])
    level_3_rate = models.DecimalField(max_digits=5, decimal_places=2, default=12, validators=[MinValueValidator(0), MaxValueValidator(100)])
    commission_delay_days = models.PositiveSmallIntegerField("Délai avant disponibilité (jours)", default=14)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def total_commission_rate(self):
        return self.level_1_rate + self.level_2_rate + self.level_3_rate

    def clean(self):
        super().clean()
        if self.total_commission_rate > 100:
            from django.core.exceptions import ValidationError
            raise ValidationError({"level_3_rate": "Le total des taux ne peut pas dépasser 100 % de la base."})

    def __str__(self):
        return "Paramètres KPYX"


class PaymentChannel(models.Model):
    name = models.CharField("Moyen de paiement", max_length=80)
    instructions = models.TextField("Instructions affichées au client")
    receiver_label = models.CharField("Bénéficiaire", max_length=120, blank=True)
    receiver_number = models.CharField("Numéro de réception", max_length=40, blank=True)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class DigitalProduct(models.Model):
    class Category(models.TextChoices):
        TRADING = "trading", "Formation trading"
        ECOMMERCE = "ecommerce", "Formation e-commerce"
        EBOOK = "ebook", "E-book"
        GUIDE = "guide", "Guide numérique"
        DOCUMENT = "document", "Document PDF"
        SOFTWARE = "software", "Logiciel et ressource"

    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    summary = models.CharField(max_length=280)
    description = models.TextField()
    price = models.PositiveIntegerField("Prix (XOF)", validators=[MinValueValidator(1)])
    compare_at_price = models.PositiveIntegerField("Prix barré (XOF)", null=True, blank=True)
    cover = models.ImageField(upload_to="covers/", blank=True)
    digital_file = models.FileField(upload_to="products/", blank=True, help_text="Stocké en privé; l'accès est contrôlé après achat.")
    published = models.BooleanField(default=False)
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Course(models.Model):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    category = models.CharField(max_length=20, choices=DigitalProduct.Category.choices)
    summary = models.CharField(max_length=280)
    description = models.TextField()
    level = models.CharField(max_length=80, default="Débutant")
    published = models.BooleanField(default=False)
    product = models.OneToOneField(DigitalProduct, null=True, blank=True, on_delete=models.SET_NULL, related_name="course")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class CourseModule(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=180)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class Lesson(models.Model):
    module = models.ForeignKey(CourseModule, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=180)
    summary = models.TextField(blank=True)
    video_url = models.URLField(blank=True)
    material = models.FileField(upload_to="lessons/", blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class Enrollment(models.Model):
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="enrollments")
    order = models.ForeignKey("Order", on_delete=models.PROTECT, related_name="enrollments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["member", "course"], name="unique_course_enrollment")]


class LessonProgress(models.Model):
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress_records")
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["member", "lesson"], name="unique_member_lesson_progress")]


class Order(models.Model):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment", "En attente de paiement"
        PAYMENT_REVIEW = "payment_review", "Paiement à vérifier"
        PAID = "paid", "Payée"
        CANCELLED = "cancelled", "Annulée"
        REFUNDED = "refunded", "Remboursée"

    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    number = models.CharField(max_length=24, unique=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.AWAITING_PAYMENT)
    total = models.PositiveIntegerField("Total (XOF)")
    currency = models.CharField(max_length=3, default="XOF")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refund_reference = models.CharField(max_length=120, blank=True, help_text="Référence confirmant le remboursement effectif auprès du moyen de paiement.")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(DigitalProduct, on_delete=models.PROTECT, related_name="order_items")
    title_snapshot = models.CharField(max_length=180)
    unit_price = models.PositiveIntegerField("Prix unitaire (XOF)")
    quantity = models.PositiveSmallIntegerField(default=1)


class PaymentSubmission(models.Model):
    class Purpose(models.TextChoices):
        REGISTRATION = "registration", "Frais de validation"
        ORDER = "order", "Commande"

    class Status(models.TextChoices):
        REVIEW = "review", "À vérifier"
        VERIFIED = "verified", "Vérifié"
        REJECTED = "rejected", "Refusé"

    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payment_submissions")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.PROTECT, related_name="payment_submissions")
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    channel = models.ForeignKey(PaymentChannel, on_delete=models.PROTECT)
    amount = models.PositiveIntegerField("Montant annoncé (XOF)")
    sender_phone = models.CharField(max_length=32)
    transaction_reference = models.CharField(max_length=120)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REVIEW)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_payments")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=280, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["channel", "transaction_reference"], name="unique_channel_payment_reference")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_purpose_display()} · {self.transaction_reference}"


class Commission(models.Model):
    class Status(models.TextChoices):
        BLOCKED = "blocked", "Bloquée — validation économique requise"
        PENDING = "pending", "En attente"
        AVAILABLE = "available", "Disponible"
        REVERSED = "reversed", "Annulée"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="commissions")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales_attributed")
    beneficiary = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="commissions")
    level = models.PositiveSmallIntegerField()
    basis = models.PositiveIntegerField("Base de calcul (XOF)")
    rate = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.PositiveIntegerField("Commission (XOF)")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.BLOCKED)
    available_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["order", "level"], name="unique_order_commission_level")]
        ordering = ["-created_at"]


class WalletEntry(models.Model):
    class Kind(models.TextChoices):
        BONUS = "bonus", "Bonus de bienvenue"
        COMMISSION = "commission", "Commission libérée"
        WITHDRAWAL = "withdrawal", "Retrait"
        ADJUSTMENT = "adjustment", "Ajustement administrateur"

    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wallet_entries")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.IntegerField("Montant signé (XOF)")
    commission = models.OneToOneField(Commission, null=True, blank=True, on_delete=models.PROTECT, related_name="wallet_entry")
    withdrawal = models.OneToOneField("WithdrawalRequest", null=True, blank=True, on_delete=models.PROTECT, related_name="wallet_entry")
    description = models.CharField(max_length=240)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Demandé"
        APPROVED = "approved", "Approuvé — paiement à effectuer"
        PAID = "paid", "Payé"
        REJECTED = "rejected", "Refusé"

    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="withdrawals")
    amount = models.PositiveIntegerField("Montant (XOF)", validators=[MinValueValidator(1)])
    channel = models.CharField(max_length=40)
    destination = models.CharField(max_length=80)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    payout_reference = models.CharField(max_length=120, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_withdrawals")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BlogPost(models.Model):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    excerpt = models.CharField(max_length=280)
    body = models.TextField()
    published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-published_at", "-id"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        if self.published and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=180)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)


class Notification(models.Model):
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=280)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events")
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
