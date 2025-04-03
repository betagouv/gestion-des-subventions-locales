Le 31/03/2025

# Probleme

Nous souhaitons gérer les double dotations des projets.
En effet, un projet peut être obtenir plusieurs subventions (une DETR, une DSIL...)


# Que voulons-nous ?

Nous voulons traiter ces demandes de subvention de façon distinctes.
Chacun son assiette, chacun son statut.
Aussi, depuis l'application, on peut créer, modifier ou supprimer une demande de suvention.

# Quelle solution ?

![Schéma de la modélisation](<img/Schema double dotation.png>)

Aujourd'hui, nous n'avons que les modèles `Projet`, `SimulationProjet` et `ProgrammationProjet`.
Nous souhaitons rajouter le modèle `DotationProjet` entre `Projet` et `SimulationProjet` et entre `Projet` et `ProgrammationProjet`.

Dans ce modèle, nous souhaitons y mettre que les infos spécifiques aux `dotations` (detr_avis_commission).
L'idée serait de nommer ces nouveaux champs : `{nom_dotation}_{champ_specifique}`



# Pourquoi une table unique ?

Une demande de subvention à des champs communs obligatoires et des champs spécifiques à la dotation.
On est sur un cas de poymorphisme.
La question s'est posée : quel choix pour implémenter ce polymorphisme ?

Pour le moment on n'a peu de champs spécifiques :
- l'avis de la commission DETR
- les catégories d'opération

[Cet article](https://realpython.com/modeling-polymorphism-django-python/) nous a permis d'évaluer les différentes possibilités.

Pour ceci, nous souhaitons rester sur quelque chose de simple. Une table avec des champs possiblement nuls en fonction de la dotation.
Le Sparse Model nous semble alors est une bonne option pour notre cas.