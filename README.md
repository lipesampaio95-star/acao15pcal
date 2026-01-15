# 📊 Sistema de Cálculo de Diferenças de Classe - PC/AL

Este sistema automatiza o cálculo de diferenças remuneratórias com base em promoções por classe (15% por nível), utilizando como fonte:

- 📄 **Ficha Financeira** (PDF ou Excel)
- 🧾 **Ficha Cadastral** (PDFs com promoções e códigos de classe)

## ✅ Funcionalidades

- Leitura automática dos arquivos via OCR e parsing.
- Reconhecimento cronológico de promoções.
- Aplicação correta do fator de 15% entre classes (A até G).
- Exportação de:
  - 📄 Laudo Técnico Pericial em PDF
  - 📊 Planilha Excel formatada
  - 🧾 Arquivo .TXT compatível com Projefweb

## 🚀 Como Executar

1. Instale os requisitos:

```bash
pip install -r requirements.txt
```

2. Execute o app com Streamlit:

```bash
streamlit run app_cronologia_final.py
```

## 📂 Uploads

- Ficha Financeira: PDF, Excel (.xls, .xlsx) ou CSV.
- Ficha Cadastral: Um ou mais PDFs com histórico de promoções.

## 🛠 Tecnologias

- Python + Streamlit
- FPDF (PDF formal jurídico)
- pdfplumber + pypdf (OCR/Leitura)
- Pandas + Plotly
- XlsxWriter

## 📌 Observações

- Classe inicial é considerada "A" caso não haja dados anteriores.
- É usada a **cronologia real** dos documentos, com transições mensais.

## ⚖️ Exemplo de Aplicação

> Usado para gerar laudos técnicos de diferenças salariais de servidores públicos estaduais com base na evolução funcional.
