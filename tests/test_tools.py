"""Os testes passam pelo servidor, não pelas funções.

Chamar a função Python direto não prova nada sobre o que o agente recebe: o
que importa é o que sai do `call_tool`, porque é isso que o modelo vai ler e
repassar ao usuário.
"""

from __future__ import annotations

from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from simples_nacional_mcp import server

TOOLS_ESPERADAS = {
    "calcular_das",
    "resolver_anexo_fator_r",
    "ressalvas_setoriais",
    "carga_fora_do_das",
}


async def chamar(nome: str, args: dict[str, Any]) -> dict[str, Any]:
    r = await server.call_tool(nome, args)
    # call_tool também pode devolver InputRequiredResult; nenhuma destas tools
    # pede entrada, então um resultado de outro tipo já é falha.
    assert isinstance(r, CallToolResult), type(r).__name__
    assert not r.is_error, r.content
    assert isinstance(r.structured_content, dict)
    return r.structured_content


class TestRegistro:
    async def test_as_quatro_tools_estao_expostas(self) -> None:
        nomes = {t.name for t in await server.list_tools()}
        assert nomes == TOOLS_ESPERADAS

    async def test_toda_tool_avisa_que_nao_e_assessoria_fiscal(self) -> None:
        # Um assistente vai repassar o resultado como conselho se ninguém disser
        # o contrário, e a descrição é o único lugar que ele sempre lê.
        for t in await server.list_tools():
            assert t.description is not None
            assert "assessoria fiscal" in t.description.lower(), t.name

    async def test_as_instrucoes_mandam_consultar_a_carga_fora_do_das(self) -> None:
        assert server.instructions is not None
        assert "carga_fora_do_das" in server.instructions


class TestCalcularDas:
    async def test_industria_na_quarta_faixa(self) -> None:
        out = await chamar(
            "calcular_das",
            {"anexo": "II", "rbt12": "1200000", "receita_do_mes": "100000"},
        )
        assert out["faixa"] == 4
        assert out["aliquota_nominal_pct"] == "11.20"
        assert out["aliquota_efetiva_pct"] == "9.33"
        assert out["das_do_mes"] == "9325.00"
        assert out["icms_iss_fora_do_das"] is False

    async def test_expoe_a_aliquota_exata_alem_da_arredondada(self) -> None:
        out = await chamar(
            "calcular_das",
            {"anexo": "II", "rbt12": "1200000", "receita_do_mes": "100000"},
        )
        assert out["aliquota_efetiva_pct"] == "9.33"
        assert out["aliquota_efetiva_exata_pct"].startswith("9.325")

    async def test_empresa_nova_usa_rbt12_proporcional(self) -> None:
        out = await chamar(
            "calcular_das",
            {
                "anexo": "I",
                "receita_acumulada": "90000",
                "meses_de_atividade": 3,
                "receita_do_mes": "30000",
            },
        )
        assert out["rbt12"] == "360000"
        assert "proporcionalizado" in out["rbt12_origem"]
        assert "§ 2º" in out["rbt12_origem"]

    async def test_acima_do_sublimite_explica_a_queda_da_aliquota(self) -> None:
        out = await chamar(
            "calcular_das",
            {"anexo": "II", "rbt12": "4000000", "receita_do_mes": "300000"},
        )
        assert out["icms_iss_fora_do_das"] is True
        assert "se reparte" in out["observacao"]

    async def test_anexo_iv_nao_lista_cpp_entre_os_tributos_do_das(self) -> None:
        out = await chamar(
            "calcular_das",
            {"anexo": "IV", "rbt12": "1000000", "receita_do_mes": "80000"},
        )
        assert "CPP" not in out["tributos_no_das"]

    async def test_sem_rbt12_nem_meses_recusa_em_vez_de_adivinhar(self) -> None:
        # O servidor levanta; no transporte isso vira resposta de erro. O que
        # importa é que ele não invente um RBT12.
        with pytest.raises(ToolError):
            await server.call_tool("calcular_das", {"anexo": "II", "receita_do_mes": "100000"})

    async def test_anexo_invalido_e_barrado_pelo_schema(self) -> None:
        # AnexoNome é um Literal, então a validação acontece antes do código da
        # tool: o modelo recebe de volta os valores aceitos, não um resultado
        # inventado para um anexo que não existe.
        with pytest.raises(ToolError):
            await server.call_tool(
                "calcular_das",
                {"anexo": "VI", "rbt12": "100000", "receita_do_mes": "10000"},
            )


