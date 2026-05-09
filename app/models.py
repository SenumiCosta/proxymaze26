from pydantic import BaseModel, Field, validator
from typing import List, Optional
from app.config import DEFAULT_EVENTS, SUPPORTED_INTEGRATIONS

class ConfigModel(BaseModel):
    check_interval_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    request_timeout_ms: Optional[int] = Field(default=None, ge=100, le=60000)

class ProxyPostRequest(BaseModel):
    proxies: List[str] = Field(default_factory=list)
    replace: bool = False

    @validator("proxies")
    def validate_proxies(cls, proxies):
        clean = []
        for proxy_url in proxies:
            if not isinstance(proxy_url, str) or not proxy_url.strip():
                continue
            clean.append(proxy_url.strip())
        return clean

class WebhookRequest(BaseModel):
    url: str

    @validator("url")
    def validate_url(cls, url):
        if not isinstance(url, str) or not url.strip():
            raise ValueError("url is required")
        if not url.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return url.strip()

class IntegrationRequest(BaseModel):
    type: str
    webhook_url: str
    username: Optional[str] = "ProxyMaze"
    events: Optional[List[str]] = None

    @validator("type")
    def validate_type(cls, integration_type):
        if integration_type not in SUPPORTED_INTEGRATIONS:
            raise ValueError("type must be slack or discord")
        return integration_type

    @validator("webhook_url")
    def validate_webhook_url(cls, webhook_url):
        if not isinstance(webhook_url, str) or not webhook_url.strip():
            raise ValueError("webhook_url is required")
        if not webhook_url.startswith(("http://", "https://")):
            raise ValueError("webhook_url must start with http:// or https://")
        return webhook_url.strip()

    @validator("events", always=True)
    def validate_events(cls, events):
        if not events:
            return DEFAULT_EVENTS.copy()
        allowed = set(DEFAULT_EVENTS)
        clean_events = []
        for event in events:
            if event in allowed and event not in clean_events:
                clean_events.append(event)
        if not clean_events:
            raise ValueError("events must include alert.fired or alert.resolved")
        return clean_events
