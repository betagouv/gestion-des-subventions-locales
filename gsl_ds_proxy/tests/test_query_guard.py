from graphql import parse
from graphql.language.ast import OperationDefinitionNode

from gsl_ds_proxy.query_guard import validate_demarche_selections


def _validate(query, operation_name=None):
    doc = parse(query)
    operations = [d for d in doc.definitions if isinstance(d, OperationDefinitionNode)]
    if operation_name:
        operation = next(
            o for o in operations if o.name and o.name.value == operation_name
        )
    else:
        operation = operations[0]
    return validate_demarche_selections(doc, operation)


def test_top_level_demarche_with_allowed_field_returns_none():
    assert _validate("query getDemarche { demarche { number } }") is None


def test_top_level_demarche_with_all_allowed_fields_returns_none():
    query = (
        "query getDemarche { demarche { "
        "number title state dateCreation dateFermeture "
        "activeRevision { id } "
        "dossiers { nodes { number } } "
        "} }"
    )
    assert _validate(query) is None


def test_top_level_demarche_with_groupeInstructeurs_rejected():
    query = "query getDemarche { demarche { groupeInstructeurs { id } } }"
    assert _validate(query) == "groupeInstructeurs"


def test_nested_dossier_demarche_with_groupeInstructeurs_rejected():
    query = "query getDossier { dossier { demarche { groupeInstructeurs { id } } } }"
    assert _validate(query) == "groupeInstructeurs"


def test_dossiers_subselection_in_demarche_is_out_of_scope():
    query = (
        "query getDemarche { demarche { dossiers { nodes "
        "{ number groupeInstructeur { instructeurs { id } } } } } }"
    )
    assert _validate(query) is None


def test_inline_fragment_with_forbidden_field_rejected():
    query = "query getDemarche { demarche { ... on Demarche { revisions { id } } } }"
    assert _validate(query) == "revisions"


def test_inline_fragment_with_allowed_field_accepted():
    query = "query getDemarche { demarche { ... on Demarche { number title } } }"
    assert _validate(query) is None


def test_fragment_spread_with_forbidden_field_rejected():
    query = (
        "query getDemarche { demarche { ...D } } "
        "fragment D on Demarche { service { nom } }"
    )
    assert _validate(query) == "service"


def test_fragment_spread_with_allowed_field_accepted():
    query = (
        "query getDemarche { demarche { ...D } } "
        "fragment D on Demarche { number title }"
    )
    assert _validate(query) is None


def test_aliased_forbidden_field_rejected():
    query = "query getDemarche { demarche { x: groupeInstructeurs { id } } }"
    assert _validate(query) == "groupeInstructeurs"


def test_typename_inside_demarche_allowed():
    query = "query getDemarche { demarche { __typename number } }"
    assert _validate(query) is None


def test_getDossier_without_demarche_selection_passes_guard():
    query = "query getDossier { dossier { number } }"
    assert _validate(query) is None


def test_demarche_inside_dossiers_nodes_caught():
    query = (
        "query getDemarche { demarche { dossiers { nodes "
        "{ demarche { groupeInstructeurs { id } } } } } }"
    )
    assert _validate(query) == "groupeInstructeurs"


def test_pending_deleted_dossiers_allowed():
    query = (
        "query getDemarche { demarche { pendingDeletedDossiers { nodes { number } } } }"
    )
    assert _validate(query) is None


def test_deleted_dossiers_allowed():
    query = "query getDemarche { demarche { deletedDossiers { nodes { number } } } }"
    assert _validate(query) is None


def test_self_referencing_fragment_does_not_loop():
    query = (
        "query getDemarche { demarche { ...D } } fragment D on Demarche { number ...D }"
    )
    assert _validate(query) is None
