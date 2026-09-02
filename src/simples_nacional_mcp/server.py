"""Servidor MCP para cálculo do Simples Nacional.

As ferramentas calculam a partir das tabelas publicadas em lei. Nenhuma delas
é assessoria fiscal, e as descrições dizem isso porque um assistente vai
repassar o resultado como se fosse conselho se ninguém o avisar.

O cálculo vive em `simples-nacional-complexo`; aqui só há a interface. A lei
não é duplicada.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from simples_nacional import (
    TRIBUTOS_NO_DAS,
    Anexo,
    PosicaoNaCadeia,
    aliquota_efetiva,
    anexo_por_fator_r,
    carga_fora_do_das,
    das_devido,
    fator_r,
    ressalvas_de,
    setores_registrados,
)

__all__ = ["main", "server"]

_AVISO = (
    "Calcula as tabelas publicadas em lei. Não é assessoria fiscal: "
    "enquadramento de atividade, regime e obrigações acessórias são decisões "
    "de contador."
)

server = MCPServer(
    name="simples-nacional",
    title="Simples Nacional",
    instructions=(
        "Cálculo do Simples Nacional a partir dos Anexos I a V da LC 123/2006. "
        "Ao relatar um resultado, sempre mencione o que a alíquota não cobre: "
        "chame `carga_fora_do_das` antes de afirmar qual é a carga tributária "
        "de alguém, porque a alíquota efetiva é a carga do DAS, não a carga "
        "total. Nunca apresente estes números como assessoria fiscal."
    ),
)

_ANEXOS = {a.value: a for a in Anexo}
AnexoNome = Literal["I", "II", "III", "IV", "V"]


def _anexo(nome: str) -> Anexo:
    try:
        return _ANEXOS[nome.strip().upper()]
    except KeyError:
        raise ValueError(f"anexo inválido: {nome!r}. Use um de {', '.join(_ANEXOS)}.") from None


def _dinheiro(valor: float | int | str, campo: str) -> Decimal:
    """Aceita o que um assistente costuma mandar, sem perder exatidão.

    Um float chegando por JSON já perdeu exatidão antes de nos alcançar, então
    o convertemos via str, que é a melhor aproximação disponível aqui.
    """
    try:
        return Decimal(str(valor))
    except Exception:
        raise ValueError(f"{campo} não é um valor numérico: {valor!r}") from None


@server.tool(
    description=(
        "Calcula o DAS do mês e a alíquota efetiva do Simples Nacional para um "
        "anexo e um RBT12 (receita bruta dos 12 meses anteriores). Devolve "
        "também a faixa, e bandeiras para o sublimite de ICMS/ISS e para a "
        "saída do regime. Se a empresa tem menos de 13 meses de atividade, "
        "informe receita_acumulada e meses_de_atividade em vez de rbt12. "
        "A alíquota devolvida é a carga do DAS: consulte carga_fora_do_das "
        "antes de afirmar qual é a carga tributária total. " + _AVISO
    )
)
def calcular_das(
    anexo: AnexoNome,
    receita_do_mes: float | int | str,
    rbt12: float | int | str | None = None,
    receita_acumulada: float | int | str | None = None,
    meses_de_atividade: int | None = None,
) -> dict[str, Any]:
    a = _anexo(anexo)

    if rbt12 is None:
        if receita_acumulada is None or meses_de_atividade is None:
            raise ValueError(
                "informe rbt12, ou receita_acumulada junto com meses_de_atividade "
                "para empresa com menos de 13 meses."
            )
        from simples_nacional import rbt12_proporcional

        base = rbt12_proporcional(
            _dinheiro(receita_acumulada, "receita_acumulada"), meses_de_atividade
        )
        origem_rbt12 = (
            f"proporcionalizado de {receita_acumulada} em {meses_de_atividade} "
            "meses, conforme art. 18, § 2º"
        )
    else:
        base = _dinheiro(rbt12, "rbt12")
        origem_rbt12 = "informado"

    ap = aliquota_efetiva(base, a)
    das = das_devido(_dinheiro(receita_do_mes, "receita_do_mes"), ap)

    return {
        "anexo": a.value,
        "anexo_descricao": a.descricao,
        "rbt12": str(base),
        "rbt12_origem": origem_rbt12,
        "faixa": ap.faixa.numero,
        "aliquota_nominal_pct": str(ap.aliquota_nominal),
        "parcela_a_deduzir": str(ap.parcela_deduzir),
        "aliquota_efetiva_pct": str(ap.aliquota_arredondada),
        "aliquota_efetiva_exata_pct": str(ap.aliquota_efetiva),
        "das_do_mes": str(das),
        "tributos_no_das": list(TRIBUTOS_NO_DAS[a]),
        "icms_iss_fora_do_das": ap.icms_iss_fora_do_das,
        "acima_do_limite_do_simples": ap.acima_do_limite,
        "observacao": (
            "Acima do sublimite de R$ 3.600.000 o ICMS e o ISS deixam de ser "
            "recolhidos no DAS, e é por isso que a alíquota do DAS cai ao "
            "cruzar essa linha. A carga total não diminui: ela se reparte."
            if ap.icms_iss_fora_do_das
            else "A alíquota efetiva é a carga do DAS, não a carga tributária total."
        ),
        "aviso": _AVISO,
    }


@server.tool(
    description=(
        "Decide entre Anexo III e Anexo V para atividades do § 5º-I (serviços "
        "intelectuais) pelo Fator R: a razão entre a folha de salários e a "
        "receita bruta, ambas dos 12 meses anteriores. Razão de 28% ou mais "
        "leva ao Anexo III, abaixo disso ao Anexo V. A diferença de alíquota "
        "nominal entre os dois chega a 9,5 pontos, então errar isto custa mais "
        "que errar a fórmula. " + _AVISO
    )
)
def resolver_anexo_fator_r(
    folha_12m: float | int | str,
    rbt12: float | int | str,
) -> dict[str, Any]:
    folha = _dinheiro(folha_12m, "folha_12m")
    receita = _dinheiro(rbt12, "rbt12")

    razao = fator_r(folha, receita)
    anexo = anexo_por_fator_r(folha, receita)

    return {
        "fator_r": str(razao),
        "fator_r_pct": str((razao * 100).quantize(Decimal("0.01"))),
        "limite_pct": "28.00",
        "anexo_aplicavel": anexo.value,
        "anexo_descricao": anexo.descricao,
        "motivo": (
            "Fator R igual ou superior a 28% enquadra no Anexo III."
            if anexo is Anexo.III
            else "Fator R inferior a 28% enquadra no Anexo V."
        ),
        "fundamentos": [
            "LC 123/2006, art. 18, §§ 5º-J e 5º-M",
        ],
        "observacao": (
            "O limite é inclusivo no Anexo III: o § 5º-M fala em razão igual ou superior a 28%."
        ),
        "aviso": _AVISO,
    }


@server.tool(
    description=(
        "Lista as ressalvas de um setor cuja receita tem regime especial de "
        "PIS/COFINS (tributação monofásica) ou de ICMS (substituição "
        "tributária): bebidas alcoólicas e frias, medicamentos, cosméticos, "
        "autopeças e pneus, combustíveis. Sem argumento, lista os setores "
        "registrados. Ausência de um setor aqui não significa que o DAS cubra "
        "toda a carga dele. " + _AVISO
    )
)
def ressalvas_setoriais(setor: str | None = None) -> dict[str, Any]:
    if setor is None:
        return {
            "setores_registrados": list(setores_registrados()),
            "como_usar": "chame de novo passando um dos setores em setores_registrados",
            "aviso": _AVISO,
        }

    achadas = ressalvas_de(setor.strip().lower())
    if not achadas:
        return {
            "setor": setor,
            "encontrado": False,
            "setores_registrados": list(setores_registrados()),
            "observacao": (
                "Este setor não está registrado. Isso não significa que o DAS "
                "cubra toda a carga dele: significa que não há registro aqui."
            ),
            "aviso": _AVISO,
        }

    return {
        "setor": setor,
        "encontrado": True,
        "ressalvas": [
            {
                "setor": r.setor,
                "resumo": r.resumo,
                "pis_cofins_monofasico": r.monofasico,
                "icms_substituicao_tributaria": r.icms_st,
                "anexo_tipico": r.anexo_tipico.value if r.anexo_tipico else None,
                "condicoes": list(r.condicoes),
                "fundamentos": list(r.fundamentos),
            }
            for r in achadas
        ],
        "proximo_passo": (
            "Chame carga_fora_do_das informando a posição na cadeia, porque "
            "produzir e revender a mesma mercadoria monofásica têm efeitos "
            "opostos sobre a carga."
        ),
        "aviso": _AVISO,
    }


@server.tool(
    name="carga_fora_do_das",
    description=(
        "Diz o que a alíquota efetiva do anexo NÃO cobre, e em que direção "
        "cada item altera a carga. Chame esta ferramenta antes de afirmar qual "
        "é a carga tributária de alguém: a alíquota efetiva é a carga do DAS, "
        "e não a total. Dois motivos distintos fazem um tributo ficar fora. "
        "O Anexo IV não abrange a contribuição patronal, que é recolhida à "
        "parte sobre a folha e ACRESCENTA carga. Já a segregação de receita "
        "monofásica ou com ICMS-ST muda de direção conforme a posição na "
        "cadeia: para quem produz ACRESCENTA, para quem revende REDUZ. "
        "Não quantifica valores, porque isso exige a repartição do DAS por "
        "tributo. " + _AVISO
    ),
)
def carga_fora_do_das_tool(
    anexo: AnexoNome,
    receita_monofasica: bool = False,
    receita_com_icms_st: bool = False,
    posicao: Literal["produtor", "revendedor"] = "revendedor",
) -> dict[str, Any]:
    a = _anexo(anexo)
    pos = (
        PosicaoNaCadeia.PRODUTOR
        if posicao.strip().lower() == "produtor"
        else PosicaoNaCadeia.REVENDEDOR
    )

    itens = carga_fora_do_das(
        a,
        receita_monofasica=receita_monofasica,
        receita_com_icms_st=receita_com_icms_st,
        posicao=pos,
    )

    return {
        "anexo": a.value,
        "posicao_na_cadeia": pos.value,
        "tributos_no_das": list(TRIBUTOS_NO_DAS[a]),
        "fora_do_das": [
            {
                "tributo": i.tributo,
                "efeito": i.efeito.value,
                "incide_sobre": i.base,
                "motivo": i.motivo,
                "fundamentos": list(i.fundamentos),
            }
            for i in itens
        ],
        "conclusao": (
            "A alíquota efetiva do DAS representa a carga tributária deste caso."
            if not itens
            else "A alíquota efetiva do DAS NÃO representa a carga tributária "
            "deste caso: há "
            + str(len(itens))
            + " item(ns) fora dele. Itens que acrescentam e itens que reduzem "
            "não se somam num único número; relate-os separadamente."
        ),
        "nao_quantificado": (
            "Quantificar cada item exige a repartição do DAS por tributo, que "
            "não está disponível nesta versão."
        ),
        "aviso": _AVISO,
    }


def main() -> None:
    """Ponto de entrada do servidor, por stdio."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
