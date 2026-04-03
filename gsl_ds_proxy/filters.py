import copy


def _dossier_is_visible(dossier, allowed_ids):
    """Check if a dossier has at least one instructeur in allowed_ids."""
    groupe = dossier.get("groupeInstructeur") or {}
    instructeurs = groupe.get("instructeurs") or []
    instructeurs += dossier.get("instructeurs") or []

    if not instructeurs:
        # No instructeur data in response — cannot filter
        return True

    return any(inst.get("id") in allowed_ids for inst in instructeurs)


def _filter_dossier_nodes(dossiers_container, allowed_ids):
    """Filter nodes[] inside a dossiers connection object in-place."""
    nodes = dossiers_container.get("nodes")
    if nodes is None:
        return
    dossiers_container["nodes"] = [
        node for node in nodes if _dossier_is_visible(node, allowed_ids)
    ]


def filter_response(response_data, allowed_instructeur_ids):
    """Filter a DS GraphQL response to only include authorized dossiers.

    Returns a new dict (deep copy), leaving the original unchanged.
    """
    result = copy.deepcopy(response_data)
    data = result.get("data")
    if not data:
        return result

    # getDemarche → data.demarche.dossiers.nodes[]
    demarche = data.get("demarche")
    if demarche and isinstance(demarche, dict):
        dossiers = demarche.get("dossiers")
        if dossiers and isinstance(dossiers, dict):
            _filter_dossier_nodes(dossiers, allowed_instructeur_ids)

    # getGroupeInstructeur → data.groupeInstructeur.dossiers.nodes[]
    groupe = data.get("groupeInstructeur")
    if groupe and isinstance(groupe, dict):
        dossiers = groupe.get("dossiers")
        if dossiers and isinstance(dossiers, dict):
            _filter_dossier_nodes(dossiers, allowed_instructeur_ids)

    # getDossier → data.dossier (single dossier)
    dossier = data.get("dossier")
    if dossier and isinstance(dossier, dict) and "number" in dossier:
        if not _dossier_is_visible(dossier, allowed_instructeur_ids):
            data["dossier"] = None
            result.setdefault("errors", []).append(
                {"message": "Dossier non autorisé pour ce token."}
            )

    return result
