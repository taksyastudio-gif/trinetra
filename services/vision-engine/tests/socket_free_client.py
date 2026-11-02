"""
Socket-Free Test Client for FastAPI Applications.
Enables reliable, deterministic in-process API testing in sandboxed Windows environments
without requiring OS loopback network permissions, AnyIO blocking portals, or socket.socketpair().
"""

import dataclasses
import inspect
from typing import Any, Dict, Optional, Tuple, Union, get_args, get_origin
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ValidationError
from starlette.datastructures import Headers


class SocketFreeResponse:
    """Simulates an HTTP response object with status_code, headers, json(), and content."""

    def __init__(
        self,
        status_code: int,
        json_data: Any = None,
        headers: Optional[Union[Dict[str, str], Headers]] = None,
        content: bytes = b""
    ):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers if isinstance(headers, Headers) else Headers(headers or {})
        self.content = content

    def json(self) -> Any:
        if self._json_data is not None:
            return self._json_data
        if self.content:
            import json
            try:
                return json.loads(self.content.decode("utf-8"))
            except Exception:
                pass
        return None

    @property
    def text(self) -> str:
        if self.content:
            return self.content.decode("utf-8", errors="replace")
        if self._json_data is not None:
            import json
            return json.dumps(self._json_data)
        return ""


class SocketFreeTestClient:
    """
    In-memory FastAPI test client that dispatches requests directly to route endpoint handlers.
    Validates request payloads against Pydantic models, catches HTTPExceptions,
    and executes startup/shutdown lifecycle hooks cleanly without sockets.
    """
    __test__ = False  # Prevent pytest from collecting this class as a test

    def __init__(self, app: FastAPI):
        self.app = app
        self._routes: Dict[Tuple[str, str], Tuple[Any, inspect.Signature, Any]] = {}
        for r in app.routes:
            if hasattr(r, "path") and hasattr(r, "methods") and hasattr(r, "endpoint"):
                deps = getattr(r, "dependencies", []) or []
                for m in r.methods:
                    self._routes[(m.upper(), r.path)] = (r.endpoint, inspect.signature(r.endpoint), deps)

    def __enter__(self) -> "SocketFreeTestClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Executes application shutdown hooks and releases hardware resources."""
        from app.main import camera_manager, perception_pipeline, speech_manager
        try:
            perception_pipeline.stop()
            camera_manager.stop_session()
            speech_manager.shutdown()
        except Exception:
            pass

    def request(
        self,
        method: str,
        url: str,
        json: Any = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> SocketFreeResponse:
        parsed_url = urlparse(url)
        path = parsed_url.path
        query_dict = {k: v[0] for k, v in parse_qs(parsed_url.query).items()}
        if params:
            query_dict.update(params)

        h_dict = Headers(headers or {})

        # Handle OpenAPI /docs if configured on app
        if method.upper() == "GET":
            if self.app.docs_url and path == self.app.docs_url:
                return SocketFreeResponse(status_code=200, content=b"<!DOCTYPE html><html><head><title>Docs</title></head></html>")
            if self.app.openapi_url and path == self.app.openapi_url:
                return SocketFreeResponse(status_code=200, json_data={"openapi": "3.1.0"})

        key = (method.upper(), path)
        if key not in self._routes:
            return SocketFreeResponse(status_code=404, json_data={"detail": f"Route '{method.upper()} {path}' Not Found"})

        endpoint, sig, deps = self._routes[key]

        # Execute route dependencies (e.g. verify_token)
        try:
            for dep in deps:
                dep_fn = getattr(dep, "dependency", None)
                if dep_fn:
                    dep_sig = inspect.signature(dep_fn)
                    dep_kwargs = {}
                    for p_name in dep_sig.parameters:
                        if "token" in p_name:
                            dep_kwargs[p_name] = h_dict.get("x-trinetra-session-token")
                    dep_fn(**dep_kwargs)
        except HTTPException as h_exc:
            return SocketFreeResponse(status_code=h_exc.status_code, json_data={"detail": h_exc.detail})

        kwargs: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            ann = param.annotation
            origin = get_origin(ann)
            target_cls = ann
            if origin is Union:
                args = [a for a in get_args(ann) if a is not type(None)]
                if args:
                    target_cls = args[0]

            is_model = inspect.isclass(target_cls) and issubclass(target_cls, BaseModel)

            if is_model:
                try:
                    kwargs[param_name] = target_cls(**(json or {}))
                except ValidationError as v_err:
                    return SocketFreeResponse(status_code=422, json_data={"detail": v_err.errors()})
            elif param_name in query_dict:
                val = query_dict[param_name]
                if param.annotation == int:
                    val = int(val)
                elif param.annotation == float:
                    val = float(val)
                kwargs[param_name] = val
            elif param.default is not inspect.Parameter.empty:
                kwargs[param_name] = param.default

        try:
            res = endpoint(**kwargs)
            if isinstance(res, Response):
                return SocketFreeResponse(
                    status_code=res.status_code or 200,
                    headers=res.headers,
                    content=getattr(res, "body", b"")
                )
            elif isinstance(res, list):
                return SocketFreeResponse(
                    status_code=200,
                    json_data=[x.model_dump() if isinstance(x, BaseModel) else x for x in res]
                )
            elif isinstance(res, BaseModel):
                return SocketFreeResponse(status_code=200, json_data=res.model_dump())
            elif isinstance(res, dict):
                return SocketFreeResponse(status_code=200, json_data=res)
            elif res is None:
                return SocketFreeResponse(status_code=200, json_data=None)
            else:
                return SocketFreeResponse(status_code=200, json_data=res)
        except HTTPException as h_exc:
            return SocketFreeResponse(status_code=h_exc.status_code, json_data={"detail": h_exc.detail})
        except Exception as exc:
            return SocketFreeResponse(status_code=500, json_data={"detail": str(exc)})

    def get(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> SocketFreeResponse:
        return self.request("GET", url, headers=headers, params=params)

    def post(self, url: str, json: Any = None, headers: Optional[Dict[str, str]] = None) -> SocketFreeResponse:
        return self.request("POST", url, json=json, headers=headers)
