from logging import getLogger

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms import ModelForm
from dsfr import widgets as dsfr_widgets
from dsfr.forms import DsfrBaseForm

from dn.sync.exceptions import DsServiceException
from dn.sync.models import Dotation
from dn.sync.services import DsService
from gsl.core.models import Collegue
from gsl.historique.models import ProjetAction
from gsl.simulation.models import SimulationProjet

from .constants import ProjetStatus
from .models import EnveloppeProjet, Projet, ProjetNote

logger = getLogger(__name__)


class ProjetForm(ModelForm, DsfrBaseForm):
    dotations = forms.MultipleChoiceField(
        choices=Dotation.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"form": "projet-form"}),
    )

    class Meta:
        model = Projet
        fields = []

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dotations"].initial = self.instance.dotations
        self.user = user

    def is_valid(self):
        valid = super().is_valid()
        if not self.cleaned_data.get("dotations"):
            self.add_error("dotations", "Veuillez sélectionner au moins une dotation.")
            valid = False
        return valid

    def clean_dotations(self):
        dotations = self.cleaned_data.get("dotations")
        if self.instance.all_dotations_are_notified and set(dotations) != set(
            self.instance.dotations
        ):
            raise ValidationError(
                "Les dotations d'un projet déjà notifié ne peuvent être modifiées."
            )
        return dotations

    @transaction.atomic
    def save(self, commit=True):
        instance: Projet = super().save(commit=False)
        if not commit:
            return instance

        dotations = self.cleaned_data.get("dotations")
        if dotations:
            self.update_dotation(instance, dotations, self.user)

        return instance

    @transaction.atomic
    def update_dotation(
        self, projet: Projet, dotations: list[Dotation], user: Collegue
    ):
        if len(dotations) == 0:
            logger.warning(
                "Projet must have at least one dotation", extra={"projet": projet.pk}
            )
            self.add_error("dotations", "Le projet doit avoir au moins une dotation.")
            return

        if len(dotations) > 2:
            logger.warning(
                "Projet can't have more than two dotations", extra={"projet": projet.pk}
            )
            self.add_error(
                "dotations", "Le projet ne peut avoir plus de deux dotations."
            )
            return

        new_dotations = set(dotations) - set(projet.dotations)
        dotation_to_remove = set[Dotation](projet.dotations) - set(dotations)
        dotations_updated_in_app = new_dotations or dotation_to_remove

        for dotation in new_dotations:
            enveloppe_projet = EnveloppeProjet.objects.create_for(
                projet,
                projet.root_enveloppe(dotation, projet.dossier_ds.annee_de_campagne),
            )
            SimulationProjet.objects.reset_for_enveloppe_projet(enveloppe_projet)
            ProjetAction.objects.create(
                projet=projet,
                action_type=ProjetAction.TYPE_DOTATION_ADDED,
                actor=user,
                source=ProjetAction.SOURCE_TURGOT,
                dotation=dotation,
                form_id=f"{type(self).__module__}.{type(self).__qualname__}",
            )

        enveloppe_projet_to_remove = EnveloppeProjet.objects.filter(
            projet=projet, enveloppe__dotation__in=dotation_to_remove
        )

        if enveloppe_projet_to_remove.filter(status=ProjetStatus.ACCEPTED).exists():
            dotations_to_be_checked = (
                EnveloppeProjet.objects.filter(
                    projet=projet, status=ProjetStatus.ACCEPTED
                )
                .exclude(enveloppe__dotation__in=dotation_to_remove)
                .values_list("enveloppe__dotation", flat=True)
            )

            ds_service = DsService()
            ds_service.update_ds_annotations_for_one_dotation(
                dossier=projet.dossier_ds,
                user=user,
                dotations_to_be_checked=list(dotations_to_be_checked),
            )

        for dotation in dotation_to_remove:
            ProjetAction.objects.create(
                projet=projet,
                action_type=ProjetAction.TYPE_DOTATION_REMOVED,
                actor=user,
                source=ProjetAction.SOURCE_TURGOT,
                dotation=dotation,
                form_id=f"{type(self).__module__}.{type(self).__qualname__}",
            )

        enveloppe_projet_to_remove.delete()

        if dotations_updated_in_app:
            projet.dotations_updated_in_app = True
            projet.save()


