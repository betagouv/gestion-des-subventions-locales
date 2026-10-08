import copy


def _dossier_is_visible(dossier, allowed_groupe_ds_id):
    """Check if a dossier belongs to the allowed groupe instructeur."""
    if not dossier:
        return False
    groupe = dossier.get("groupeInstructeur") or {}
    return groupe.get("id") == allowed_groupe_ds_id


def _filter_dossier_nodes(dossiers_container, allowed_groupe_ds_id):
    """Filter nodes[] inside a dossiers connection object in-place."""
    nodes = dossiers_container.get("nodes")
    if nodes is None:
        return
    dossiers_container["nodes"] = [
        node for node in nodes if _dossier_is_visible(node, allowed_groupe_ds_id)
    ]


def filter_response(response_data, allowed_groupe_ds_id):
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
            _filter_dossier_nodes(dossiers, allowed_groupe_ds_id)

        for connection_field in ("pendingDeletedDossiers", "deletedDossiers"):
            connection = demarche.get(connection_field)
            if connection and isinstance(connection, dict):
                _filter_dossier_nodes(connection, allowed_groupe_ds_id)

    # getDossier → data.dossier (single dossier)
    dossier = data.get("dossier")
    if dossier and isinstance(dossier, dict) and "number" in dossier:
        if not _dossier_is_visible(dossier, allowed_groupe_ds_id):
            data["dossier"] = None
            result.setdefault("errors", []).append(
                {"message": "Dossier non autorisé pour ce token."}
            )

    return result
