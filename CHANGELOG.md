# Changelog

## 0.2.0

- `quantificar_segregacao` responde quanto se paga a mais por não segregar receita monofásica ou com ICMS-ST. Informe a receita do mês repartida por categoria e ela devolve o DAS sem segregar, o segregado, e a diferença — que é indébito recuperável para quem revende.
- `calcular_das` aceita `incluir_reparticao`, que acrescenta a divisão do DAS por tributo.
- Depende de `simples-nacional-complexo>=0.3.0`, que trouxe as tabelas de repartição.

Um bar no Anexo I com RBT12 de R$ 900 mil e R$ 60 mil mensais em cerveja paga R$ 2.410,80 a mais por mês sem segregar: 37% do próprio DAS.

## 0.1.0

Primeira versão, com quatro ferramentas: `calcular_das`, `resolver_anexo_fator_r`, `ressalvas_setoriais` e `carga_fora_do_das`.

As instruções do servidor pedem ao assistente que consulte `carga_fora_do_das` antes de afirmar qual é a carga tributária de alguém, e toda descrição de ferramenta avisa que o resultado não é assessoria fiscal.

O cálculo vem de `simples-nacional-complexo`; este pacote é só a interface.
