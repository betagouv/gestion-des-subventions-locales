import requests

# TODO move it in api folder

DATA_GOUV_API_URL = "https://www.data.gouv.fr/api/1"


def get_dataset_api_url(dataset_id):
    return f"{DATA_GOUV_API_URL}/datasets/{dataset_id}/"


def get_dataset_resources(dataset_id, resource_format="csv"):
    """
    Interroge l'API data.gouv.fr et retourne les ressources d'un jeu de
    données pour un format donné, plutôt que des URLs de ressources figées
    dans le code (qui changeraient à chaque nouveau millésime).
    """
    url = get_dataset_api_url(dataset_id)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    dataset = response.json()

    return [
        r
        for r in dataset.get("resources", [])
        if r.get("format", "").lower() == resource_format.lower()
    ]


def get_latest_resource_url(dataset_id, resource_format="csv"):
    """
    Récupère l'URL de la ressource la plus récemment mise à jour d'un jeu de
    données pour un format donné.
    """
    resources = get_dataset_resources(dataset_id, resource_format)
    if not resources:
        raise ValueError(
            f"Aucune ressource au format {resource_format} trouvée sur "
            f"{get_dataset_api_url(dataset_id)}"
        )
    # Plusieurs ressources du même format peuvent coexister (nouveau
    # millésime ajouté sans retrait de l'ancien) : on prend la plus
    # récemment mise à jour par prudence.
    resource = max(resources, key=lambda r: r.get("last_modified") or "")
    return resource["url"]
