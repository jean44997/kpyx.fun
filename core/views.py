from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.views.decorators.http import require_GET, require_POST

from .forms import ContactForm, PaymentSubmissionForm, RegisterForm, WithdrawalForm
from .models import (
    AuditLog, BlogPost, Commission, Course, DigitalProduct, DigitalService, Lesson, LessonProgress,
    Member, Notification, Order, OrderItem, PaymentChannel, PaymentSubmission, SiteSettings,
    ServicePack, WithdrawalRequest,
)
from .services import daily_service_pack_pricing, make_order_number, reserved_withdrawals, wallet_balance


def home(request):
    return render(request, "core/home.html", {
        "products": DigitalProduct.objects.filter(published=True, featured=True)[:3],
        "courses": Course.objects.filter(published=True)[:3],
    })


def shop(request):
    products = DigitalProduct.objects.filter(published=True)
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    if query:
        products = products.filter(title__icontains=query) | products.filter(summary__icontains=query)
    if category:
        products = products.filter(category=category)
    return render(request, "core/shop.html", {"products": products.distinct(), "query": query, "categories": DigitalProduct.Category.choices, "selected_category": category})


def product_detail(request, slug):
    product = get_object_or_404(DigitalProduct, slug=slug, published=True)
    payment_form = PaymentSubmissionForm()
    return render(request, "core/product_detail.html", {"product": product, "payment_form": payment_form})


def cart_add(request, slug):
    if request.method != "POST":
        return redirect("product_detail", slug=slug)
    product = get_object_or_404(DigitalProduct, slug=slug, published=True)
    cart_items = request.session.get("kpyx_cart", {})
    cart_items[slug] = min(int(cart_items.get(slug, 0)) + 1, 10)
    request.session["kpyx_cart"] = cart_items
    messages.success(request, f"{product.title} a été ajouté à votre panier.")
    return redirect("cart")


def cart_data(request):
    stored = request.session.get("kpyx_cart", {})
    products = {product.slug: product for product in DigitalProduct.objects.filter(slug__in=stored.keys(), published=True)}
    rows = [(products[slug], min(max(int(quantity), 1), 10)) for slug, quantity in stored.items() if slug in products]
    valid = {product.slug: quantity for product, quantity in rows}
    if valid != stored:
        request.session["kpyx_cart"] = valid
    return rows


def cart(request):
    items = cart_data(request)
    rows = [(product, quantity, product.price * quantity) for product, quantity in items]
    total = sum(line_total for _, _, line_total in rows)
    return render(request, "core/cart.html", {
        "rows": rows, "total": total,
        "payment_form": PaymentSubmissionForm(),
        "payment_channels": PaymentChannel.objects.filter(active=True),
    })


@require_POST
def cart_update(request):
    slug = request.POST.get("slug", "")
    cart_items = request.session.get("kpyx_cart", {})
    if slug not in cart_items:
        return redirect("cart")
    if request.POST.get("action") == "remove":
        cart_items.pop(slug, None)
    else:
        try:
            quantity = int(request.POST.get("quantity", 1))
        except (ValueError, TypeError):
            quantity = 1
        if quantity <= 0:
            cart_items.pop(slug, None)
        else:
            cart_items[slug] = min(quantity, 10)
    request.session["kpyx_cart"] = cart_items
    return redirect("cart")


@login_required
@require_POST
def cart_checkout(request):
    if request.user.status != Member.Status.VALIDATED:
        messages.error(request, "Votre compte doit être validé avant un achat.")
        return redirect("dashboard")
    rows = cart_data(request)
    if not rows:
        messages.error(request, "Votre panier est vide.")
        return redirect("cart")
    form = PaymentSubmissionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vérifiez le moyen de paiement, le numéro et la référence de transaction.")
        return redirect("cart")
    total = sum(product.price * quantity for product, quantity in rows)
    try:
        with transaction.atomic():
            order = Order.objects.create(member=request.user, number=make_order_number(), total=total, status=Order.Status.PAYMENT_REVIEW)
            for product, quantity in rows:
                OrderItem.objects.create(order=order, product=product, title_snapshot=product.title, unit_price=product.price, quantity=quantity)
            PaymentSubmission.objects.create(
                member=request.user, order=order, purpose=PaymentSubmission.Purpose.ORDER,
                channel=form.cleaned_data["channel"], amount=total,
                sender_phone=form.cleaned_data["sender_phone"],
                transaction_reference=form.cleaned_data["transaction_reference"],
            )
    except IntegrityError:
        messages.error(request, "Cette référence a déjà été soumise. Vérifiez votre transaction.")
        return redirect("cart")
    request.session["kpyx_cart"] = {}
    messages.success(request, f"La commande {order.number} est en attente de vérification indépendante. Aucun contenu ne sera délivré avant confirmation.")
    return redirect("dashboard")


