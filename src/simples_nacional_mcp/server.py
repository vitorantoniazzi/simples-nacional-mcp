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
    Competencia,
    PosicaoNaCadeia,
    Tributo,
    aliquota_efetiva,
    anexo_por_fator_r,
    carga_fora_do_das,
    comparar_anexos,
    das_com_segregacao,
    das_devido,
    das_por_tributo,
    fator_r,
    indebito_por_segregacao,
    percentual_segregavel,
    reparticao_da_faixa,
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


def _reais(valor: Decimal) -> str:
    """Formata dinheiro sempre com dois decimais.

    Um consumidor da API não deve receber "0" numa chamada e "0.00" na
    seguinte para o mesmo campo.
    """
    return str(valor.quantize(Decimal("0.01")))


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
    incluir_reparticao: bool = False,
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
    receita = _dinheiro(receita_do_mes, "receita_do_mes")
    das = das_devido(receita, ap)

    extra: dict[str, Any] = {}
    if incluir_reparticao:
        extra["das_por_tributo"] = {
            t.value: str(v) for t, v in das_por_tributo(receita, ap).items()
        }
        extra["reparticao_da_faixa_pct"] = {
            t.value: str(v) for t, v in reparticao_da_faixa(a, ap.faixa.numero).items()
        }

    return {
        **extra,
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


@server.tool(
    description=(
        "Quantifica o efeito da segregação de receitas no DAS. Receita "
        "monofásica de PIS/COFINS (bebidas, medicamentos, cosméticos, "
        "autopeças, combustíveis) e receita com ICMS já retido por "
        "substituição tributária devem ser segregadas: os percentuais dos "
        "tributos já cobrados na cadeia são desconsiderados no cálculo. "
        "Informe a receita do mês repartida entre as categorias e a "
        "ferramenta devolve o DAS sem segregar, o DAS segregado, e a "
        "diferença — que é o valor pago a mais por quem não segrega, e é "
        "recuperável. Use para quem REVENDE mercadoria já tributada na "
        "origem; quem produz é o responsável pelo recolhimento concentrado e "
        "tem carga acima da alíquota, não abaixo. " + _AVISO
    )
)
def quantificar_segregacao(
    anexo: AnexoNome,
    rbt12: float | int | str,
    receita_sem_regime_especial: float | int | str = 0,
    receita_monofasica: float | int | str = 0,
    receita_com_icms_st: float | int | str = 0,
    receita_monofasica_e_com_icms_st: float | int | str = 0,
) -> dict[str, Any]:
    a = _anexo(anexo)
    base = _dinheiro(rbt12, "rbt12")
    ap = aliquota_efetiva(base, a)

    baldes = [
        ("sem_regime_especial", receita_sem_regime_especial, False, False),
        ("monofasica", receita_monofasica, True, False),
        ("com_icms_st", receita_com_icms_st, False, True),
        ("monofasica_e_com_icms_st", receita_monofasica_e_com_icms_st, True, True),
    ]

    cem = Decimal("100")
    detalhe = []
    total_sem = total_com = Decimal("0")
    for nome, valor, mono, st in baldes:
        receita = _dinheiro(valor, nome)
        if receita < 0:
            raise ValueError(f"{nome} não pode ser negativa: {receita}")
        if receita == 0:
            continue
        sem = (receita * ap.aliquota_efetiva / cem).quantize(Decimal("0.01"))
        com = das_com_segregacao(receita, a, base, monofasica=mono, com_icms_st=st)
        fora = percentual_segregavel(a, ap.faixa.numero, monofasica=mono, com_icms_st=st)
        total_sem += sem
        total_com += com
        detalhe.append(
            {
                "categoria": nome,
                "receita": str(receita),
                "percentual_desconsiderado": str(fora),
                "das_sem_segregar": _reais(sem),
                "das_segregado": _reais(com),
                "economia": _reais(sem - com),
            }
        )

    if not detalhe:
        raise ValueError("informe ao menos uma das categorias de receita com valor maior que zero.")

    pesos = reparticao_da_faixa(a, ap.faixa.numero)
    icms_ausente = Tributo.ICMS not in pesos and (
        _dinheiro(receita_com_icms_st, "x") > 0
        or _dinheiro(receita_monofasica_e_com_icms_st, "x") > 0
    )

    return {
        "anexo": a.value,
        "faixa": ap.faixa.numero,
        "aliquota_efetiva_pct": str(ap.aliquota_arredondada),
        "reparticao_da_faixa_pct": {t.value: str(v) for t, v in pesos.items()},
        "por_categoria": detalhe,
        "das_sem_segregar": _reais(total_sem),
        "das_segregado": _reais(total_com),
        "pago_a_mais_por_nao_segregar": _reais(total_sem - total_com),
        "observacao": (
            "Acima do sublimite o ICMS já não integra o DAS, então segregar "
            "receita com ICMS-ST não altera nada nesta faixa."
            if icms_ausente
            else "A diferença é o indébito de quem revende sem segregar. "
            "Recuperá-lo depende de prazo prescricional e de escrituração; "
            "confirme com contador."
        ),
        "aviso": _AVISO,
    }


@server.tool(
    name="comparar_anexos",
    description=(
        "Compara os cinco anexos por CARGA TOTAL, não por alíquota do DAS. "
        "Informe a folha mensal: ela só altera o Anexo IV, único cujo DAS não "
        "abrange a contribuição patronal, recolhida à parte a 20% sobre a "
        "folha mais o RAT do grau de risco (1% a 3%, ajustável pelo FAP). "
        "Sem a folha, a comparação reproduz a ilusão de que o Anexo IV é o "
        "mais barato. Use esta ferramenta, e não calcular_das repetido, "
        "sempre que a pergunta for qual anexo custa menos. "
        "O anexo aplicável depende da atividade e não é escolha livre: isto "
        "compara custos, não define enquadramento. " + _AVISO
    ),
)
def comparar_anexos_tool(
    rbt12: float | int | str,
    receita_do_mes: float | int | str,
    folha: float | int | str = 0,
    rat_pct: float | int | str = 1,
    fap: float | int | str = 1,
) -> dict[str, Any]:
    receita = _dinheiro(receita_do_mes, "receita_do_mes")
    linhas = comparar_anexos(
        _dinheiro(rbt12, "rbt12"),
        receita,
        folha=_dinheiro(folha, "folha"),
        rat_pct=Decimal(str(rat_pct)),
        fap=Decimal(str(fap)),
    )
    por_anexo = [
        {
            "anexo": c.anexo.value,
            "anexo_descricao": c.anexo.descricao,
            "faixa": c.faixa,
            "aliquota_efetiva_pct": str(c.aliquota_efetiva_pct),
            "das": str(c.das),
            "cpp_fora_do_das": str(c.cpp_fora_do_das),
            "carga_total": str(c.carga_total),
            "carga_pct_da_receita": str(c.carga_pct_da_receita(receita)),
        }
        for c in linhas
    ]
    iii = next(c for c in linhas if c.anexo is Anexo.III)
    iv = next(c for c in linhas if c.anexo is Anexo.IV)
    inverteu = iv.das < iii.das and iv.carga_total > iii.carga_total
    return {
        "por_anexo": por_anexo,
        "folha_informada": str(_dinheiro(folha, "folha")),
        "alerta_anexo_iv": (
            "Pela alíquota do DAS o Anexo IV parece mais barato que o Anexo III, "
            "e pela carga total é mais caro. A diferença é a contribuição "
            "patronal, que no Anexo IV fica fora do DAS."
            if inverteu
            else "Sem folha informada não há CPP a somar, e a comparação sai "
            "pela alíquota do DAS apenas — o que subestima o Anexo IV."
            if _dinheiro(folha, "folha") == 0
            else "Nesta combinação de receita e folha a ordem por carga total "
            "coincide com a ordem por alíquota."
        ),
        "aviso": _AVISO,
    }


@server.tool(
    description=(
        "Soma o indébito de vários meses de quem revendeu sem segregar receita "
        "monofásica ou com ICMS-ST, e separa o que ainda está no prazo de cinco "
        "anos do art. 168 do CTN do que já prescreveu. Passe uma lista de "
        "competências, cada uma com ano, mes, rbt12 e a receita repartida por "
        "categoria. A contagem do prazo usa o vencimento do DAS, dia 20 do mês "
        "seguinte, como referência do pagamento; quem pagou em atraso conta da "
        "data efetiva, que só o contribuinte conhece. Pedido administrativo não "
        "interrompe o prazo. " + _AVISO
    )
)
def indebito_acumulado(
    anexo: AnexoNome,
    competencias: list[dict[str, Any]],
) -> dict[str, Any]:
    if not competencias:
        raise ValueError("informe ao menos uma competência.")
    a = _anexo(anexo)
    itens = []
    for i, c in enumerate(competencias):
        faltando = {"ano", "mes", "rbt12"} - set(c)
        if faltando:
            raise ValueError(f"competência {i} sem os campos obrigatórios: {sorted(faltando)}")
        itens.append(
            Competencia(
                ano=int(c["ano"]),
                mes=int(c["mes"]),
                rbt12=_dinheiro(c["rbt12"], "rbt12"),
                receita_sem_regime_especial=_dinheiro(
                    c.get("receita_sem_regime_especial", 0), "receita_sem_regime_especial"
                ),
                receita_monofasica=_dinheiro(c.get("receita_monofasica", 0), "receita_monofasica"),
                receita_com_icms_st=_dinheiro(
                    c.get("receita_com_icms_st", 0), "receita_com_icms_st"
                ),
                receita_monofasica_e_com_icms_st=_dinheiro(
                    c.get("receita_monofasica_e_com_icms_st", 0),
                    "receita_monofasica_e_com_icms_st",
                ),
            )
        )

    r = indebito_por_segregacao(itens, a)
    return {
        "anexo": a.value,
        "data_de_corte": r.data_de_corte.isoformat(),
        "competencias": [
            {
                "ano": c.competencia.ano,
                "mes": c.competencia.mes,
                "vencimento": c.competencia.vencimento.isoformat(),
                "faixa": c.faixa,
                "das_sem_segregar": _reais(c.das_sem_segregar),
                "das_segregado": _reais(c.das_segregado),
                "indebito": _reais(c.indebito),
                "prescrito": c.prescrito,
            }
            for c in r.competencias
        ],
        "recuperavel": _reais(r.recuperavel),
        "prescrito": _reais(r.prescrito),
        "total": _reais(r.total),
        "observacao": (
            "Recuperar depende de escrituração que comprove a segregação devida "
            "e de via adequada (restituição ou compensação). O valor prescrito "
            "consta apenas para dimensionar o que se perdeu."
        ),
        "aviso": _AVISO,
    }


def main() -> None:
    """Ponto de entrada do servidor, por stdio."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
