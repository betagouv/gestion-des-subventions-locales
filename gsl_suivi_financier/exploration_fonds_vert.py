"""
Script d'exploration de l'API Fonds Vert.

Usage:
    FV_USERNAME=... FV_PASSWORD=... venv/bin/python gsl_suivi_financier/exploration_fonds_vert.py
"""

import json
import os
import sys

import requests

BASE_URL = "https://api-fonds-vert.datahub.din.developpement-durable.gouv.fr"


def login(username: str, password: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/fonds_vert/login",
        headers={"Accept": "application/json"},
        data={"username": username, "password": password},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get(token: str, path: str, **params) -> dict:
    resp = requests.get(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )
    resp.raise_for_status()
    return resp.json()


def pp(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    username = os.environ.get("FV_USERNAME")
    password = os.environ.get("FV_PASSWORD")
    if not username or not password:
        print(
            "Usage: FV_USERNAME=... FV_PASSWORD=... venv/bin/python exploration_fonds_vert.py"
        )
        sys.exit(1)

    token = login(username, password)
    print("=== Authentification OK ===\n")

    # 1. Nombre de dossiers par année
    print("=== Dossiers par année ===")
    for annee in [2023, 2024, 2025, 2026]:
        data = get(token, "/fonds_vert/v2/dossiers", per_page=1, annee_millesime=annee)
        print(f"  {annee}: {data.get('count')} dossiers")
    print()

    # 2. Dossiers acceptés 2026 (données année en cours)
    print("=== Dossiers acceptés 2026 (année en cours) ===")
    data = get(
        token,
        "/fonds_vert/v2/dossiers",
        per_page=1,
        annee_millesime=2026,
        state="Accepté",
    )
    print(f"  Total acceptés 2026: {data.get('count')}")
    print()

    # 3. Exemple de dossier accepté avec finances
    print("=== Exemple dossier avec informations financières ===")
    data = get(
        token,
        "/fonds_vert/v2/dossiers",
        per_page=1,
        annee_millesime=2023,
        state="Accepté",
    )
    if data.get("data"):
        dossier_number = data["data"][0]["socle_commun"]["dossier_number"]
        detail = get(
            token, f"/fonds_vert/v2/dossiers/{dossier_number}", include_finances=True
        )
        pp(detail["data"])
    print()

    # 4. Filtre par SIRET
    print("=== Filtre par SIRET ===")
    data = get(token, "/fonds_vert/v2/dossiers", siret="21040129500014")
    print(f"  Résultats pour SIRET 21040129500014: {data.get('count')}")
    print()

    # 5. Stats par département
    print("=== Stats département (exemple Ain, 2026) ===")
    data = get(
        token, "/fonds_vert/stats/departements", annee_millesime=2026, per_page=1
    )
    pp(data["data"][0])
    print()

    # 6. Liste des démarches Fonds Vert (catégories)
    # Note: l'endpoint /demarches retourne une "Response Validation Error" mais les données
    # sont présentes dans detail[0].input (bug côté API, non bloquant).
    print("=== Démarches Fonds Vert ===")
    resp = requests.get(
        f"{BASE_URL}/fonds_vert/demarches",
        headers={"Authorization": f"Bearer {token}"},
    )
    raw = resp.json()
    demarches = (
        raw.get("detail", [{}])[0].get("input", [])
        if "detail" in raw
        else raw.get("data", [])
    )
    print(f"  {len(demarches)} démarches")
    axes = {}
    for d in demarches:
        axe = d.get("nom_axe", "?")
        axes.setdefault(axe, []).append(
            d.get("demarche_short_title", d.get("demarche_title", "?"))
        )
    for axe, titles in sorted(axes.items()):
        print(f"\n  Axe: {axe}")
        for t in titles:
            print(f"    - {t}")


if __name__ == "__main__":
    main()