@login_required
@require_POST
def buy_product(request, slug):
    member = request.user
    if member.status != Member.Status.VALIDATED:
        messages.error(request, "Votre compte doit être validé avant un achat.")
        return redirect("dashboard")
    product = get_object_or_404(DigitalProduct, slug=slug, published=True)
    form = PaymentSubmissionForm(request.POST)
    if not form.is_valid():
        return render(request, "core/product_detail.html", {"product": product, "payment_form": form}, status=400)
    if not form.cleaned_data["channel"].active:
        form.add_error("channel", "Ce moyen de paiement n'est plus disponible.")
        return render(request, "core/product_detail.html", {"product": product, "payment_form": form}, status=400)
    try:
        with transaction.atomic():
            order = Order.objects.create(member=member, number=make_order_number(), total=product.price)
            OrderItem.objects.create(order=order, product=product, title_snapshot=product.title, unit_price=product.price)
            order.status = Order.Status.PAYMENT_REVIEW
            order.save(update_fields=["status", "updated_at"])
            PaymentSubmission.objects.create(
                member=member, order=order, purpose=PaymentSubmission.Purpose.ORDER,
                channel=form.cleaned_data["channel"], amount=product.price,
                sender_phone=form.cleaned_data["sender_phone"],
                transaction_reference=form.cleaned_data["transaction_reference"],
            )
    except IntegrityError:
        form.add_error("transaction_reference", "Cette référence a déjà été soumise. Vérifiez votre transaction.")
        return render(request, "core/product_detail.html", {"product": product, "payment_form": form}, status=400)
    messages.success(request, f"La commande {order.number} est en attente de vérification indépendante du paiement. Aucun fichier ne sera délivré avant confirmation.")
    return redirect("dashboard")


def academy(request):
    return render(request, "core/academy.html", {"courses": Course.objects.filter(published=True)})


def service_packs(request):
    packs = ServicePack.objects.filter(active=True).prefetch_related("services")
    individual_packs = list(packs.filter(tier=ServicePack.Tier.INDIVIDUAL))
    bundle_packs = list(packs.filter(tier=ServicePack.Tier.BUNDLE))
    premium_pack = packs.filter(tier=ServicePack.Tier.PREMIUM).first()

    service_prices = {}
    for individual_pack in individual_packs:
        for service in individual_pack.services.all():
            if individual_pack.price_xof is not None:
                service_prices[service.slug] = individual_pack.price_xof

    daily_offers = [*bundle_packs, *([premium_pack] if premium_pack else [])]
    discount_day = timezone.localdate()
    for pack in daily_offers:
        for attribute, value in daily_service_pack_pricing(pack, service_prices, on_date=discount_day).items():
            setattr(pack, attribute, value)

    local_now = timezone.localtime()
    next_midnight = (local_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return render(request, "core/service_packs.html", {
        "individual_packs": individual_packs,
        "bundle_packs": bundle_packs,
        "premium_pack": premium_pack,
        "discount_timezone": timezone.get_current_timezone_name(),
        "discount_reset_at_ms": int(next_midnight.timestamp() * 1000),
    })


@require_GET
def service_logo(request, service_id):
    service = get_object_or_404(DigitalService, pk=service_id, active=True)
    if not service.logo:
        raise Http404("Logo non fourni")
    return FileResponse(service.logo.open("rb"), as_attachment=False, filename=service.logo.name.rsplit("/", 1)[-1])


def course_detail(request, slug):
    course = get_object_or_404(Course.objects.prefetch_related("modules__lessons"), slug=slug, published=True)
    enrolled = request.user.is_authenticated and course.enrollments.filter(member=request.user).exists()
    progress_ids = set()
    if enrolled:
        progress_ids = set(LessonProgress.objects.filter(member=request.user, lesson__module__course=course).values_list("lesson_id", flat=True))
    return render(request, "core/course_detail.html", {"course": course, "enrolled": enrolled, "progress_ids": progress_ids})


@login_required
@require_POST
def complete_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related("module__course"), pk=lesson_id)
    if not lesson.module.course.enrollments.filter(member=request.user).exists():
        raise Http404
    LessonProgress.objects.get_or_create(member=request.user, lesson=lesson)
    messages.success(request, "Progression enregistrée.")
    return redirect("course_detail", slug=lesson.module.course.slug)


