from django import forms
from django.contrib import admin, messages

from gsl_ds_proxy.models import ProxyToken

_MAX_EMAILS_IN_LABEL = 5


def _format_groupe_choice(groupe):
    instructeurs = groupe.get("instructeurs") or []
    emails = [i.get("email") for i in instructeurs if i.get("email")]
    if len(emails) > _MAX_EMAILS_IN_LABEL:
        shown = ", ".join(emails[:_MAX_EMAILS_IN_LABEL])
        emails_part = f"{shown}… (+{len(emails) - _MAX_EMAILS_IN_LABEL})"
    else:
        emails_part = ", ".join(emails)
    label = groupe.get("label") or ""
    number = groupe.get("number")
    base = f"{label} (#{number})" if number is not None else label
    return f"{base} — {emails_part}" if emails_part else base


class ProxyTokenAdminForm(forms.ModelForm):
    class Meta:
        model = ProxyToken
        fields = ("label", "demarche", "groupe_instructeur_ds_id", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        demarche = (
            getattr(self.instance, "demarche", None) if self.instance.pk else None
        )
        groupes = (
            (demarche.raw_ds_data or {}).get("groupeInstructeurs") if demarche else None
        )

        if groupes:
            choices = [("", "---------")] + [
                (g["id"], _format_groupe_choice(g)) for g in groupes if g.get("id")
            ]
            self.fields["groupe_instructeur_ds_id"] = forms.ChoiceField(
                label="Groupe instructeur",
                choices=choices,
                required=False,
            )
        else:
            self.fields["groupe_instructeur_ds_id"].disabled = True
            self.fields["groupe_instructeur_ds_id"].help_text = (
                "Sauvegardez le token après avoir choisi une démarche pour "
                "pouvoir sélectionner un groupe instructeur."
            )


@admin.register(ProxyToken)
class ProxyTokenAdmin(admin.ModelAdmin):
    form = ProxyTokenAdminForm
    list_display = (
        "label",
        "demarche",
        "is_active",
        "created_at",
        "groupe_instructeur_label",
    )
    list_filter = ("is_active", "demarche")
    readonly_fields = ("key_hash", "created_at", "updated_at")

    def groupe_instructeur_label(self, obj):
        if not obj.groupe_instructeur_ds_id or not obj.demarche_id:
            return ""
        groupes = (obj.demarche.raw_ds_data or {}).get("groupeInstructeurs") or []
        for g in groupes:
            if g.get("id") == obj.groupe_instructeur_ds_id:
                label = g.get("label") or ""
                number = g.get("number")
                return f"{label} (#{number})" if number is not None else label
        return obj.groupe_instructeur_ds_id

    groupe_instructeur_label.short_description = "Groupe instructeur"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        plaintext = getattr(obj, "_plaintext_key", None)
        if plaintext:
            messages.success(
                request,
                f"Clé API générée (à copier maintenant, elle ne sera plus affichée) : {plaintext}",
            )
