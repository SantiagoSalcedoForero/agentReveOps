from typing import Any, Optional
from pydantic import BaseModel, Field


class WhatsAppText(BaseModel):
    body: str


class WhatsAppMessage(BaseModel):
    id: str
    from_: str = Field(alias="from")
    timestamp: str
    type: str
    text: Optional[WhatsAppText] = None
    interactive: Optional[dict[str, Any]] = None
    button: Optional[dict[str, Any]] = None

    class Config:
        populate_by_name = True


class WhatsAppContact(BaseModel):
    profile: dict[str, Any]
    wa_id: str


class WhatsAppValue(BaseModel):
    messaging_product: str
    metadata: dict[str, Any]
    contacts: Optional[list[WhatsAppContact]] = None
    messages: Optional[list[WhatsAppMessage]] = None
    statuses: Optional[list[dict[str, Any]]] = None


class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    id: str
    changes: list[WhatsAppChange]


class WhatsAppWebhookPayload(BaseModel):
    object: str
    entry: list[WhatsAppEntry]


class HandoffAcceptRequest(BaseModel):
    conversation_id: str
    agent_profile_id: str


class HandoffMessageRequest(BaseModel):
    conversation_id: str
    agent_profile_id: str
    message: str


class LandingGateRequest(BaseModel):
    phone: str
    email: Optional[str] = None
    name: Optional[str] = None
    company: Optional[str] = None
    employees: Optional[int] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    job_title: Optional[str] = None
    professional_role: Optional[str] = None     # "Cómo te identificas" del form
    nivel_riesgo_arl: Optional[str] = None      # "Nivel de riesgo ARL" del form
    template_slug: str
    template_url: str
    # Nuevo: el landing envía el nombre humano y descripción de la plantilla
    # para que el bot pueda hablar específicamente de ELLA (antes solo
    # teníamos 5 slugs hardcoded). Ambos son opcionales por retrocompat.
    template_title: Optional[str] = None
    template_description: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    referrer: Optional[str] = None
    source_url: Optional[str] = None


class LandingVerifyRequest(BaseModel):
    phone: str
    code: str


class LeadIntentRequest(BaseModel):
    """Form de contacto / demo-request en verifty.com (no es descarga de plantilla)."""
    phone: str
    source_form: str              # "contact_form", "demo_request", "newsletter", etc.
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    employees: Optional[int] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    pain_point: Optional[str] = None
    message: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    referrer: Optional[str] = None
    source_url: Optional[str] = None