class TestFatorR:
    @pytest.mark.parametrize(
        ("folha", "esperado"), [("28000", "III"), ("27999", "V"), ("50000", "III")]
    )
    async def test_limite_de_28_por_cento(self, folha: str, esperado: str) -> None:
        out = await chamar("resolver_anexo_fator_r", {"folha_12m": folha, "rbt12": "100000"})
        assert out["anexo_aplicavel"] == esperado

    async def test_devolve_a_razao_e_cita_a_norma(self) -> None:
        out = await chamar("resolver_anexo_fator_r", {"folha_12m": "28000", "rbt12": "100000"})
        assert out["fator_r_pct"] == "28.00"
        assert any("5º-M" in f for f in out["fundamentos"])


class TestRessalvasSetoriais:
    async def test_sem_argumento_lista_os_setores(self) -> None:
        out = await chamar("ressalvas_setoriais", {})
        assert "bebidas_alcoolicas" in out["setores_registrados"]

    async def test_cerveja_e_monofasica_e_tem_st(self) -> None:
        out = await chamar("ressalvas_setoriais", {"setor": "bebidas_alcoolicas"})
        (r,) = out["ressalvas"]
        assert r["pis_cofins_monofasico"] is True
        assert r["icms_substituicao_tributaria"] is True
        assert any("MAPA" in c for c in r["condicoes"])

    async def test_setor_desconhecido_nao_afirma_que_o_das_cobre_tudo(self) -> None:
        out = await chamar("ressalvas_setoriais", {"setor": "consultoria"})
        assert out["encontrado"] is False
        assert "não significa" in out["observacao"]


class TestCargaForaDoDas:
    async def test_anexo_iii_nao_tem_nada_fora(self) -> None:
        out = await chamar("carga_fora_do_das", {"anexo": "III"})
        assert out["fora_do_das"] == []
        assert "representa a carga tributária" in out["conclusao"]

    async def test_anexo_iv_acrescenta_cpp_sobre_a_folha(self) -> None:
        out = await chamar("carga_fora_do_das", {"anexo": "IV"})
        (item,) = out["fora_do_das"]
        assert item["tributo"] == "CPP"
        assert item["efeito"] == "acrescenta"
        assert "folha" in item["incide_sobre"]
        assert item["fundamentos"]

    async def test_produtor_e_revendedor_tem_efeitos_opostos(self) -> None:
        produtor = await chamar(
            "carga_fora_do_das",
            {
                "anexo": "II",
                "receita_monofasica": True,
                "receita_com_icms_st": True,
                "posicao": "produtor",
            },
        )
        revendedor = await chamar(
            "carga_fora_do_das",
            {
                "anexo": "I",
                "receita_monofasica": True,
                "receita_com_icms_st": True,
                "posicao": "revendedor",
            },
        )
        assert {i["efeito"] for i in produtor["fora_do_das"]} == {"acrescenta"}
        assert {i["efeito"] for i in revendedor["fora_do_das"]} == {"reduz"}

    async def test_avisa_para_nao_somar_efeitos_opostos_num_numero(self) -> None:
        out = await chamar(
            "carga_fora_do_das",
            {"anexo": "IV", "receita_monofasica": True, "posicao": "revendedor"},
        )
        assert len(out["fora_do_das"]) == 2
        assert "não se somam" in out["conclusao"]

    async def test_diz_explicitamente_que_nao_quantifica(self) -> None:
        # Um agente que não for avisado vai inventar um número.
        out = await chamar("carga_fora_do_das", {"anexo": "IV"})
        assert "repartição do DAS por tributo" in out["nao_quantificado"]