@login_required
def download_lesson_material(request, lesson_id):
    lesson = get_object_or_404(Lesson.objects.select_related("module__course"), pk=lesson_id)
    if not lesson.module.course.enrollments.filter(member=request.user).exists() or not lesson.material:
        raise Http404
    return FileResponse(lesson.material.open("rb"), as_attachment=True, filename=lesson.material.name.rsplit("/", 1)[-1])


def opportunities(request):
    settings = SiteSettings.get_solo()
    return render(request, "core/opportunities.html", {"level_rates": [(1, settings.level_1_rate), (2, settings.level_2_rate), (3, settings.level_3_rate)]})


def about(request):
    return render(request, "core/about.html")


def blog(request):
    return render(request, "core/blog.html", {"posts": BlogPost.objects.filter(published=True)})


def blog_detail(request, slug):
    return render(request, "core/blog_detail.html", {"post": get_object_or_404(BlogPost, slug=slug, published=True)})


def contact(request):
    selected_pack = None
    initial = {}
    pack_slug = request.GET.get("pack", "").strip()
    if pack_slug:
        selected_pack = ServicePack.objects.filter(slug=pack_slug, active=True).prefetch_related("services").first()
        if selected_pack:
            selected_pack.final_price_xof = None
            selected_pack.discount_percent = None
            selected_pack.variable_services = []
            if selected_pack.tier in (ServicePack.Tier.BUNDLE, ServicePack.Tier.PREMIUM):
                service_prices = {}
                for individual_pack in ServicePack.objects.filter(active=True, tier=ServicePack.Tier.INDIVIDUAL).prefetch_related("services"):
                    for service in individual_pack.services.all():
                        if individual_pack.price_xof is not None:
                            service_prices[service.slug] = individual_pack.price_xof
                for attribute, value in daily_service_pack_pricing(selected_pack, service_prices).items():
                    setattr(selected_pack, attribute, value)
            if selected_pack.price_xof:
                request_message = (
                    f"Bonjour, je souhaite obtenir le pack « {selected_pack.title} » "
                    f"au tarif unique de {selected_pack.price_xof} FCFA. Merci de me confirmer "
                    "sa disponibilité et ses modalités d’accès."
                )
            elif getattr(selected_pack, "final_price_xof", None) is not None:
                request_message = (
                    f"Bonjour, je souhaite obtenir le pack « {selected_pack.title} » au prix affiché "
                    f"de {selected_pack.final_price_xof} FCFA après remise du jour de {selected_pack.discount_percent} %. "
                    "Merci de me confirmer sa disponibilité et ses modalités d’accès."
                )
            elif selected_pack.tier in (ServicePack.Tier.BUNDLE, ServicePack.Tier.PREMIUM):
                request_message = (
                    f"Bonjour, je souhaite obtenir le pack « {selected_pack.title} ». "
                    f"La remise du jour affichée est de {selected_pack.discount_percent} %. "
                    "Merci de calculer le total après le choix du VPN et de me confirmer les modalités d’accès."
                )
            else:
                request_message = (
                    f"Bonjour, je souhaite obtenir le pack « {selected_pack.title} ». "
                    "Merci de me préciser son tarif et ses modalités d’accès."
                )
            initial = {
                "subject": f"Demande du pack : {selected_pack.title}",
                "message": request_message,
            }
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Votre message est enregistré. Notre équipe vous répondra dès que possible.")
        return redirect("contact")
    return render(request, "core/contact.html", {"form": form, "selected_pack": selected_pack})


