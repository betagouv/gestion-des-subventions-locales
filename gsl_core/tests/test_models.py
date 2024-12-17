from django.core.exceptions import ValidationError
from django.test import TestCase

from gsl_core.models import Arrondissement, Departement, Perimetre, Region


class PerimetreTest(TestCase):
    def setUp(self):
        # Création des régions
        self.region_idf = Region.objects.create(insee_code="11", name="Île-de-France")
        self.region_normandie = Region.objects.create(insee_code="28", name="Normandie")

        # Création des départements
        self.dept_75 = Departement.objects.create(
            insee_code="75", name="Paris", region=self.region_idf
        )
        self.dept_76 = Departement.objects.create(
            insee_code="76", name="Seine-Maritime", region=self.region_normandie
        )

        # Création des arrondissements
        self.arr_paris_centre = Arrondissement.objects.create(
            insee_code="75101", name="Paris Centre", departement=self.dept_75
        )
        self.arr_le_havre = Arrondissement.objects.create(
            insee_code="762", name="Le Havre", departement=self.dept_76
        )

    def test_clean_valid_perimetre(self):
        """Test qu'un périmètre avec un département de la bonne région est valide"""
        perimetre = Perimetre(region=self.region_idf, departement=self.dept_75)
        try:
            perimetre.clean()
        except ValidationError:
            self.fail("clean() a levé une ValidationError de façon inattendue!")

    def test_clean_invalid_perimetre(self):
        """Test qu'un périmètre avec un département d'une autre région lève une erreur"""
        perimetre = Perimetre(region=self.region_idf, departement=self.dept_76)
        with self.assertRaises(ValidationError) as context:
            perimetre.clean()

        self.assertIn("departement", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["departement"][0],
            "Le département doit appartenir à la même région que le périmètre.",
        )

    def test_clean_perimetre_without_departement(self):
        """Test qu'un périmètre sans département est valide"""
        perimetre = Perimetre(region=self.region_idf, departement=None)
        try:
            perimetre.clean()
        except ValidationError:
            self.fail("clean() a levé une ValidationError de façon inattendue!")

    def test_save_invalid_perimetre(self):
        """Test que save() appelle clean() et empêche la sauvegarde d'un périmètre invalide"""
        perimetre = Perimetre(region=self.region_idf, departement=self.dept_76)
        with self.assertRaises(ValidationError):
            perimetre.save()

    def test_clean_valid_perimetre_with_arrondissement(self):
        """Test qu'un périmètre avec un arrondissement du bon département est valide"""
        perimetre = Perimetre(
            region=self.region_idf,
            departement=self.dept_75,
            arrondissement=self.arr_paris_centre,
        )
        try:
            perimetre.clean()
        except ValidationError:
            self.fail("clean() a levé une ValidationError de façon inattendue!")

    def test_clean_perimetre_with_wrong_arrondissement(self):
        """Test qu'un périmètre avec un arrondissement d'un autre département lève une erreur"""
        perimetre = Perimetre(
            region=self.region_idf,
            departement=self.dept_75,
            arrondissement=self.arr_le_havre,
        )
        with self.assertRaises(ValidationError) as context:
            perimetre.clean()

        self.assertIn("arrondissement", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["arrondissement"][0],
            "L'arrondissement sélectionné doit appartenir à son département.",
        )

    def test_clean_perimetre_with_arrondissement_without_departement(self):
        """Test qu'un périmètre avec un arrondissement mais sans département lève une erreur"""
        perimetre = Perimetre(
            region=self.region_idf,
            departement=None,
            arrondissement=self.arr_paris_centre,
        )
        with self.assertRaises(ValidationError) as context:
            perimetre.clean()

        self.assertIn("arrondissement", context.exception.message_dict)
        self.assertEqual(
            context.exception.message_dict["arrondissement"][0],
            "Un arrondissement ne peut être sélectionné sans département.",
        )