class ProjetPremiereAnneeForm(ModelForm, DsfrBaseForm):
    """Changing the year switches the projet onto that campagne (see Projet.basculer)."""

    campagne = forms.TypedChoiceField(
        label="Première année de traitement",
        help_text="Permet de corriger l'année de traitement. Les dossiers déposés "
        "après le 1er octobre sont attribués à l'année suivante par défaut.",
        coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Projet
        fields = []

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        campagne = self.instance.campagne
        self.fields["campagne"].initial = campagne
        self.fields["campagne"].choices = [
            (annee, annee)
            for annee in sorted([campagne, *self.instance.campagnes_de_bascule])
        ]

    def save(self, commit=True):
        if "campagne" in self.changed_data:
            try:
                self.instance.basculer(self.cleaned_data["campagne"], actor=self.user)
            except ValidationError as error:
                self.add_error("campagne", error)
        return self.instance


class ProjetAnnotationsForm(ModelForm, DsfrBaseForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def _annotation_key(self, field):
        return f"annotations_{field}"

    def save(self, commit=True):
        instance: Projet = super().save(commit=False)
        if not commit:
            return instance
        if not any(field in self.changed_data for field in self.fields):
            return instance

        with transaction.atomic():
            instance.save()
            for name in self.changed_data:
                if isinstance(self.fields[name], forms.BooleanField):
                    ProjetAction.objects.create(
                        projet=instance,
                        action_type=ProjetAction.TYPE_BOOLEAN_MODIFIED,
                        actor=self.user,
                        source=ProjetAction.SOURCE_TURGOT,
                        boolean_field=self.fields[name].label,
                        boolean_value=self.cleaned_data.get(name),
                        form_id=f"{type(self).__module__}.{type(self).__qualname__}",
                    )
            try:
                DsService().update_annotations(
                    dossier=instance.dossier_ds,
                    user=self.user,
                    annotations={
                        self._annotation_key(name): self.cleaned_data.get(name)
                        for name in self.fields
                    },
                )
            except DsServiceException as err:
                self.add_error(None, str(err))
                transaction.set_rollback(True)
        return instance


class ProjetBudgetVertForm(ProjetAnnotationsForm):
    is_budget_vert = forms.BooleanField(
        label="Projet concourant à la transition écologique au sens budget vert",
        required=False,
    )

    class Meta:
        model = Projet
        fields = ["is_budget_vert"]


class ProjetZonageForm(ProjetAnnotationsForm):
    is_in_qpv = forms.BooleanField(label="Projet situé en QPV", required=False)
    is_attached_to_a_crte = forms.BooleanField(
        label="Projet rattaché à un CRTE", required=False
    )
    is_frr = forms.BooleanField(label="Projet situé en FRR", required=False)
    is_acv = forms.BooleanField(
        label="Projet rattaché à un programme Action coeurs de Ville (ACV)",
        required=False,
    )
    is_pvd = forms.BooleanField(
        label="Projet rattaché à un programme Petites villes de demain (PVD)",
        required=False,
    )
    is_va = forms.BooleanField(
        label="Projet rattaché à un programme Villages d'avenir", required=False
    )
    is_autre_zonage_local = forms.BooleanField(
        label="Projet rattaché à un autre zonage local",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "data-controller": "conditional-field",
                "data-action": "change->conditional-field#toggle",
                "data-conditional-field-for": "id_autre_zonage_local",
            }
        ),
    )
    autre_zonage_local = forms.CharField(
        label="Nom du zonage local",
        required=False,
    )
    is_contrat_local = forms.BooleanField(
        label="Projet rattaché à un contrat local",
        required=False,
        widget=forms.CheckboxInput(
            attrs={
                "data-controller": "conditional-field",
                "data-action": "change->conditional-field#toggle",
                "data-conditional-field-for": "id_contrat_local",
            }
        ),
    )
    contrat_local = forms.CharField(
        label="Nom du contrat local",
        required=False,
    )

    class Meta:
        model = Projet
        fields = [
            "is_in_qpv",
            "is_attached_to_a_crte",
            "is_frr",
            "is_acv",
            "is_pvd",
            "is_va",
            "is_autre_zonage_local",
            "autre_zonage_local",
            "is_contrat_local",
            "contrat_local",
        ]

    def _annotation_key(self, field):
        overrides = {
            "is_in_qpv": "annotations_is_qpv",
            "is_attached_to_a_crte": "annotations_is_crte",
        }
        return overrides.get(field, super()._annotation_key(field))

    def clean_autre_zonage_local(self):
        is_autre_zonage_local = self.cleaned_data.get("is_autre_zonage_local")
        autre_zonage_local = self.cleaned_data.get("autre_zonage_local")
        if is_autre_zonage_local and not autre_zonage_local:
            self.add_error(
                "autre_zonage_local",
                "Ce champ est obligatoire si le projet est rattaché à un autre zonage local.",
            )
        if not is_autre_zonage_local:
            autre_zonage_local = ""
        return autre_zonage_local

    def clean_contrat_local(self):
        is_contrat_local = self.cleaned_data.get("is_contrat_local")
        contrat_local = self.cleaned_data.get("contrat_local")
        if is_contrat_local and not contrat_local:
            self.add_error(
                "contrat_local",
                "Ce champ est obligatoire si le projet est rattaché à un contrat local.",
            )
        if not is_contrat_local:
            contrat_local = ""
        return contrat_local


