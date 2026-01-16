# ⚖️ Calculadora de Diferença de Classe (PC/AL)

Sistema jurídico automatizado para cálculo de diferenças remuneratórias de servidores da Polícia Civil de Alagoas (PC/AL), conforme a Lei nº 7.602/2014.

## 📋 Funcionalidades

- Leitura automática das **fichas financeiras** (1 PDF por ano).
- Registro **manual** das promoções por **classe** e **nível**.
- Cálculo completo das diferenças com base nos seguintes critérios:
  - **Progressão Horizontal (Classe)**: +15% por classe.
  - **Progressão Vertical (Nível)**: +5% por nível.
  - Consideração do **adicional de férias** (linha 133.00).
- Geração de:
  - 📄 Laudo técnico em PDF.
  - 📑 Arquivo ProjefWeb compatível (.txt).
  - 📊 Relatório Excel com todos os dados.
- Interface visual simples via **Streamlit**.

---

## 📂 Estrutura esperada dos arquivos

### Fichas Financeiras (PDF)
- Deve conter a estrutura padrão do Portal do Servidor.
- Um arquivo por **ano**.
- Informações extraídas automaticamente da tabela de **Subsídio** e **Adicional de Férias**.

### Promoções (Entrada Manual)
- Datas e classes/níveis devem ser informados via painel lateral no app.
- Exemplo:
