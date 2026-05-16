"""Tests de persistencia de memoria del bot entre turnos (Módulo 2.1).

Cubre:
- A1: get_message_history devuelve los N más recientes en orden ASC
- A2: build_lead_context_block inyecta el contexto correctamente
"""
from __future__ import annotations

from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_history_client(msgs_descending: list[dict]):
    """Devuelve un CRMClient cuyo Supabase retorna msgs_descending (simula DESC)."""
    from app.crm.client import CRMClient

    mock_resp = MagicMock()
    mock_resp.data = msgs_descending

    mock_table = MagicMock()
    (mock_table.select.return_value
                .eq.return_value
                .order.return_value
                .limit.return_value
                .execute.return_value) = mock_resp

    client = CRMClient.__new__(CRMClient)
    client.sb = MagicMock()
    client.sb.table.return_value = mock_table
    return client


def _make_db_messages(n: int) -> list[dict]:
    """Genera n mensajes con sent_at distintos en orden ASC."""
    return [
        {
            "role": "user" if i % 2 == 0 else "bot",
            "content": f"mensaje {i + 1}",
            "sent_at": f"2026-01-01T{i // 60:02d}:{i % 60:02d}:00+00:00",
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# A1 — get_message_history devuelve los más recientes en orden ASC
# ---------------------------------------------------------------------------

class TestGetMessageHistoryOrder:

    def test_devuelve_mas_recientes_en_orden_cronologico(self):
        """Con 35 mensajes y limit=30, debe devolver mensajes 6-35 en ASC."""
        all_msgs = _make_db_messages(35)
        # Supabase con DESC+limit=30 devuelve los 30 más nuevos en orden inverso
        msgs_desc = list(reversed(all_msgs[5:]))
        client = _mock_history_client(msgs_desc)

        result = client.get_message_history("conv-id", limit=30)

        assert len(result) == 30
        assert result[0]["body"] == "mensaje 6"    # más viejo de los 30 recientes
        assert result[-1]["body"] == "mensaje 35"  # el más reciente

    def test_orden_ascendente_para_claude(self):
        """El array final debe ir de viejo a nuevo."""
        all_msgs = _make_db_messages(10)
        client = _mock_history_client(list(reversed(all_msgs)))

        result = client.get_message_history("conv-id", limit=10)

        bodies = [r["body"] for r in result]
        assert bodies == [f"mensaje {i + 1}" for i in range(10)]

    def test_conversacion_menor_al_limite(self):
        """Con menos mensajes que el límite, devuelve todos en ASC."""
        all_msgs = _make_db_messages(5)
        client = _mock_history_client(list(reversed(all_msgs)))

        result = client.get_message_history("conv-id", limit=30)

        assert len(result) == 5
        assert result[0]["body"] == "mensaje 1"
        assert result[-1]["body"] == "mensaje 5"

    def test_normaliza_role_a_direction(self):
        """role='user' → direction='inbound', cualquier otra → 'outbound'."""
        msgs = [
            {"role": "user",  "content": "hola",       "sent_at": "2026-01-01T00:00:00+00:00"},
            {"role": "bot",   "content": "respuesta",  "sent_at": "2026-01-01T00:01:00+00:00"},
            {"role": "agent", "content": "msg agente", "sent_at": "2026-01-01T00:02:00+00:00"},
        ]
        client = _mock_history_client(list(reversed(msgs)))

        result = client.get_message_history("conv-id", limit=30)

        assert result[0]["direction"] == "inbound"
        assert result[1]["direction"] == "outbound"
        assert result[2]["direction"] == "outbound"

    def test_historial_vacio(self):
        """Sin mensajes en BD, devuelve lista vacía."""
        client = _mock_history_client([])
        result = client.get_message_history("conv-id", limit=30)
        assert result == []


# ---------------------------------------------------------------------------
# A2 — build_lead_context_block
# ---------------------------------------------------------------------------

class TestLeadContextBlock:

    def test_contiene_campos_conocidos(self):
        """Con lead_data poblado, el bloque tiene todos los campos relevantes."""
        from app.bot.lead_context import build_lead_context_block

        lead_data = {
            "name": "Santiago",
            "company": "Instalaciones Red",
            "industry": "telecomunicaciones",
            "city": "Bogotá",
            "employee_count": 7,
            "has_contractors": False,
            "sst_process": "papel_excel",
            "pain_point": "cumplir Resolución 0312",
            "email": "santiago@empresa.com",
            "plan_recomendado": "PRO",
        }
        msgs = build_lead_context_block(lead_data)

        assert msgs is not None
        assert len(msgs) == 2

        content = msgs[0]["content"]
        assert msgs[0]["role"] == "user"
        assert "===CONTEXTO_PERSISTENTE_DEL_LEAD===" in content
        assert "===FIN_CONTEXTO_PERSISTENTE===" in content
        assert "Número de empleados: 7" in content
        assert "Sector / industria: telecomunicaciones" in content
        assert "Nombre: Santiago" in content
        assert "Empresa: Instalaciones Red" in content
        assert "Maneja contratistas: no" in content
        assert "Plan ya recomendado: PRO" in content
        assert "santiago@empresa.com" in content

        assert msgs[1]["role"] == "assistant"
        assert "Entendido" in msgs[1]["content"]

    def test_skipped_cuando_lead_data_vacio(self):
        """Primer turno: lead_data vacío → no se inyecta el bloque."""
        from app.bot.lead_context import build_lead_context_block

        assert build_lead_context_block({}) is None
        assert build_lead_context_block(None) is None

    def test_skipped_cuando_todos_desconocidos(self):
        """Si todos los valores son 'unknown', tampoco se inyecta."""
        from app.bot.lead_context import build_lead_context_block

        lead_data = {
            "name": "unknown",
            "company": "desconocido",
            "industry": "unknown",
            "email": "unknown",
            "city": "unknown",
        }
        assert build_lead_context_block(lead_data) is None

    def test_omite_campos_vacios(self):
        """Campos con valor vacío o 'unknown' no aparecen en el bloque."""
        from app.bot.lead_context import build_lead_context_block

        lead_data = {
            "name": "Santiago",
            "company": "unknown",
            "industry": "",
            "email": "unknown",
        }
        msgs = build_lead_context_block(lead_data)
        assert msgs is not None
        content = msgs[0]["content"]
        assert "Santiago" in content
        assert "unknown" not in content
        assert "Empresa" not in content
        assert "Sector" not in content
        assert "Email" not in content

    def test_has_contractors_si(self):
        """has_contractors=True → 'sí'."""
        from app.bot.lead_context import build_lead_context_block

        msgs = build_lead_context_block({"has_contractors": True, "name": "Juan"})
        assert msgs is not None
        assert "Maneja contratistas: sí" in msgs[0]["content"]

    def test_solo_country_sin_city(self):
        """Si city está vacío pero country sí, muestra country."""
        from app.bot.lead_context import build_lead_context_block

        msgs = build_lead_context_block({"country": "Colombia", "name": "Ana"})
        assert msgs is not None
        assert "Colombia" in msgs[0]["content"]

    def test_employee_count_como_string(self):
        """employee_count puede llegar como string '7' o int 7."""
        from app.bot.lead_context import build_lead_context_block

        msgs_int = build_lead_context_block({"employee_count": 7})
        msgs_str = build_lead_context_block({"employee_count": "7"})
        assert msgs_int is not None
        assert msgs_str is not None
        assert "Número de empleados: 7" in msgs_int[0]["content"]
        assert "Número de empleados: 7" in msgs_str[0]["content"]