class EnveloppeProjetForm(ModelForm, DsfrBaseForm):
    DETR_AVIS_CHOICES = [
        (None, "En cours"),
        (True, "Oui"),
        (False, "Non"),
    ]

    detr_avis_commission = forms.ChoiceField(
        label="L'avis de la commission est-il positif ?",
        choices=DETR_AVIS_CHOICES,
        required=False,
    )

    def clean_detr_avis_commission(self):
        value = self.cleaned_data.get("detr_avis_commission")
        if value == "":
            return None
        if value == "True":
            return True
        if value == "False":
            return False
        return value

    class Meta:
        model = EnveloppeProjet
        fields = [
            "detr_avis_commission",
        ]


class FrenchDecimalField(forms.DecimalField):
    def to_python(self, value):
        if isinstance(value, str):
            value = "".join(value.split()).replace(",", ".").replace("€", "")
        return super().to_python(value)


MONTANT_INPUT_ATTRS = {
    "class": "fr-input",
    "inputmode": "numeric",
    "data-controller": "format-montant",
    "data-format-montant-target": "field",
    "data-action": "change->format-montant#format",
}


class EnveloppeProjetAssietteForm(ModelForm, DsfrBaseForm):
    assiette = FrenchDecimalField(
        label="Montant des dépenses éligibles retenues (€)",
        required=True,
        help_text=" Cette valeur est identique sur toutes les simulations de cette dotation.",
        widget=forms.TextInput(attrs=MONTANT_INPUT_ATTRS),
    )

    class Meta:
        model = EnveloppeProjet
        fields = ["assiette"]


class InlineRadioSelect(dsfr_widgets.InlineRadioSelect):
    """Inline DSFR radio buttons whose `disabled_choices` stay visible but cannot be
    picked, and which can put the focus on the checked one.

    The class name needs to be InlineRadioSelect for DsfrBaseForm to render it as
    a DSFR fieldset (it dispatches on the widget class name).
    """

    disabled_choices = ()
    focus_checked = False

    def create_option(self, name, value, label, selected, *args, **kwargs):
        option = super().create_option(name, value, label, selected, *args, **kwargs)
        if value in self.disabled_choices:
            option["attrs"]["disabled"] = True
        if self.focus_checked and selected:
            option["attrs"]["autofocus"] = True
        return option


class DotationCardForm(EnveloppeProjetForm):
    """The editable fields of an enveloppe projet, saved together from its card in
    the dotations tab: its year whatever its status; while in processing, also its
    assiette and, for a DETR one reaching the threshold, the commission avis."""

    annee = forms.TypedChoiceField(
        label="Année de traitement",
        coerce=int,
        widget=InlineRadioSelect,
    )
    assiette = FrenchDecimalField(
        label="Assiette subventionnable",
        required=True,
        help_text="Cette valeur est identique sur toutes les simulations de cette dotation.",
        widget=forms.TextInput(
            attrs={
                **MONTANT_INPUT_ATTRS,
                "data-format-montant-suffix-value": " €",
                "data-format-montant-minimum-fraction-digits-value": "0",
            }
        ),
    )

    field_order = ["annee", "detr_avis_commission", "assiette"]

    class Meta:
        model = EnveloppeProjet
        fields = ["assiette", "detr_avis_commission"]

    def __init__(self, *args, user: Collegue | None = None, **kwargs):
        self.user = user
        # Several cards share the page: keep their field ids distinct.
        kwargs.setdefault("auto_id", f"id_%s_{kwargs['instance'].pk}")
        super().__init__(*args, **kwargs)
        annee = self.fields["annee"]
        annee.initial = self.instance.enveloppe.annee
        annee.choices = [(a, a) for a in self.instance.annees_de_bascule]
        annee.widget.disabled_choices = self.instance.annees_occupees

        if self.instance.is_programmee:
            # Once programmed, only its campagne can still be corrected.
            del self.fields["assiette"]
            del self.fields["detr_avis_commission"]
            return
        self.fields["assiette"].widget.attrs["aria-describedby"] = (
            f"{self['assiette'].auto_id}-messages"
        )
        if not self.has_detr_avis_commission:
            del self.fields["detr_avis_commission"]

    @property
    def has_detr_avis_commission(self) -> bool:
        return (
            self.instance.dotation == Dotation.DETR
            and self.instance.projet.demande_montant_is_greater_than_min_montant_for_detr_commission
        )

    @property
    def annee_changed(self) -> bool:
        return "annee" in self.changed_data

    def clean_annee(self):
        annee = self.cleaned_data["annee"]
        if annee in self.instance.annees_occupees:
            raise ValidationError(
                f"Le projet a déjà une dotation {self.instance.dotation} sur la "
                f"campagne {annee}."
            )
        return annee

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit and self.annee_changed:
            instance.basculer(self.cleaned_data["annee"], actor=self.user)
        return instance


