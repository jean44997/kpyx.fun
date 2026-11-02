from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import ContactMessage, Member, PaymentChannel, SiteSettings, WithdrawalRequest


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Adresse e-mail")
    phone = forms.CharField(label="Téléphone", max_length=32)
    referral = forms.CharField(label="Code de parrainage", max_length=20, required=False)
    share_contact_with_network = forms.BooleanField(
        label="Partager mon e-mail et mon téléphone avec les membres de mon réseau de parrainage",
        required=False,
    )

    class Meta:
        model = Member
        fields = ("first_name", "last_name", "email", "phone", "referral", "share_contact_with_network")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Mot de passe"
        self.fields["password2"].label = "Confirmer le mot de passe"
        self.fields["referral"].required = SiteSettings.get_solo().referral_code_required

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Member.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email

    def clean_referral(self):
        code = self.cleaned_data.get("referral", "").strip().upper()
        if not code:
            return None
        try:
            return Member.objects.get(referral_code__iexact=code, status=Member.Status.VALIDATED, is_active=True)
        except Member.DoesNotExist:
            raise forms.ValidationError("Ce code de parrainage est introuvable ou inactif.")

    def save(self, commit=True):
        member = super().save(commit=False)
        member.email = self.cleaned_data["email"]
        member.first_name = self.cleaned_data["first_name"].strip()
        member.last_name = self.cleaned_data["last_name"].strip()
        member.phone = self.cleaned_data["phone"].strip()
        member.referred_by = self.cleaned_data.get("referral")
        member.share_contact_with_network = self.cleaned_data.get("share_contact_with_network", False)
        member.status = Member.Status.PENDING
        if commit:
            member.save()
        return member


class PaymentSubmissionForm(forms.Form):
    channel = forms.ModelChoiceField(label="Moyen de paiement", queryset=PaymentChannel.objects.none())
    sender_phone = forms.CharField(label="Numéro utilisé pour le paiement", max_length=32)
    transaction_reference = forms.CharField(label="Référence de transaction", max_length=120)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["channel"].queryset = PaymentChannel.objects.filter(active=True)

    def clean_transaction_reference(self):
        return self.cleaned_data["transaction_reference"].strip()


class WithdrawalForm(forms.ModelForm):
    class Meta:
        model = WithdrawalRequest
        fields = ("amount", "channel", "destination")
        labels = {"amount": "Montant (XOF)", "channel": "Moyen de réception", "destination": "Numéro ou compte de réception"}
        widgets = {"amount": forms.NumberInput(attrs={"min": 1, "step": 1})}


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "subject", "message")
        labels = {"name": "Nom", "email": "E-mail", "subject": "Sujet", "message": "Votre message"}
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}