def faq(request):
    faqs = [
        ("Comment activer mon compte ?", "Après votre inscription, réglez les frais affichés via un moyen configuré et transmettez la référence. Un administrateur vérifie le paiement auprès du service de paiement avant d'activer le compte."),
        ("Une capture d'écran suffit-elle pour valider un paiement ?", "Non. Une capture ou une déclaration ne constitue pas une preuve de réception. L'équipe vérifie la transaction dans le compte de réception."),
        ("Quand puis-je télécharger un achat ?", "Après confirmation effective du paiement de la commande. Les fichiers sont délivrés depuis l'espace membre."),
        ("Comment sont calculées les commissions ?", "Elles ne peuvent porter que sur des ventes réelles admissibles. Les taux et la base restent bloqués jusqu'à la validation de la simulation économique et juridique."),
        ("Les formations de trading garantissent-elles des gains ?", "Non. Le trading présente un risque de perte et aucun résultat financier n'est garanti."),
        ("Comment demander un retrait ?", "Une fois des commissions disponibles, faites une demande depuis le portefeuille. Elle reste en attente jusqu'à son approbation puis à la confirmation effective du paiement."),
    ]
    return render(request, "core/faq.html", {"faqs": faqs})


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None, initial={"referral": request.GET.get("ref", "")})
    if request.method == "POST" and form.is_valid():
        member = form.save()
        login(request, member, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Votre compte est créé. Il reste en attente jusqu'à la vérification des frais de validation.")
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard(request):
    member = request.user
    level1_query = Member.objects.filter(referred_by=member)
    level2_query = Member.objects.filter(referred_by__in=level1_query.values("pk"))
    level3_query = Member.objects.filter(referred_by__in=level2_query.values("pk"))
    level1_count = level1_query.count()
    level2_count = level2_query.count()
    level3_count = level3_query.count()
    initial_referrals = list(level1_query.annotate(children_count=Count("direct_referrals")).order_by("date_joined", "pk")[:50])
    total = wallet_balance(member)
    reserved = reserved_withdrawals(member)
    settings = SiteSettings.get_solo()
    network_members = Member.objects.filter(referred_by=member) | level2_query | level3_query
    sales = Order.objects.filter(member__in=network_members, status=Order.Status.PAID).aggregate(count=Count("id"), total=Sum("total"))
    pending_commissions = sum(member.commissions.filter(status__in=[Commission.Status.BLOCKED, Commission.Status.PENDING]).values_list("amount", flat=True))
    return render(request, "core/dashboard.html", {
        "member": member,
        "balance": total,
        "available_balance": total - reserved,
        "reserved_balance": reserved,
        "pending_commissions": pending_commissions,
        "commission_total": sum(member.commissions.exclude(status=Commission.Status.REVERSED).values_list("amount", flat=True)),
        "registration_fee": settings.registration_fee,
        "payment_channels": PaymentChannel.objects.filter(active=True),
        "referral_link": request.build_absolute_uri(f"/inscription/?ref={member.referral_code}"),
        "sales_count": sales["count"] or 0,
        "sales_total": sales["total"] or 0,
        "level1_count": level1_count, "level2_count": level2_count, "level3_count": level3_count,
        "initial_referrals": initial_referrals,
        "orders": member.orders.order_by("-created_at")[:8],
        "wallet_entries": member.wallet_entries.all()[:8],
        "notifications": member.notifications.all()[:5],
        "fee_payments": member.payment_submissions.filter(purpose=PaymentSubmission.Purpose.REGISTRATION),
        "payment_form": PaymentSubmissionForm(),
    })


@login_required
@require_POST
def update_network_sharing(request):
    member = request.user
    share = request.POST.get("share_contact_with_network") == "1"
    if member.share_contact_with_network != share:
        member.share_contact_with_network = share
        member.save(update_fields=["share_contact_with_network"])
        AuditLog.objects.create(
            actor=member,
            action="member.network_contact_sharing_changed",
            object_type="Member",
            object_id=str(member.pk),
            details={"share_contact_with_network": share},
        )
    messages.success(request, "Votre préférence de partage des coordonnées a été enregistrée.")
    return redirect("dashboard")


@login_required
@require_POST
def submit_registration_payment(request):
    form = PaymentSubmissionForm(request.POST)
    if not form.is_valid():
        for error in form.non_field_errors():
            messages.error(request, error)
        messages.error(request, "Vérifiez le moyen de paiement, le numéro et la référence de transaction.")
        return redirect("dashboard")
    try:
        with transaction.atomic():
            member = Member.objects.select_for_update().get(pk=request.user.pk)
            if member.status != Member.Status.PENDING:
                messages.error(request, "Une déclaration de paiement est déjà en cours ou aucune validation n'est attendue.")
                return redirect("dashboard")
            settings = SiteSettings.get_solo()
            PaymentSubmission.objects.create(
                member=member, purpose=PaymentSubmission.Purpose.REGISTRATION,
                channel=form.cleaned_data["channel"], amount=settings.registration_fee,
                sender_phone=form.cleaned_data["sender_phone"],
                transaction_reference=form.cleaned_data["transaction_reference"],
            )
            member.status = Member.Status.PAYMENT_REVIEW
            member.save(update_fields=["status"])
    except IntegrityError:
        messages.error(request, "Cette référence a déjà été soumise. Vérifiez votre transaction.")
        return redirect("dashboard")
    messages.success(request, "La déclaration de paiement est transmise. Votre compte reste en attente jusqu'à la vérification effective.")
    return redirect("dashboard")


@login_required
def wallet(request):
    member = request.user
    balance = wallet_balance(member)
    reserved = reserved_withdrawals(member)
    form = WithdrawalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if member.status != Member.Status.VALIDATED:
            messages.error(request, "Votre compte doit être validé pour demander un retrait.")
        elif form.cleaned_data["amount"] > balance - reserved:
            form.add_error("amount", "Le montant dépasse votre solde disponible.")
        else:
            with transaction.atomic():
                Member.objects.select_for_update().get(pk=member.pk)
                latest_balance = wallet_balance(member)
                latest_reserved = reserved_withdrawals(member)
                if form.cleaned_data["amount"] > latest_balance - latest_reserved:
                    form.add_error("amount", "Le solde disponible a changé. Vérifiez le montant et réessayez.")
                else:
                    withdrawal = form.save(commit=False)
                    withdrawal.member = member
                    withdrawal.save()
                    AuditLog.objects.create(actor=member, action="withdrawal.requested", object_type="WithdrawalRequest", object_id=str(withdrawal.pk), details={"amount": withdrawal.amount})
                    messages.success(request, "Votre demande est enregistrée et n'est pas encore payée.")
                    return redirect("wallet")
    return render(request, "core/wallet.html", {
        "balance": balance, "reserved": reserved, "available": balance - reserved,
        "entries": member.wallet_entries.all(), "withdrawals": member.withdrawals.all(), "form": form,
        "pending_commissions": member.commissions.filter(status=Commission.Status.PENDING),
        "blocked_commissions": member.commissions.filter(status=Commission.Status.BLOCKED),
    })


@login_required
def download_product(request, order_id, item_id):
    order = get_object_or_404(Order, pk=order_id, member=request.user, status=Order.Status.PAID)
    item = get_object_or_404(OrderItem.objects.select_related("product"), pk=item_id, order=order)
    if not item.product.digital_file:
        raise Http404("Fichier indisponible")
    return FileResponse(item.product.digital_file.open("rb"), as_attachment=True, filename=item.product.digital_file.name.rsplit("/", 1)[-1])


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, member=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return redirect("dashboard")


@require_GET
def api_products(request):
    rows = DigitalProduct.objects.filter(published=True).values("id", "slug", "title", "category", "summary", "price")
    return JsonResponse({"results": list(rows), "currency": "XOF"})


@login_required
@require_GET
def api_me(request):
    member = request.user
    return JsonResponse({"email": member.email, "name": member.get_full_name(), "status": member.status, "referral_code": member.referral_code, "balance_xof": wallet_balance(member) - reserved_withdrawals(member)})


@login_required
@require_GET
def api_referrals(request):
    current = [request.user]
    result = []
    for level in range(1, 4):
        current = list(Member.objects.filter(referred_by__in=current).values("id", "first_name", "last_name", "status", "date_joined")) if current else []
        result.append({"level": level, "members": current})
    return JsonResponse({"levels": result})


def _referral_depth(root_id, target_id, max_depth=100):
    """Return target's distance below root, or None when it is outside the tree."""
    if root_id == target_id:
        return 0
    row = Member.objects.filter(pk=target_id).values("referred_by_id").first()
    if row is None:
        return None
    parent_id = row["referred_by_id"]
    depth = 0
    visited = {target_id}
    while parent_id is not None and depth < max_depth:
        depth += 1
        if parent_id == root_id:
            return depth
        if parent_id in visited:
            return None
        visited.add(parent_id)
        parent_id = Member.objects.filter(pk=parent_id).values_list("referred_by_id", flat=True).first()
    return None


@login_required
@require_GET
def api_referral_tree_children(request, member_id):
    target = get_object_or_404(Member, pk=member_id)
    depth = _referral_depth(request.user.pk, target.pk, max_depth=100)
    if depth is None:
        raise Http404
    if depth >= 100:
        return JsonResponse({"members": [], "has_more": False, "limit_reached": True, "depth": depth})

    try:
        offset = max(0, int(request.GET.get("offset", "0")))
    except (TypeError, ValueError):
        return JsonResponse({"error": "offset doit être un entier positif."}, status=400)
    page_size = 50
    children_query = Member.objects.filter(referred_by=target).annotate(children_count=Count("direct_referrals")).order_by("date_joined", "pk")
    total = children_query.count()
    children = children_query[offset:offset + page_size]
    rows = []
    for child in children:
        shared = child.share_contact_with_network
        rows.append({
            "id": child.pk,
            "name": child.get_full_name().strip() or "Membre KPYX",
            "email": child.email if shared else None,
            "phone": child.phone if shared else None,
            "contacts_shared": shared,
            "status": child.get_status_display(),
            "sponsor_name": target.get_full_name().strip() or "Membre KPYX",
            "depth": depth + 1,
            "children_count": child.children_count,
        })
    next_offset = offset + len(rows)
    return JsonResponse({
        "members": rows,
        "depth": depth,
        "next_offset": next_offset,
        "has_more": next_offset < total,
        "limit_reached": depth + 1 >= 100,
    })


def admin_dashboard(request):
    now = timezone.now()
    monthly = list(Member.objects.filter(date_joined__year=now.year).annotate(month=TruncMonth("date_joined")).values("month").annotate(count=Count("id")).order_by("month"))
    members_total = Member.objects.count()
    members_active = Member.objects.filter(status=Member.Status.VALIDATED).count()
    members_pending = Member.objects.filter(status__in=[Member.Status.PENDING, Member.Status.PAYMENT_REVIEW]).count()
    sales_total = Order.objects.filter(status=Order.Status.PAID).aggregate(value=Sum("total"))["value"] or 0
    sales_count = Order.objects.filter(status=Order.Status.PAID).count()
    commissions_total = Commission.objects.exclude(status=Commission.Status.REVERSED).aggregate(value=Sum("amount"))["value"] or 0
    withdrawals_paid = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.PAID).aggregate(value=Sum("amount"))["value"] or 0
    payment_queue = PaymentSubmission.objects.filter(status=PaymentSubmission.Status.REVIEW).count()
    return render(request, "admin/dashboard.html", {
        "members_total": members_total, "members_active": members_active,
        "members_pending": members_pending, "sales_total": sales_total,
        "sales_count": sales_count, "commissions_total": commissions_total,
        "withdrawals_paid": withdrawals_paid, "monthly": monthly,
        "payment_queue": payment_queue, "current_year": now.year,
        "stats": [("Membres", members_total), ("Actifs", members_active), ("En attente", members_pending), ("Commandes payées", sales_count), ("Ventes confirmées (FCFA)", sales_total), ("Commissions enregistrées (FCFA)", commissions_total), ("Retraits payés (FCFA)", withdrawals_paid)],
    })
