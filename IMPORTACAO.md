# Guia de Importação Mensal

Este painel agora trabalha com os campos **NOVEMBRO**, **DEZEMBRO** e **COBERTURA** diretamente da planilha `atualizacao.xlsx`. A seguir você encontra as boas práticas para preparar a planilha e importar os dados sem comprometer o dashboard.

## Estrutura esperada da planilha

Cada aba da planilha deve conter, no mínimo, as colunas abaixo:

| Campo obrigatório | Observações |
| ----------------- | ----------- |
| `CÓDIGO`          | Identificador único do item. |
| `FORNECEDOR`      | Nome do parceiro comercial. |
| `FAMÍLIA`         | Categoria do produto. |
| `ITEM`            | Descrição comercial. |
| `1-4`, `90-13`, `90-15` | Estoque por estabelecimento (nomenclatura exatamente igual à planilha padrão). |
| `ESTOQUE EM MESES` ou `COBERTURA` | Caso `COBERTURA` esteja presente ela passa a ser o valor prioritário para o cálculo dos meses de estoque. |
| `VENDAS 4M`       | Quantidade vendida nos últimos 4 meses. |
| `MÉDIA 3M`        | Média mensal das vendas dos últimos 3 meses. |
| `NOVEMBRO`        | Quantidade planejada para o mês de novembro. |
| `DEZEMBRO`        | Quantidade planejada para o mês de dezembro. |

> **Dica:** ao adicionar novas abas para os meses seguintes, mantenha a mesma estrutura e apenas renomeie as colunas de acordo com o novo período (ex.: `JANEIRO`, `FEVEREIRO`). O dashboard continuará importando automaticamente os campos adicionais.

## Fluxo de importação

1. Abra o dashboard e clique em **Importar planilha**.
2. Selecione o arquivo `atualizacao.xlsx` (ou outro arquivo compatível).
3. Caso a planilha possua mais de uma aba, o sistema exibirá um modal listando todas elas. Escolha a aba correspondente ao mês desejado e clique em **Importar "Nome da Aba"**.
4. O dashboard grava automaticamente os dados (incluindo NOVEMBRO, DEZEMBRO e COBERTURA), recalcula os indicadores e atualiza o cartão “Painel Mensal Importado”.

Se preferir cancelar a importação, basta fechar o modal ou clicar em **Cancelar** — nenhuma alteração será aplicada.

## Exportação e histórico

- O botão **Exportar** agora inclui as colunas `MÉDIA 3M`, `NOVEMBRO`, `DEZEMBRO` e `COBERTURA (PLANILHA)` no arquivo gerado.
- O arquivo `data.js` recebe automaticamente os novos campos e armazena metadados sobre a última importação para fins de auditoria.

## Boas práticas adicionais

- Sempre valide os valores de NOVEMBRO e DEZEMBRO na planilha antes de importar. Valores vazios são interpretados como `0`.
- Utilize a nova seção **Painel Mensal Importado** no dashboard para acompanhar o total de cada mês e a média de cobertura informada na planilha.
- Em planilhas muito grandes, recomenda-se manter apenas uma aba por mês para facilitar o processo de seleção e evitar confusões.

Seguindo estas orientações você garante que o dashboard continue estável, com dados atualizados e prontos para análise.
