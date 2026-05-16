from __future__ import annotations
"""Tests de estructura para los schemas de Tool Use (M3)."""

from app.bot.tools.schemas import TOOLS, TOOL_NAMES


class TestToolsStructure:
    def test_hay_cuatro_herramientas(self):
        assert len(TOOLS) == 4

    def test_nombres_correctos(self):
        nombres = {t["name"] for t in TOOLS}
        assert nombres == {
            "recomendar_plan_y_cerrar",
            "escalar_a_demo",
            "pedir_cotizacion_por_correo",
            "escalar_a_humano",
        }

    def test_tool_names_frozenset(self):
        assert isinstance(TOOL_NAMES, frozenset)
        assert len(TOOL_NAMES) == 4

    def test_cada_tool_tiene_description_e_input_schema(self):
        for t in TOOLS:
            assert "description" in t, f"{t['name']} sin description"
            assert "input_schema" in t, f"{t['name']} sin input_schema"
            schema = t["input_schema"]
            assert schema.get("type") == "object"
            assert "properties" in schema
            assert "required" in schema


class TestRecomendar:
    def _schema(self):
        return next(t for t in TOOLS if t["name"] == "recomendar_plan_y_cerrar")

    def test_requeridos_correctos(self):
        assert set(self._schema()["input_schema"]["required"]) == {
            "plan", "ciclo", "razon_eleccion"
        }

    def test_enum_planes(self):
        enum = self._schema()["input_schema"]["properties"]["plan"]["enum"]
        assert set(enum) == {"BASIC", "STARTER", "PRO", "PLUS"}
        # Corporativo no está — va por escalar_a_demo
        assert "CORPORATIVO" not in enum

    def test_enum_ciclos(self):
        enum = self._schema()["input_schema"]["properties"]["ciclo"]["enum"]
        assert set(enum) == {"mensual", "anual"}


class TestEscalarADemo:
    def _schema(self):
        return next(t for t in TOOLS if t["name"] == "escalar_a_demo")

    def test_requerido_motivo(self):
        assert self._schema()["input_schema"]["required"] == ["motivo"]

    def test_enum_motivos(self):
        enum = self._schema()["input_schema"]["properties"]["motivo"]["enum"]
        assert "mas_de_130_empleados" in enum
        assert "corporativo_sst" in enum

    def test_num_empleados_y_pais_opcionales(self):
        props = self._schema()["input_schema"]["properties"]
        reqs = self._schema()["input_schema"]["required"]
        assert "num_empleados" in props
        assert "pais" in props
        assert "num_empleados" not in reqs
        assert "pais" not in reqs


class TestPedirCotizacion:
    def _schema(self):
        return next(t for t in TOOLS if t["name"] == "pedir_cotizacion_por_correo")

    def test_requeridos(self):
        assert set(self._schema()["input_schema"]["required"]) == {
            "email", "plan", "company"
        }

    def test_contact_name_opcional(self):
        props = self._schema()["input_schema"]["properties"]
        reqs = self._schema()["input_schema"]["required"]
        assert "contact_name" in props
        assert "contact_name" not in reqs

    def test_enum_planes_minuscula(self):
        enum = self._schema()["input_schema"]["properties"]["plan"]["enum"]
        assert all(p == p.lower() for p in enum)
        assert "pro" in enum


class TestEscalarHumano:
    def _schema(self):
        return next(t for t in TOOLS if t["name"] == "escalar_a_humano")

    def test_requeridos(self):
        assert set(self._schema()["input_schema"]["required"]) == {
            "motivo", "resumen_para_humano"
        }

    def test_enum_motivos(self):
        enum = self._schema()["input_schema"]["properties"]["motivo"]["enum"]
        assert "urgencia_auditoria" in enum
        assert "solicitud_explicita" in enum
        assert "bot_confused" in enum
