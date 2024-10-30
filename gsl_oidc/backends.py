from logging import getLogger

import requests
from mozilla_django_oidc.auth import (
    OIDCAuthenticationBackend as MozillaOIDCAuthenticationBackend,
)

logger = getLogger(__name__)


class OIDCAuthenticationBackend(MozillaOIDCAuthenticationBackend):
    def get_userinfo(self, access_token, id_token, payload):
        # Surcharge de la récupération des informations utilisateur:
        # le décodage JSON du contenu JWT pose problème avec ProConnect
        # qui le retourne en format JWT (content-type: application/jwt)
        # d'où ce petit hack.
        # Inspiré de : https://github.com/numerique-gouv/people/blob/b637774179d94cecb0ef2454d4762750a6a5e8c0/src/backend/core/authentication/backends.py#L47C1-L47C57
        user_response = requests.get(
            self.OIDC_OP_USER_ENDPOINT,
            headers={"Authorization": "Bearer {0}".format(access_token)},
            verify=self.get_settings("OIDC_VERIFY_SSL", True),
            timeout=self.get_settings("OIDC_TIMEOUT", None),
            proxies=self.get_settings("OIDC_PROXY", None),
        )
        user_response.raise_for_status()

        try:
            # cas où le type du token JWT est `application/json`
            return user_response.json()
        except requests.exceptions.JSONDecodeError:
            # sinon, on présume qu'il s'agit d'un token JWT au format `application/jwt`
            # comme c'est le cas pour ProConnect.
            return self.verify_token(user_response.text)
