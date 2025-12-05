# 📊 Dashboard de Estoque com Análise Preditiva - Borracha

Um dashboard web interativo para análise de estoque com capacidades preditivas, desenvolvido para gestão de produtos de borracha da Usiquímica do Brasil (prazo limitado). A ferramenta automatiza a análise de níveis de estoque, identifica produtos críticos e oferece previsões de ruptura de estoque. Foi pensado para uso rápido em ambiente local (sem backend), permitindo que a equipe visualize dados atualizados, gere alertas e exporte relatórios sem depender de instalação complexa. Abaixo você encontra as funcionalidades incluídas, para que servem e um passo a passo direto de uso.

## 📋 Índice

- [Sobre o Projeto](#sobre-o-projeto)
- [Funcionalidades](#funcionalidades)
- [Tecnologias Utilizadas](#tecnologias-utilizadas)
- [Como Usar](#como-usar)
- [Para que Serve](#para-que-serve)
- [Estrutura de Análise](#estrutura-de-análise)
- [Limitações](#limitações)
- [Créditos](#créditos)
- [Licença](#licença)

## 🎯 Sobre o Projeto

Este dashboard foi desenvolvido para automatizar e otimizar o controle de estoque de produtos de borracha, eliminando análises manuais demoradas e fornecendo insights preditivos em tempo real. A ferramenta processa dados de múltiplos estabelecimentos e fornece alertas automáticos sobre produtos em situação crítica.

## ✨ Funcionalidades

### 📊 Análise de Estoque
- **Análise Multi-Estabelecimento**: Consolida os estabelecimentos 1-4, 90-13 e 90-15 para enxergar rapidamente onde cada item está disponível.
- **Análise Preditiva**: Antecipação de produtos que podem zerar em 30 e 60 dias para planejar reposição sem surpresas.
- **Classificação Automática**: Categoriza produtos como críticos (<2 meses), baixo estoque (2-6 meses) ou slow moving (>6 meses) para priorizar ações.
- **Métricas Consolidadas**: Visão geral com totais, médias e indicadores críticos para decisões rápidas.

### 🎮 Interface Interativa
- **Gauges Animados**: Visualização por família de produtos com animações fluidas, facilitando a leitura do status geral.
- **Filtros Dinâmicos**: Busca por código, nome, fornecedor ou família para achar itens específicos em poucos cliques.
- **Dashboard Responsivo**: Interface adaptada para desktop e mobile, mantendo o controle em qualquer dispositivo.
- **Alertas Visuais**: Códigos de cores para identificação rápida de status, evitando depender de análises demoradas.

### 📄 Importação e Exportação
- **Importação Flexível**: Suporte para Excel (.xlsx, .xls) e CSV para aproveitar planilhas já usadas pela equipe.
- **Mapeamento Inteligente**: Detecção automática de colunas com debug visual, reduzindo erros na leitura dos dados.
- **Exportação Completa**: Relatórios em Excel ou CSV com dados filtrados para compartilhar rapidamente com outras áreas.
- **Compartilhamento**: Sistema de arquivos para distribuição de dados atualizados sem depender de e-mail ou servidores.

### 🔧 Funcionalidades Avançadas
- **Modo Offline**: Funciona completamente sem servidor, ideal para uso local em equipes restritas.
- **Salvamento Automático**: File System API para salvar dados automaticamente quando suportado pelo navegador.
- **Debug Avançado**: Sistema completo de diagnóstico e mapeamento de colunas para validar a leitura das planilhas.
- **Histórico de Dados**: Backup automático no localStorage, permitindo retomar o trabalho sem reenviar arquivos.

## 🛠 Tecnologias Utilizadas

- **HTML5**: Estrutura semântica moderna
- **CSS3**: Estilização avançada com animações e responsividade
- **JavaScript ES6+**: Lógica de negócio e manipulação de dados
- **Canvas API**: Gauges animados personalizados
- **SheetJS (XLSX)**: Processamento de planilhas Excel
- **File System Access API**: Salvamento automático de arquivos
- **Local Storage**: Backup de dados do navegador

## 🧭 Para que Serve

O dashboard centraliza o acompanhamento de estoque de produtos de borracha, ajudando a:

- Priorizar reposição de itens críticos antes da ruptura
- Visualizar o desempenho por família, fornecedor e estabelecimento
- Padronizar a análise com classificação automática e alertas visuais
- Exportar relatórios filtrados para equipes operacionais ou gerenciais

## 🚀 Como Usar

### 1. Preparação dos Dados
Certifique-se de que sua planilha contenha as colunas:
- **CÓDIGO**: Código do produto
- **FORNECEDOR**: Nome do fornecedor
- **FAMÍLIA**: Categoria do produto
- **ITEM**: Descrição do produto
- **1-4**: Estoque Guarulhos
- **90-13**: Estoque Itajaí
- **90-15**: Estoque Garuva
- **ESTOQUE EM MESES**: Quantidade em meses
- **VENDAS 3M**: Vendas dos últimos 3 meses
- **MÉDIA 3M**: Uma média comparada com as últimas vendas dos 3 meses anteriores

### 2. Importação de Dados
- Clique na seção "📊 Importar Dados da Planilha"
- Selecione seu arquivo Excel ou CSV
- Aguarde o processamento automático
- Verifique o mapeamento de colunas se necessário

### 3. Análise e Filtros
- Use a **busca global** para encontrar produtos específicos
- **Filtros rápidos**: Todos, Crítico, Baixo, Slow Moving
- **Filtros avançados**: Por família, fornecedor ou estabelecimento
- **Análise preditiva**: Clique nos alertas para filtrar produtos críticos

### 4. Visualização e Relatórios
- **Gauges por família**: Clique nos gráficos para filtrar
- **Tabela detalhada**: Dados completos com status visual
- **Exportação**: Gere relatórios Excel/CSV dos dados filtrados

### 5. Fluxo Rápido de Uso
- Baixe o repositório ou faça o download dos arquivos HTML/CSS/JS.
- Abra o arquivo `index.html` diretamente no navegador (funciona offline).
- Importe a planilha e use os filtros para encontrar itens críticos.
- Exporte um CSV/Excel filtrado para compartilhar com sua equipe.

## 📐 Estrutura de Análise

### Classificação de Estoque
```
Crítico: < 2 meses de estoque
Atenção: 2-6 meses de estoque  
Bom: > 6 meses de estoque
```

### Análise Preditiva
```
Zerarão em 30 dias: 0-1 mês de estoque
Zerarão em 60 dias: 1-2 meses de estoque
Ponto de reposição ideal: 3-4 meses
```

### Métricas Calculadas
- **Estoque Total**: Soma de todos os estabelecimentos
- **Média de Estoque**: Tempo médio em meses por família
- **Produtos Críticos**: Contagem automática por categoria
- **Previsão de Ruptura**: Algoritmo baseado em vendas 4M

## ⚠️ Limitações

### Importante - Dados e Precisão
Este dashboard processa dados fornecidos, mas a precisão depende de:

- **Qualidade dos Dados**: Planilhas com colunas corretamente nomeadas
- **Atualização Regular**: Dados desatualizados afetam previsões
- **Variações Sazonais**: Algoritmo não considera sazonalidade
- **Novos Produtos**: Produtos sem histórico podem gerar alertas falsos
- **Mapeamento Manual**: Colunas mal nomeadas podem ser mapeadas incorretamente

### Funcionalidades do Navegador
- **File System API**: Salvamento automático apenas em Chrome/Edge + HTTPS
- **LocalStorage**: Backup local limitado por navegador
- **Responsive Design**: Melhor experiência em telas maiores

### Uso Recomendado
- ✅ Análise rápida e identificação de tendências
- ✅ Alertas automáticos para gestão proativa
- ✅ Relatórios executivos e operacionais
- ⚠️ Sempre validar dados críticos com sistemas oficiais

## 👨‍💻 Créditos

**Desenvolvido por:** Paulo Roberto S. S. ([@Parososi](https://github.com/parososi))

### Agradecimentos
- **Usiquímica do Brasil**: Por fornecer requisitos e dados de teste
- **Comunidade Open Source**: Pelas bibliotecas SheetJS, Chart.js e outras

### Bibliotecas Utilizadas
- **SheetJS**: Processamento de planilhas Excel
- **File System Access API**: Salvamento automático
- **Canvas API**: Gráficos e gauges personalizados

## 📄 Licença

Este projeto está sob a licença CC BY-NC-ND 4.0 (Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International). Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

### Resumo da Licença
- ✅ **Usar**: Para fins não comerciais
- ✅ **Compartilhar**: Com atribuição ao autor
- ❌ **Modificar**: Não são permitidas obras derivadas
- ❌ **Comercializar**: Não é permitido uso comercial
