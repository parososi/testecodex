# Plano de Ação para Regularizar o Dashboard e Finalizar o PR

## 1. Diagnóstico Atual
- O arquivo `index.html` concentra praticamente todas as funcionalidades e já sofreu múltiplas reescritas no histórico recente. O merge pendente indica conflitos extensos exatamente nesse arquivo, portanto precisamos comparar o estado atual com o `main` remoto antes de qualquer nova alteração.
- Foram inseridos novos filtros (ex.: seletor avançado para "Sem estoque" e "> 50 meses"), tooltips e cálculos estatísticos (mediana, quartis, desvio-padrão, previsão dinâmica). Contudo, parte das regras está acoplada a estados globais (ex.: `currentEstablishment`) e pode gerar comportamentos inconsistentes quando combinações de filtros são utilizadas.
- Revisão rápida do código mostra que `productMatchesFilters` faz checagens duplicadas para o filtro avançado dependendo da seleção de estabelecimento, o que pode impedir o filtro de funcionar corretamente quando nenhum estabelecimento é escolhido. Também há risco de regressão na renderização porque o HTML cresceu muito e o CSS inline ficou repetitivo, dificultando manutenções.

## 2. Objetivos do Ajuste
1. Resolver os conflitos de `index.html`, preservando os filtros principais e o novo filtro avançado solicitado pelo usuário.
2. Garantir que a lógica de filtragem (global, por família, fornecedor, estabelecimento, previsões e filtro avançado) esteja centralizada em um único helper para evitar divergências.
3. Revisar o layout após a resolução dos conflitos para confirmar que os tooltips e cards (Resumo Geral, Análise ABC, Detalhes) continuam alinhados e responsivos.

## 3. Passos Propostos
1. **Sincronização com a base**
   - Executar `git fetch origin` e comparar `work` com `origin/main` via `git diff origin/main..work -- index.html`.
   - Identificar os blocos que divergem (filtros, cards, funções JS) e planejar um merge manual preservando as regras mais recentes.
2. **Isolar helpers antes do merge**
   - Copiar para um arquivo temporário ou bloco de notas os helpers críticos (`productMatchesFilters`, `getCoverageInfo`, `getPrediction`, `applyAllFilters`, `updateSummary`, `updateParetoAnalysis`). Isso facilitará reintroduzir a versão correta após o merge.
3. **Resolver conflitos no `index.html`**
   - Reaplicar o layout principal garantindo que o bloco de controles inclua: filtros rápidos, dropdowns de família/fornecedor/estabelecimento e o novo `#advancedStockFilter`.
   - Revalidar que `productMatchesFilters` receba o estado do filtro avançado e aplique a regra de estoque sem depender da seleção de estabelecimento. A checagem deve funcionar tanto para estoque total quanto por unidade selecionada.
   - Confirmar que `updatePredictiveAnalysis`, `updateSummary` e `updateParetoAnalysis` utilizem sempre `filteredData` já tratado pelo helper único.
4. **Ajustes finais e limpeza**
   - Eliminar estilos duplicados e garantir que os componentes de tooltip compartilhem as mesmas classes.
   - Revisar strings longas (previsão de ruptura) para que fiquem apenas nos tooltips e não quebrem o layout da tabela.
   - Garantir que a função `resetAllFilters()` limpe também `advancedStockFilter` e os estados globais (`predictionFilter`, `selectedFamily`, etc.).

## 4. Validação e Testes
- Abrir o `index.html` no navegador e validar manualmente:
  - Pesquisa global + filtro avançado “Sem estoque”.
  - Filtro rápido “Estoque Crítico” combinado com avançado “> 50 meses”.
  - Seleção por família e estabelecimento verificando a atualização dos cards, gauges e análise ABC.
  - Tooltips sobre “Resumo Geral”, “Análise ABC por Vendas”, colunas da tabela e previsão nos detalhes.
- Revisar o console do navegador para garantir ausência de erros JS.
- Gerar uma exportação (caso disponível) para conferir se o texto resumido da previsão permanece consistente.

## 5. Critérios de Aceite
- `git status` limpo após as correções e merge sem conflitos.
- Filtros originais + filtro avançado funcionando em todas as combinações sem travar a tabela.
- Layout íntegro (sem quebras visuais) e tooltips acessíveis.
- Contadores de análise preditiva, resumo e ABC refletindo o conjunto filtrado atual.
