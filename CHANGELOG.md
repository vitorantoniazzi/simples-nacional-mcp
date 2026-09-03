# Changelog

## 0.3.0

Duas ferramentas novas, e a aritmética saiu daqui.

- **`comparar_anexos`** põe os cinco anexos lado a lado por **carga total**, não por alíquota do DAS. Informando a folha, o Anexo IV deixa de parecer barato: para RBT12 de R$ 1 mi, receita de R$ 80 mil e folha de R$ 30 mil, ele mostra 10,02% de alíquota contra 12,44% do Anexo III e carga de 17,90% contra 12,44%. A ferramenta alerta quando a ordem se inverte, e avisa quando a folha não foi informada.
- **`indebito_acumulado`** soma o indébito de várias competências e separa o que está no prazo de cinco anos do art. 168 do CTN do que prescreveu. Vinte meses do bar do exemplo: R$ 48.216,00 recuperáveis.
- `quantificar_segregacao` passou a chamar a biblioteca em vez de recalcular. A matemática pertence ao pacote de cálculo; aqui é interface.
- Valores em reais agora saem sempre com dois decimais. Antes um campo podia devolver `"0"` numa chamada e `"0.00"` na seguinte.

Depende de `simples-nacional-complexo>=0.4.0`.

## 0.2.0

- `quantificar_segregacao` responde quanto se paga a mais por não segregar receita monofásica ou com ICMS-ST. Informe a receita do mês repartida por categoria e ela devolve o DAS sem segregar, o segregado, e a diferença — que é indébito recuperável para quem revende.
- `calcular_das` aceita `incluir_reparticao`, que acrescenta a divisão do DAS por tributo.
- Depende de `simples-nacional-complexo>=0.3.0`, que trouxe as tabelas de repartição.

Um bar no Anexo I com RBT12 de R$ 900 mil e R$ 60 mil mensais em cerveja paga R$ 2.410,80 a mais por mês sem segregar: 37% do próprio DAS.

## 0.1.0

Primeira versão, com quatro ferramentas: `calcular_das`, `resolver_anexo_fator_r`, `ressalvas_setoriais` e `carga_fora_do_das`.

As instruções do servidor pedem ao assistente que consulte `carga_fora_do_das` antes de afirmar qual é a carga tributária de alguém, e toda descrição de ferramenta avisa que o resultado não é assessoria fiscal.

O cálculo vem de `simples-nacional-complexo`; este pacote é só a interface.
