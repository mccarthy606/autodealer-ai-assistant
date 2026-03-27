"""LLM service with strict tool-based interaction. Never invents data."""

import json
import logging
from typing import Any, Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.inventory import InventoryService

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Sos un asistente de un concesionario de autos en Argentina. Hablás en español argentino, corto y amigable.

REGLAS ESTRICTAS:
- NUNCA inventes autos, precios, kilometraje ni disponibilidad. Solo usa datos que te pasan por herramientas.
- Si no tenés la info, decí "No tengo esa info ahora" y ofrecé conectar con un vendedor.
- Respuestas: 1-3 oraciones cortas + 1 pregunta.
- Siempre proponé siguiente paso: visita al salón o hablar con vendedor.
- Para visitas: "¿Querés pasar a verla al salón hoy o mañana?" + mención de dirección/zona.
"""


def make_tools_definitions() -> list[dict]:
    """Define tools for LLM."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_inventory",
                "description": "Buscar autos en inventario. Usar SOLO con datos reales. No inventar.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "brand": {"type": "string", "description": "Marca (ej: Toyota, Ford)"},
                        "model": {"type": "string", "description": "Modelo"},
                        "year": {"type": "integer", "description": "Año"},
                        "condition": {"type": "string", "enum": ["new", "used", "zero_km"]},
                        "status": {"type": "string", "enum": ["available", "in_transit", "preorder"]},
                        "budget_min": {"type": "number", "description": "Presupuesto mínimo en ARS"},
                        "budget_max": {"type": "number", "description": "Presupuesto máximo en ARS"},
                        "max_km": {"type": "integer", "description": "Kilometraje máximo"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_lead",
                "description": "Crear lead cuando el cliente quiere visita o contacto con vendedor.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "phone": {"type": "string", "description": "Teléfono del cliente"},
                        "intent": {"type": "string", "enum": ["visit", "info", "financing"]},
                        "preferred_brand": {"type": "string"},
                        "preferred_model": {"type": "string"},
                        "budget_min": {"type": "number"},
                        "budget_max": {"type": "number"},
                        "notes": {"type": "string", "description": "Resumen: qué buscaba, qué le ofrecimos"},
                    },
                    "required": ["phone", "intent"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "handoff_to_manager",
                "description": "Transferir lead al vendedor. Usar después de create_lead cuando el cliente acepta visita.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "integer"},
                        "summary_text": {"type": "string", "description": "Resumen: qué buscaba, autos ofrecidos, horario acordado"},
                    },
                    "required": ["lead_id", "summary_text"],
                },
            },
        },
    ]


