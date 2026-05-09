from pydantic import BaseModel
from typing import List, Optional

class ConfigModel(BaseModel):
    check_interval_seconds: Optional[int] = None
    request_timeout_ms: Optional[int] = None

class ProxyPostRequest(BaseModel):
    proxies: List[str] = []
    replace: bool = False

class WebhookRequest(BaseModel):
    url: str

class IntegrationRequest(BaseModel):
    type: str
    webhook_url: str
    username: str
    events: Optional[List[str]] = None
