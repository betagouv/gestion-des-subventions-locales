# Generated by Django 5.1.1 on 2024-10-17 14:29

import django.db.models.deletion
import gsl_demarches_simplifiees.models
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Arrondissement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="AutreAide",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="CritereEligibiliteDetr",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="CritereEligibiliteDsil",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="Demarche",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("ds_id", models.CharField(unique=True, verbose_name="Identifiant DS")),
                (
                    "ds_number",
                    models.IntegerField(unique=True, verbose_name="Numéro DS"),
                ),
                ("ds_title", models.CharField(verbose_name="Titre DS")),
                (
                    "ds_state",
                    models.CharField(
                        choices=[
                            ("brouillon", "Brouillon"),
                            ("close", "Close"),
                            ("depubliee", "Dépubliée"),
                            ("publiee", "Publiée"),
                        ],
                        verbose_name="État DS",
                    ),
                ),
                (
                    "ds_date_creation",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Date de création dans DS"
                    ),
                ),
                (
                    "ds_date_fermeture",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Date de fermeture dans DS"
                    ),
                ),
            ],
            options={
                "verbose_name": "Démarche",
            },
        ),
        migrations.CreateModel(
            name="NaturePorteurProjet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ObjectifEnvironnemental",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="Profile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("ds_id", models.CharField(unique=True, verbose_name="Identifiant DS")),
                ("ds_email", models.EmailField(max_length=254, verbose_name="E-mail")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ProjetContractualisation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="ProjetZonage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("label", models.CharField(unique=True, verbose_name="Libellé")),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.CreateModel(
            name="FieldMappingForHuman",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                (
                    "label",
                    models.CharField(unique=True, verbose_name="Libellé du champ DS"),
                ),
                (
                    "django_field",
                    models.CharField(
                        blank=True,
                        choices=gsl_demarches_simplifiees.models.mapping_field_choices,
                        verbose_name="Champ correspondant dans Django",
                    ),
                ),
                (
                    "demarche",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="gsl_demarches_simplifiees.demarche",
                        verbose_name="Démarche sur laquelle ce libellé de champ a été trouvé la première fois",
                    ),
                ),
            ],
            options={
                "verbose_name": "Réconciliation de champ",
                "verbose_name_plural": "Réconciliations de champs",
            },
        ),
        migrations.CreateModel(
            name="FieldMappingForComputer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                (
                    "ds_field_id",
                    models.CharField(unique=True, verbose_name="ID du champ DS"),
                ),
                (
                    "ds_field_label",
                    models.CharField(
                        help_text="Libellé au moment où ce champ a été rencontré pour la première fois — il a pu changer depuis !",
                        verbose_name="Libellé DS",
                    ),
                ),
                ("ds_field_type", models.CharField(verbose_name="Type de champ DS")),
                (
                    "django_field",
                    models.CharField(
                        choices=gsl_demarches_simplifiees.models.mapping_field_choices,
                        verbose_name="Champ Django",
                    ),
                ),
                (
                    "demarche",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="gsl_demarches_simplifiees.demarche",
                    ),
                ),
                (
                    "field_mapping_for_human",
                    models.ForeignKey(
                        help_text="Réconciliation utilisée pour créer cette correspondance",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="gsl_demarches_simplifiees.fieldmappingforhuman",
                    ),
                ),
            ],
            options={
                "verbose_name": "Correspondance technique",
                "verbose_name_plural": "Correspondances techniques",
            },
        ),
        migrations.AddField(
            model_name="demarche",
            name="ds_instructeurs",
            field=models.ManyToManyField(to="gsl_demarches_simplifiees.profile"),
        ),
        migrations.CreateModel(
            name="Dossier",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Date de modification"
                    ),
                ),
                ("ds_id", models.CharField(verbose_name="Identifiant DS")),
                ("ds_number", models.IntegerField(verbose_name="Numéro DS")),
                (
                    "ds_state",
                    models.CharField(
                        choices=[
                            ("accepte", "Accepté"),
                            ("en_construction", "En construction"),
                            ("en_instruction", "En instruction"),
                            ("refuse", "Refusé"),
                            ("sans_suite", "Classé sans suite"),
                        ],
                        verbose_name="État DS",
                    ),
                ),
                (
                    "ds_date_depot",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Date de dépôt"
                    ),
                ),
                (
                    "ds_date_passage_en_construction",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Date de passage en construction",
                    ),
                ),
                (
                    "ds_date_passage_en_instruction",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Date de passage en instruction",
                    ),
                ),
                (
                    "ds_date_derniere_modification",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Date de dernière modification",
                    ),
                ),
                (
                    "ds_date_derniere_modification_champs",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Date de dernière modification des champs",
                    ),
                ),
                (
                    "porteur_de_projet_fonction",
                    models.CharField(
                        blank=True, verbose_name="Fonction du porteur de projet"
                    ),
                ),
                (
                    "porteur_de_projet_nom",
                    models.CharField(
                        blank=True, verbose_name="Nom du porteur de projet"
                    ),
                ),
                (
                    "porteur_de_projet_prenom",
                    models.CharField(
                        blank=True, verbose_name="Prénom du porteur de projet"
                    ),
                ),
                (
                    "maitrise_douvrage_deleguee",
                    models.BooleanField(
                        null=True,
                        verbose_name="La maîtrise d'ouvrage de l'opération sera-t-elle déléguée ?",
                    ),
                ),
                (
                    "maitrise_douvrage_siret",
                    models.CharField(
                        blank=True, verbose_name="Identification du maître d'ouvrage"
                    ),
                ),
                (
                    "projet_intitule",
                    models.CharField(blank=True, verbose_name="Intitulé du projet"),
                ),
                (
                    "projet_adresse",
                    models.TextField(
                        blank=True, verbose_name="Adresse principale du projet"
                    ),
                ),
                (
                    "projet_immo",
                    models.BooleanField(
                        null=True,
                        verbose_name="Le projet d'investissement comprend-il des acquisitions immobilières ?",
                    ),
                ),
                (
                    "projet_travaux",
                    models.BooleanField(
                        null=True,
                        verbose_name="Le projet d'investissement comprend-il des travaux ?",
                    ),
                ),
                (
                    "projet_contractualisation_autre",
                    models.CharField(
                        blank=True,
                        verbose_name="Autre contrat : précisez le contrat concerné",
                    ),
                ),
                (
                    "environnement_transition_eco",
                    models.BooleanField(
                        null=True,
                        verbose_name="Le projet concourt-il aux enjeux de la transition écologique ?",
                    ),
                ),
                (
                    "environnement_artif_sols",
                    models.BooleanField(
                        null=True,
                        verbose_name="Le projet implique-t-il une artificialisation des sols ?",
                    ),
                ),
                (
                    "date_debut",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Date de commencement de l'opération",
                    ),
                ),
                (
                    "date_achevement",
                    models.DateField(
                        null=True,
                        verbose_name="Date prévisionnelle d'achèvement de l'opération",
                    ),
                ),
                (
                    "finance_cout_total",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Coût total de l'opération (en euros HT)",
                    ),
                ),
                (
                    "finance_recettes",
                    models.BooleanField(
                        null=True,
                        verbose_name="Le projet va-t-il générer des recettes ?",
                    ),
                ),
                (
                    "demande_annee_precedente",
                    models.BooleanField(
                        null=True,
                        verbose_name="Avez-vous déjà présenté cette opération au titre de campagnes DETR/DSIL en 2023 ?",
                    ),
                ),
                (
                    "demande_numero_demande_precedente",
                    models.CharField(
                        blank=True,
                        verbose_name="Précisez le numéro du dossier déposé antérieurement",
                    ),
                ),
                (
                    "demande_dispositif_sollicite",
                    models.CharField(
                        blank=True,
                        choices=[("DETR", "DETR"), ("DSIL", "DSIL")],
                        verbose_name="Dispositif de financement sollicité",
                    ),
                ),
                (
                    "demande_montant",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=12,
                        null=True,
                        verbose_name="Montant de l'aide demandée",
                    ),
                ),
                (
                    "demande_autre_precision",
                    models.TextField(
                        blank=True,
                        verbose_name="Autre - précisez le dispositif de financement concerné",
                    ),
                ),
                (
                    "demande_autre_numero_dossier",
                    models.CharField(
                        blank=True,
                        verbose_name="Si votre dossier a déjà été déposé, précisez le numéro de dossier",
                    ),
                ),
                (
                    "demande_autre_dsil_detr",
                    models.BooleanField(
                        null=True,
                        verbose_name="Présentez-vous une autre opération au titre de la DETR/DSIL 2024 ?",
                    ),
                ),
                (
                    "demande_priorite_dsil_detr",
                    models.IntegerField(
                        null=True,
                        verbose_name="Si oui, précisez le niveau de priorité de ce dossier.",
                    ),
                ),
                (
                    "demande_autres_aides",
                    models.ManyToManyField(
                        to="gsl_demarches_simplifiees.autreaide",
                        verbose_name="En 2024, comptez-vous solliciter d'autres aides publiques pour financer cette opération  ?",
                    ),
                ),
                (
                    "demande_eligibilite_detr",
                    models.ManyToManyField(
                        to="gsl_demarches_simplifiees.critereeligibilitedetr",
                        verbose_name="Eligibilité de l'opération à la DETR",
                    ),
                ),
                (
                    "demande_eligibilite_dsil",
                    models.ManyToManyField(
                        to="gsl_demarches_simplifiees.critereeligibilitedsil",
                        verbose_name="Eligibilité de l'opération à la DSIL",
                    ),
                ),
                (
                    "ds_demarche",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="gsl_demarches_simplifiees.demarche",
                    ),
                ),
                (
                    "porteur_de_projet_arrondissement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="gsl_demarches_simplifiees.arrondissement",
                        verbose_name="Département et arrondissement du porteur de projet",
                    ),
                ),
                (
                    "porteur_de_projet_nature",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="gsl_demarches_simplifiees.natureporteurprojet",
                        verbose_name="Nature du porteur de projet",
                    ),
                ),
                (
                    "environnement_objectifs",
                    models.ManyToManyField(
                        to="gsl_demarches_simplifiees.objectifenvironnemental",
                        verbose_name="Si oui, indiquer quels sont les objectifs environnementaux impactés favorablement.",
                    ),
                ),
                (
                    "projet_contractualisation",
                    models.ManyToManyField(
                        to="gsl_demarches_simplifiees.projetcontractualisation",
                        verbose_name="Contractualisation : le projet est-il inscrit dans un ou plusieurs contrats avec l'Etat ?",
                    ),
                ),
                (
                    "projet_zonage",
                    models.ManyToManyField(
                        to="gsl_demarches_simplifiees.projetzonage",
                        verbose_name="Zonage spécifique : le projet est il situé dans l'une des zones suivantes ?",
                    ),
                ),
            ],
            options={
                "verbose_name": "Dossier",
            },
        ),
    ]