class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.model = settings.openai_model

    async def rephrase(self, text: str, lang: str = "es") -> Optional[str]:
        """Rephrase a deterministic bot response using LLM for more natural phrasing."""
        if not self.client:
            return None
        try:
            system_prompt = (
                f"You are a friendly car dealership assistant. "
                f"Rephrase the following message in {'Spanish' if lang.startswith('es') else 'English'} "
                f"to sound more natural and helpful. Keep the same meaning and all factual details. "
                f"Reply with ONLY the rephrased message, nothing else."
            )
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                max_tokens=500,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("LLM rephrase error: %s", e)
            return None

    async def generate_response(
        self,
        session: AsyncSession,
        dealership_id: int,
        user_message: str,
        conversation_history: list[dict[str, str]],
        state: dict[str, Any],
        user_phone: str,
        tools_executor: "ToolsExecutor",
    ) -> tuple[str, dict[str, Any]]:
        """
        Generate LLM response using tools. Returns (response_text, updated_state).
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Estado actual: {json.dumps(state, default=str)}"},
        ]
        for h in conversation_history[-10:]:  # last 10 messages
            role = "user" if h["direction"] == "in" else "assistant"
            messages.append({"role": role, "content": h.get("text", "") or ""})

        messages.append({"role": "user", "content": user_message})

        if not self.client or not settings.openai_api_key or settings.openai_api_key.startswith("sk-your"):
            return (
                "Hola. Por ahora no puedo procesar mensajes automáticamente. "
                "¿Querés que te contacte un vendedor? Escribí SÍ para que te llamen.",
                state,
            )

        max_iterations = 5
        for _ in range(max_iterations):
            try:
                response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=make_tools_definitions(),
                tool_choice="auto",
                temperature=0.3,
                max_tokens=200,
            )
            except Exception:
                return (
                    "Hola. Por ahora no puedo procesar mensajes automáticamente. "
                    "¿Querés que te contacte un vendedor? Escribí SÍ para que te llamen.",
                    state,
                )

            choice = response.choices[0]
            if not choice.message.tool_calls:
                text = (choice.message.content or "").strip()
                return (text or "No pude procesar tu mensaje. ¿Querés hablar con un vendedor?", state)

            for tc in choice.message.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                result = await tools_executor.execute(
                    name, args, session=session, dealership_id=dealership_id, user_phone=user_phone
                )
                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": name, "arguments": tc.function.arguments},
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str),
                    }
                )
                state = tools_executor.get_updated_state(state, name, args, result)

        return (
            "Te conecto con un vendedor para que te ayude. ¿Cuál es tu nombre?",
            state,
        )


class ToolsExecutor:
    """Executes tool calls and updates state."""

    def __init__(
        self,
        on_create_lead=None,
        on_handoff=None,
    ):
        self.on_create_lead = on_create_lead
        self.on_handoff = on_handoff
        self._last_lead_id: Optional[int] = None

    async def execute(
        self,
        name: str,
        args: dict,
        *,
        session: AsyncSession,
        dealership_id: int,
        user_phone: str,
    ) -> dict[str, Any]:
        if name == "search_inventory":
            items = await InventoryService.search(
                session,
                dealership_id,
                brand=args.get("brand"),
                model=args.get("model"),
                year=args.get("year"),
                condition=args.get("condition"),
                status=args.get("status"),
                budget_min=args.get("budget_min"),
                budget_max=args.get("budget_max"),
                max_km=args.get("max_km"),
                limit=5,
            )
            return {"found": len(items), "items": items}

        if name == "create_lead":
            lead = await self._create_lead(session, dealership_id, user_phone, args)
            self._last_lead_id = lead.id
            if self.on_create_lead:
                self.on_create_lead(lead)
            return {"lead_id": lead.id, "status": "created"}

        if name == "handoff_to_manager":
            lead_id = args.get("lead_id") or self._last_lead_id
            summary = args.get("summary_text", "")
            if self.on_handoff and lead_id:
                await self.on_handoff(dealership_id, lead_id, summary)
            return {"ok": True, "lead_id": lead_id}

        return {"error": f"Unknown tool: {name}"}

    async def _create_lead(
        self,
        session: AsyncSession,
        dealership_id: int,
        user_phone: str,
        args: dict,
    ):
        from src.db.models import Lead, LeadIntentEnum, LeadStatusEnum

        intent_val = args.get("intent", "visit")
        try:
            intent_enum = LeadIntentEnum(intent_val)
        except (ValueError, TypeError):
            intent_enum = LeadIntentEnum.visit

        lead = Lead(
            dealership_id=dealership_id,
            name=args.get("name"),
            phone=user_phone,
            intent=intent_enum,
            preferred_brand=args.get("preferred_brand"),
            preferred_model=args.get("preferred_model"),
            budget_min=args.get("budget_min"),
            budget_max=args.get("budget_max"),
            notes=args.get("notes"),
            status=LeadStatusEnum.qualified,
        )
        session.add(lead)
        await session.flush()
        return lead

    def get_updated_state(
        self,
        state: dict,
        tool_name: str,
        args: dict,
        result: dict,
    ) -> dict:
        s = dict(state)
        if tool_name == "search_inventory":
            s["last_seen_inventory"] = result.get("items", [])
        if tool_name == "create_lead":
            s["lead_id"] = result.get("lead_id")
        if tool_name == "handoff_to_manager":
            s["handoff_requested"] = True
        return s
