"""Field-level allow-list for the `Demarche` GraphQL type.

The DN proxy hands a token holder a single démarche; the dossier-level
filter trims the dossiers they may see, but DS will happily expose the
full `Demarche` shape (e.g. `groupeInstructeurs.instructeurs`) if asked.
This module walks the parsed query AST and rejects any selection on the
`Demarche` type that is not in `ALLOWED_DEMARCHE_FIELDS`.
"""

from graphql.language.ast import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
)

ALLOWED_DEMARCHE_FIELDS = frozenset(
    {
        "number",
        "title",
        "state",
        "dateCreation",
        "dateFermeture",
        "activeRevision",
        "revision",
        "dossiers",
        "pendingDeletedDossiers",
        "deletedDossiers",
        # GraphQL meta-fields are always allowed.
        "__typename",
        "__schema",
        "__type",
    }
)


def _fragments_by_name(doc):
    return {
        d.name.value: d
        for d in doc.definitions
        if isinstance(d, FragmentDefinitionNode)
    }


def _resolve_spread(sel, fragments, seen_fragments):
    """Yield (selection_set, new_seen) for a spread, or None if cycle/missing."""
    frag_name = sel.name.value
    if frag_name in seen_fragments:
        return None
    fragment = fragments.get(frag_name)
    if fragment is None:
        return None
    return fragment.selection_set, seen_fragments | {frag_name}


def _check_demarche_selection_set(selection_set, fragments, seen_fragments):
    """Validate the direct selection set of a `Demarche` (aliases ignored)."""
    if selection_set is None:
        return None
    for sel in selection_set.selections:
        if isinstance(sel, FieldNode):
            if sel.name.value not in ALLOWED_DEMARCHE_FIELDS:
                return sel.name.value
            continue
        if isinstance(sel, InlineFragmentNode):
            sub = sel.selection_set
            new_seen = seen_fragments
        elif isinstance(sel, FragmentSpreadNode):
            resolved = _resolve_spread(sel, fragments, seen_fragments)
            if resolved is None:
                continue
            sub, new_seen = resolved
        else:
            continue
        offender = _check_demarche_selection_set(sub, fragments, new_seen)
        if offender is not None:
            return offender
    return None


def _walk_for_demarche(selection_set, fragments, seen_fragments):
    """Find every `demarche` field in the AST and apply the Demarche guard.

    Whenever we hit a field literally named `demarche`, we apply the
    allow-list to its selection set. We also keep descending so that a
    `demarche` nested under e.g. `dossier` or `demarche.dossiers.nodes`
    is still caught.
    """
    if selection_set is None:
        return None
    for sel in selection_set.selections:
        if isinstance(sel, FieldNode):
            if sel.name.value == "demarche":
                offender = _check_demarche_selection_set(
                    sel.selection_set, fragments, set()
                )
                if offender is not None:
                    return offender
            sub, new_seen = sel.selection_set, seen_fragments
        elif isinstance(sel, InlineFragmentNode):
            sub, new_seen = sel.selection_set, seen_fragments
        elif isinstance(sel, FragmentSpreadNode):
            resolved = _resolve_spread(sel, fragments, seen_fragments)
            if resolved is None:
                continue
            sub, new_seen = resolved
        else:
            continue
        offender = _walk_for_demarche(sub, fragments, new_seen)
        if offender is not None:
            return offender
    return None


def validate_demarche_selections(doc, operation):
    """Return the offending field name, or None if every `Demarche` selection is allowed."""
    fragments = _fragments_by_name(doc)
    return _walk_for_demarche(operation.selection_set, fragments, set())
