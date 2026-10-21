import pytest
from graphql import parse
from graphql.language.ast import OperationDefinitionNode

from dn.proxy.exceptions import ProxyError
from dn.proxy.query_guard import validate_demarche_selections


def _validate(query, operation_name=None):
    doc = parse(query)
    operations = [d for d in doc.definitions if isinstance(d, OperationDefinitionNode)]
    if operation_name:
        operation = next(
            o for o in operations if o.name and o.name.value == operation_name
        )
    else:
        operation = operations[0]
    validate_demarche_selections(doc, operation)


def test_top_level_demarche_with_allowed_field_accepted():
    _validate("query getDemarche { demarche { number } }")


def test_top_level_demarche_with_all_allowed_fields_accepted():
    query = (
        "query getDemarche { demarche { "
        "number title state dateCreation dateFermeture "
        "activeRevision { id } "
        "dossiers { nodes { number } } "
        "} }"
    )
    _validate(query)


def test_top_level_demarche_with_groupeInstructeurs_rejected():
    query = "query getDemarche { demarche { groupeInstructeurs { id } } }"
    with pytest.raises(ProxyError, match="`groupeInstructeurs`"):
        _validate(query)


def test_nested_dossier_demarche_with_groupeInstructeurs_rejected():
    query = "query getDossier { dossier { demarche { groupeInstructeurs { id } } } }"
    with pytest.raises(ProxyError, match="`groupeInstructeurs`"):
        _validate(query)


def test_dossiers_subselection_in_demarche_is_out_of_scope():
    query = (
        "query getDemarche { demarche { dossiers { nodes "
        "{ number groupeInstructeur { instructeurs { id } } } } } }"
    )
    _validate(query)


def test_inline_fragment_with_forbidden_field_rejected():
    query = "query getDemarche { demarche { ... on Demarche { revisions { id } } } }"
    with pytest.raises(ProxyError, match="`revisions`"):
        _validate(query)


def test_inline_fragment_with_allowed_field_accepted():
    query = "query getDemarche { demarche { ... on Demarche { number title } } }"
    _validate(query)


def test_fragment_spread_with_forbidden_field_rejected():
    query = (
        "query getDemarche { demarche { ...D } } "
        "fragment D on Demarche { service { nom } }"
    )
    with pytest.raises(ProxyError, match="`service`"):
        _validate(query)


def test_fragment_spread_with_allowed_field_accepted():
    query = (
        "query getDemarche { demarche { ...D } } "
        "fragment D on Demarche { number title }"
    )
    _validate(query)


def test_aliased_forbidden_field_rejected():
    query = "query getDemarche { demarche { x: groupeInstructeurs { id } } }"
    with pytest.raises(ProxyError, match="`groupeInstructeurs`"):
        _validate(query)


def test_typename_inside_demarche_allowed():
    query = "query getDemarche { demarche { __typename number } }"
    _validate(query)


def test_getDossier_without_demarche_selection_passes_guard():
    query = "query getDossier { dossier { number } }"
    _validate(query)


def test_demarche_inside_dossiers_nodes_caught():
    query = (
        "query getDemarche { demarche { dossiers { nodes "
        "{ demarche { groupeInstructeurs { id } } } } } }"
    )
    with pytest.raises(ProxyError, match="`groupeInstructeurs`"):
        _validate(query)


def test_pending_deleted_dossiers_allowed():
    query = (
        "query getDemarche { demarche { pendingDeletedDossiers { nodes { number } } } }"
    )
    _validate(query)


def test_deleted_dossiers_allowed():
    query = "query getDemarche { demarche { deletedDossiers { nodes { number } } } }"
    _validate(query)


def test_self_referencing_fragment_does_not_loop():
    query = (
        "query getDemarche { demarche { ...D } } fragment D on Demarche { number ...D }"
    )
    _validate(query)
