from __future__ import annotations

import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import SiigoConfig, load_siigo_config


class SiigoError(RuntimeError):
    pass


class SiigoConnectionError(SiigoError):
    """Fallo de red antes de obtener una respuesta HTTP de Siigo."""


class SiigoUncertainWriteError(SiigoError):
    """Un POST pudo haber llegado a Siigo, pero no se recibió confirmación."""


class SiigoClient:
    """Cliente Siigo API con timeouts, diagnóstico y reintentos seguros.

    GET/consultas pueden reintentarse ante fallos transitorios. Las escrituras
    NO se reintentan automáticamente: un timeout tras un POST se marca como
    estado incierto para evitar comprobantes duplicados.
    """

    CONNECT_TIMEOUT = 12
    READ_TIMEOUT = 35
    SAFE_RETRIES = 2

    def __init__(self, config: SiigoConfig | None = None):
        self.config = config or load_siigo_config()
        self._token: str | None = None
        self._token_expires_at = 0

    def _timeout_for(self, method: str) -> int:
        # urllib usa un único timeout para conexión/lectura. Damos más margen
        # a escrituras, pero jamás las reintentamos automáticamente.
        return self.READ_TIMEOUT if method.upper() != "POST" else 45

    def _request_once(self, method: str, url: str, headers: dict, body: bytes | None):
        req = Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urlopen(req, timeout=self._timeout_for(method)) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")[:2000]
            except Exception:
                detail = ""
            raise SiigoError(f"Siigo respondió HTTP {exc.code}. {detail}".strip()) from exc
        except (URLError, socket.timeout, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise SiigoConnectionError(
                f"Siigo no respondió a tiempo o la conexión se interrumpió. Detalle técnico: {reason}"
            ) from exc

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 payload: dict | None = None, authenticate: bool = True,
                 extra_headers: dict | None = None):
        if not self.config.enabled:
            raise SiigoError("La integración Siigo está deshabilitada. Configura SIIGO_ENABLED=true en .env.")
        if authenticate and not self.config.credentials_configured:
            raise SiigoError("Faltan SIIGO_USERNAME, SIIGO_ACCESS_KEY o SIIGO_PARTNER_ID en el archivo .env.")

        url = f"{self.config.base_url}{path}"
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                url += "?" + urlencode(clean)

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if authenticate:
            headers["Authorization"] = f"Bearer {self.get_token()}"
            headers["Partner-Id"] = self.config.partner_id
        if extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items() if v not in (None, "")})

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        method_upper = method.upper()
        safe_to_retry = method_upper in {"GET", "HEAD"} or (method_upper == "POST" and path == "/auth")
        attempts = self.SAFE_RETRIES + 1 if safe_to_retry else 1

        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                return self._request_once(method_upper, url, headers, body)
            except SiigoConnectionError as exc:
                last_exc = exc
                if attempt >= attempts:
                    break
                time.sleep(0.8 * attempt)

        if method_upper in {"POST", "PUT", "PATCH", "DELETE"} and path != "/auth":
            raise SiigoUncertainWriteError(
                "Siigo no confirmó la operación. Por seguridad NO se reintentó automáticamente. "
                "Verifica primero en Siigo si el comprobante fue creado antes de volver a enviarlo. "
                f"Detalle: {last_exc}"
            ) from last_exc
        raise last_exc or SiigoConnectionError("No fue posible conectar con Siigo.")

    def get_token(self, force_refresh: bool = False) -> str:
        now = int(time.time())
        if not force_refresh and self._token and now < self._token_expires_at - 60:
            return self._token
        if not self.config.username or not self.config.access_key:
            raise SiigoError("Faltan SIIGO_USERNAME o SIIGO_ACCESS_KEY en .env.")
        auth = self._request("POST", "/auth", payload={"username": self.config.username, "access_key": self.config.access_key}, authenticate=False)
        token = auth.get("access_token")
        if not token:
            raise SiigoError("Siigo no devolvió access_token durante la autenticación.")
        expires_in = int(auth.get("expires_in") or 86400)
        self._token = token
        self._token_expires_at = now + expires_in
        return token

    def document_types(self, type_: str = "FV"):
        return self._request("GET", "/v1/document-types", params={"type": type_})
    def users(self, page: int = 1, page_size: int = 100):
        return self._request("GET", "/v1/users", params={"page": page, "page_size": page_size})
    def payment_types(self, document_type: str = "FV"):
        return self._request("GET", "/v1/payment-types", params={"document_type": document_type})
    def taxes(self):
        return self._request("GET", "/v1/taxes")
    def customers(self, identification: str | None = None, page: int = 1, page_size: int = 25):
        return self._request("GET", "/v1/customers", params={"identification": identification, "page": page, "page_size": page_size})
    def customer(self, customer_id: str):
        return self._request("GET", f"/v1/customers/{customer_id}")
    def create_customer(self, payload: dict):
        return self._request("POST", "/v1/customers", payload=payload)
    def update_customer(self, customer_id: str, payload: dict):
        return self._request("PUT", f"/v1/customers/{customer_id}", payload=payload)
    def journal_document_types(self):
        return self._request("GET", "/v1/document-types", params={"type": "CC"})
    def resolve_journal_document_type(self, code: str) -> dict:
        wanted = str(code or "").strip().upper().replace("CC-", "")
        raw = self.journal_document_types()
        rows = raw if isinstance(raw, list) else (raw.get("results") or raw.get("data") or raw.get("items") or [] if isinstance(raw, dict) else [])
        for item in rows:
            if not isinstance(item, dict):
                continue
            candidates = [item.get("code"), item.get("name"), item.get("description"), item.get("number")]
            normalized = " | ".join(str(x or "").upper() for x in candidates)
            if f"CC-{wanted}" in normalized or str(item.get("code") or "").strip() == wanted or str(item.get("number") or "").strip() == wanted:
                if item.get("id") not in (None, ""):
                    return item
        raise SiigoError(f"No se encontró en Siigo el comprobante contable CC-{wanted}.")
    def journals(self, **filters):
        return self._request("GET", "/v1/journals", params=filters)
    def journal(self, journal_id: str):
        return self._request("GET", f"/v1/journals/{journal_id}")
    def create_journal(self, payload: dict, idempotency_key: str | None = None):
        if not self.config.live_payroll_journal_enabled:
            raise SiigoError("La carga real de nómina a Siigo está bloqueada. Configura SIIGO_LIVE_PAYROLL_JOURNAL_ENABLED=true únicamente después de validar la previsualización.")
        return self._request("POST", "/v1/journals", payload=payload, extra_headers={"Idempotency-Key": idempotency_key} if idempotency_key else None)


_CLIENT: SiigoClient | None = None

def get_siigo_client() -> SiigoClient:
    global _CLIENT
    cfg = load_siigo_config()
    if _CLIENT is None or _CLIENT.config != cfg:
        _CLIENT = SiigoClient(cfg)
    return _CLIENT
