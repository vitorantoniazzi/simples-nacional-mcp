# simples-nacional-mcp

Servidor MCP para cálculo do Simples Nacional. Quatro ferramentas, tabelas vindas da lei, e uma que existe só para impedir a conclusão errada mais comum.

```bash
pip install simples-nacional-mcp
```

## Por que existe

Pergunte a um assistente quanto uma empresa paga de imposto no Simples e ele vai calcular a alíquota efetiva — que é a carga do **DAS**, não a carga tributária. A diferença não é sutil:

- O DAS do **Anexo IV** não abrange a contribuição patronal. São 20% sobre a folha, mais RAT, recolhidos à parte. Pela alíquota, o Anexo IV parece mais barato que o Anexo III. Não é.
- Cruzar o **sublimite** de R$ 3,6 mi *reduz* a alíquota do DAS, porque ICMS e ISS saem dele. A carga não cai; ela se reparte.
- Receita **monofásica** ou com **ICMS-ST** muda a conta em direções opostas conforme a posição na cadeia: quem produz recolhe o concentrado por fora, quem revende segrega e reduz o DAS.

A ferramenta `carga_fora_do_das` existe para que o assistente diga isso em vez de entregar um número redondo e errado.

## Ferramentas

| Ferramenta | O que responde |
| --- | --- |
| `calcular_das` | DAS do mês, alíquota efetiva, faixa, tributos no DAS, bandeiras de sublimite e de saída do regime. Aceita `rbt12`, ou `receita_acumulada` + `meses_de_atividade` para empresa com menos de treze meses |
| `resolver_anexo_fator_r` | Anexo III ou V, pelo Fator R, com a razão e a norma |
| `ressalvas_setoriais` | Setores com regime especial: bebidas alcoólicas e frias, medicamentos, cosméticos, autopeças, pneus, combustíveis |
| `carga_fora_do_das` | O que a alíquota **não** cobre, e se cada item acrescenta ou reduz |
| `quantificar_segregacao` | Quanto se paga a mais por não segregar receita monofásica ou com ICMS-ST |
| `comparar_anexos` | Os cinco anexos por **carga total**, somando a CPP que o Anexo IV deixa fora do DAS |
| `indebito_acumulado` | Indébito de várias competências, separando o que prescreveu |

## O número que ninguém calcula

Um bar no Anexo I, RBT12 de R$ 900 mil, receita mensal de R$ 80 mil sendo R$ 60 mil em cerveja:

| | |
| --- | --- |
| DAS sem segregar | R$ 6.560,00 |
| DAS segregado | R$ 4.149,20 |
| **Pago a mais** | **R$ 2.410,80/mês** |

São 37% do DAS, quase R$ 29 mil por ano, e é indébito recuperável. Cerveja é monofásica de PIS/COFINS e tem ICMS-ST, então 49% da alíquota daquela faixa corresponde a tributos já recolhidos na cadeia.

`quantificar_segregacao` calcula isso. Acima do sublimite ela avisa que segregar ICMS-ST não muda nada, porque ali o ICMS já não integra o DAS.

## A armadilha do Anexo IV, quantificada

RBT12 de R$ 1 milhão, receita mensal de R$ 80 mil, folha de R$ 30 mil:

| Anexo | Alíquota do DAS | CPP por fora | Carga total |
| --- | --- | --- | --- |
| III | 12,44% | — | **12,44%** |
| IV | **10,02%** | R$ 6.300 | **17,90%** |

`comparar_anexos` soma o que fica fora do DAS e alerta quando a ordem por carga inverte a ordem por alíquota — que é o caso acima. Sem folha informada, ela avisa que a comparação subestima o Anexo IV.

## E quanto dá para recuperar

`indebito_acumulado` recebe as competências e devolve o total, separando o que ainda cabe no prazo de cinco anos:

| | |
| --- | --- |
| 20 competências recentes | R$ 48.216,00 **recuperáveis** |
| 2 competências de 2019 | R$ 4.821,60 **prescritos** |

Prazo do art. 168 do CTN. A contagem usa o vencimento do DAS como referência do pagamento; pedido administrativo não interrompe o prazo.

## Instalação no Claude Code

```bash
claude mcp add simples-nacional -- simples-nacional-mcp
```

## Instalação no Claude Desktop

Em `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "simples-nacional": {
      "command": "simples-nacional-mcp"
    }
  }
}
```

## Exemplo

> Uma empresa de serviços com RBT12 de R$ 1 milhão e folha de R$ 250 mil: qual anexo, e quanto paga?

O assistente resolve o Fator R (25%, abaixo de 28%, portanto Anexo V), calcula o DAS, e ao ser perguntado sobre a carga chama `carga_fora_do_das` — que no Anexo V devolve lista vazia, confirmando que ali a alíquota realmente representa a carga. Trocando para uma atividade do Anexo IV, a mesma pergunta passa a devolver a CPP por fora.

## O que não faz

- **`carga_fora_do_das` não quantifica.** Ela diz o que fica fora e em que direção; para números, use `quantificar_segregacao`, que calcula sobre a repartição do DAS por tributo.
- **Não enquadra atividade.** Descobrir o anexo de um CNAE é decisão contábil.
- **Não é assessoria fiscal.** Cada descrição de ferramenta repete isso, porque um assistente repassa resultado como conselho se ninguém o avisar.

## Onde mora o cálculo

Em [simples-nacional](https://github.com/vitorantoniazzi/simples-nacional) ([PyPI](https://pypi.org/project/simples-nacional-complexo/)), com as tabelas transcritas da LC 123/2006 e testadas contra uma segunda transcrição independente. Aqui há apenas a interface: a lei não é duplicada em dois lugares.

## Licença

MIT