class EnveloppeProjetDeleteForm(forms.Form):
    def __init__(self, *args, instance: EnveloppeProjet, user: Collegue, **kwargs):
        self.instance = instance
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        if not self.instance.can_be_deleted:
            raise ValidationError(
                "Seule une dotation en traitement peut être supprimée, "
                "et le projet doit garder au moins une dotation."
            )
        return super().clean()

    @transaction.atomic
    def save(self):
        projet = self.instance.projet
        ProjetAction.objects.create(
            projet=projet,
            action_type=ProjetAction.TYPE_DOTATION_REMOVED,
            actor=self.user,
            source=ProjetAction.SOURCE_TURGOT,
            dotation=self.instance.dotation,
            form_id=f"{type(self).__module__}.{type(self).__qualname__}",
        )
        self.instance.delete()
        projet.dotations_updated_in_app = True
        projet.save(update_fields=["dotations_updated_in_app"])


class EnveloppeProjetRevertToProcessingForm(forms.Form):
    def __init__(self, *args, instance: EnveloppeProjet, user: Collegue, **kwargs):
        self.instance = instance
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        if not self.instance.can_be_set_back_to_processing:
            raise ValidationError(
                "Seule une dotation programmée de la campagne la plus récente du "
                "projet peut repasser en traitement."
            )
        return super().clean()

    def save(self):
        return self.instance.set_back_status_to_processing(self.user)


class EnveloppeProjetReportForm(forms.Form):
    def __init__(self, *args, instance: EnveloppeProjet, user: Collegue, **kwargs):
        self.instance = instance
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        if not self.instance.can_be_reported:
            raise ValidationError(
                "Seule une dotation refusée ou classée sans suite, et notifiée, peut "
                "être reportée sur la campagne suivante, si celle-ci est ouverte et "
                "n'a pas déjà cette dotation."
            )
        return super().clean()

    def save(self):
        return self.instance.report(self.user)


class ProjetNoteForm(ModelForm, DsfrBaseForm):
    title = forms.CharField(
        label="Titre de la note",
    )
    content = forms.CharField(
        label="Note",
        widget=forms.Textarea(attrs={"rows": 6}),
    )

    class Meta:
        model = ProjetNote
        fields = [
            "title",
            "content",
        ]


COMMENT_FIELDS = {
    "1": "comment_1",
    "2": "comment_2",
    "3": "comment_3",
}


class ProjetRevertToProcessingForm(forms.ModelForm):
    """Sends the dossier back to instruction on DN: its dotations keep their status
    but are to notify again."""

    @transaction.atomic
    def save(self, user, commit=True):
        self.instance.enveloppeprojet_set.update(notified_at=None)
        DsService().repasser_en_instruction(self.instance.dossier_ds, user)
        return self.instance

    class Meta:
        model = Projet
        fields = ()


class ProjetCommentForm(ModelForm, DsfrBaseForm):
    comment_number = forms.ChoiceField(
        choices=(
            ("1", "Commentaire 1"),
            ("2", "Commentaire 2"),
            ("3", "Commentaire 3"),
        ),
        widget=forms.HiddenInput,
    )
    value = forms.CharField(
        label="Commentaire",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Saisir le commentaire…",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        number = self.initial.get("comment_number")
        if number is not None:
            self.fields["value"].label = "Commentaire " + number
            self.fields["value"].initial = getattr(
                self.instance, COMMENT_FIELDS[number]
            )

    class Meta:
        model = Projet
        fields = []

    def save(self, commit=True):
        instance: Projet = self.instance
        field_name = COMMENT_FIELDS[self.cleaned_data["comment_number"]]
        setattr(instance, field_name, self.cleaned_data["value"])
        if commit:
            instance.save(update_fields=[field_name])
        return instance
