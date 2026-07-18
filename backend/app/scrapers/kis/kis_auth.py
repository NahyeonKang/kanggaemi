"""
app/scrapers/kis/kis_auth.py

KIS (Korea Investment & Securities) Open API REST auth client.

Ported from the reference kis_auth.py (REST portion only — no WebSocket
support, no file-based token caching). The access token is cached in
memory and refreshed automatically when it expires.
"""
import json
import logging
import time
from collections import namedtuple
from datetime import datetime, timedelta
from typing import Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_PATH = "/oauth2/tokenP"
_SMART_SLEEP_SECONDS = 0.05


def smart_sleep(seconds: float = _SMART_SLEEP_SECONDS) -> None:
    """Sleep briefly between consecutive paginated API calls."""
    time.sleep(seconds)


class APIResp:
    """Wraps a successful (HTTP 200) KIS API response."""

    def __init__(self, resp: requests.Response) -> None:
        self._rescode = resp.status_code
        self._resp = resp
        self._header = self._set_header()
        self._body = self._set_body()
        self._err_code = self._body.msg_cd
        self._err_message = self._body.msg1

    def getResCode(self) -> int:
        return self._rescode

    def _set_header(self):
        fld = {k: v for k, v in self._resp.headers.items() if k.islower()}
        _th = namedtuple("header", fld.keys())
        return _th(**fld)

    def _set_body(self):
        # KIS responses are UTF-8 JSON; requests' encoding auto-detection
        # can misdetect Korean text and produce mojibake, so decode explicitly.
        body = json.loads(self._resp.content.decode("utf-8"))
        _tb = namedtuple("body", body.keys())
        return _tb(**body)

    def getHeader(self):
        return self._header

    def getBody(self):
        return self._body

    def isOK(self) -> bool:
        try:
            return self.getBody().rt_cd == "0"
        except Exception:
            return False

    def getErrorCode(self) -> str:
        return self._err_code

    def getErrorMessage(self) -> str:
        return self._err_message

    def printError(self, url: str) -> None:
        logger.error(
            "Error in response: %s url=%s rt_cd=%s msg_cd=%s msg1=%s",
            self.getResCode(), url, self.getBody().rt_cd,
            self.getErrorCode(), self.getErrorMessage(),
        )


class APIRespError(APIResp):
    """
    Wraps a non-200 KIS API response.

    Provides empty Header/Body stubs so callers can safely call
    .getHeader().tr_cont and .getBody() without an AttributeError.
    """

    def __init__(self, status_code: int, error_text: str) -> None:
        self.status_code = status_code
        self.error_text = error_text
        self._error_code = str(status_code)
        self._error_message = error_text

    def getResCode(self) -> int:
        return self.status_code

    def isOK(self) -> bool:
        return False

    def getErrorCode(self) -> str:
        return self._error_code

    def getErrorMessage(self) -> str:
        return self._error_message

    def getBody(self):
        class EmptyBody:
            rt_cd = ""
            msg_cd = ""
            msg1 = ""

            def __getattr__(self, name):
                return None

        return EmptyBody()

    def getHeader(self):
        class EmptyHeader:
            tr_cont = ""

            def __getattr__(self, name):
                return ""

        return EmptyHeader()

    def printError(self, url: str = "") -> None:
        logger.error("Error Code: %s | %s | url=%s", self.status_code, self.error_text, url)


class KISAuthClient:
    """
    Manages KIS OAuth2 access tokens and wraps REST API calls.

    Requires KIS_APPKEY and KIS_SECRETKEY to be set in settings (.env).
    The access token is cached in memory only and refreshed automatically
    once it expires.
    """

    def __init__(self) -> None:
        self.base_url = settings.KIS_BASE_URL.rstrip("/")
        self.app_key = settings.KIS_APPKEY
        self.app_secret = settings.KIS_SECRETKEY

        if not self.app_key or not self.app_secret:
            raise RuntimeError(
                "KIS_APPKEY / KIS_SECRETKEY is not set. Add them to .env."
            )

        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def url_fetch(
        self,
        api_url: str,
        tr_id: str,
        tr_cont: str,
        params: dict,
        post_flag: bool = False,
    ) -> APIResp:
        """
        Call a KIS REST endpoint and return a parsed APIResp / APIRespError.

        Args:
            api_url: API path, e.g. "/uapi/domestic-stock/v1/quotations/comp-interest".
            tr_id: KIS transaction ID.
            tr_cont: Continuation flag ("" for first page, "N" for next page).
            params: Query params (GET) or JSON body (POST).
            post_flag: True to issue a POST request, False for GET.
        """
        url = f"{self.base_url}{api_url}"
        headers = self._build_headers(tr_id, tr_cont)

        if post_flag:
            res = requests.post(url, headers=headers, json=params)
        else:
            res = requests.get(url, headers=headers, params=params)

        if res.status_code == 200:
            return APIResp(res)

        logger.error("Error Code: %s | %s", res.status_code, res.text)
        return APIRespError(res.status_code, res.text)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_headers(self, tr_id: str, tr_cont: str) -> dict:
        return {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "authorization": f"Bearer {self._ensure_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": "P",
        }

    def _ensure_token(self) -> str:
        if (
            self._token is not None
            and self._token_expires_at is not None
            and datetime.now() < self._token_expires_at
        ):
            return self._token

        self._token, self._token_expires_at = self._issue_token()
        return self._token

    def _issue_token(self) -> tuple[str, datetime]:
        logger.info("Requesting new KIS access token.")
        res = requests.post(
            f"{self.base_url}{_TOKEN_PATH}",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            headers={"Content-Type": "application/json"},
        )
        res.raise_for_status()
        body = res.json()

        token = body.get("access_token")
        if not token:
            raise RuntimeError("KIS token response did not contain access_token.")

        expired_at_raw = body.get("access_token_token_expired")
        if expired_at_raw:
            expires_at = datetime.strptime(expired_at_raw, "%Y-%m-%d %H:%M:%S")
        else:
            expires_at = datetime.now() + timedelta(seconds=int(body.get("expires_in", 86400)))

        return token, expires_at
