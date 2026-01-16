# 📊 Sistema de Cálculo PC/AL - Promoções Manuais

Este sistema realiza o cálculo automático de diferenças salariais entre valores pagos e valores devidos com base na progressão funcional (classe A até G), focado em servidores públicos do Estado de Alagoas.

---

## ✅ Funcionalidades

- Upload de múltiplas Fichas Financeiras (PDF) — uma por ano
- Leitura estruturada de Subsídio, Adicional de Férias e 13º Salário
- Entrada manual das promoções (mês/ano + classe)
- Cálculo automático com reajuste de 15% por classe
- Exportação para PDF Laudo Técnico e TXT compatível com o Projefweb

---

## 🛠️ Tecnologias utilizadas

- `Streamlit` — Interface web
- `pdfplumber` — Leitura estruturada de PDFs
- `pandas` — Processamento de dados
- `fpdf` — Geração de PDF laudo

---

## 🚀 Como executar

### 1. Instale as dependências

```bash
pip install -r requirements.txt
```

### 2. Execute o app

```bash
streamlit run app_promocao_manual.py
```

---

## ✍️ Formato de entrada para promoções

Você deve informar manualmente as datas de promoção no seguinte formato:

```
01/2016 - E
04/2020 - F
04/2025 - G
```

Cada linha representa uma promoção. A classe passa a valer a partir do mês informado.

---

## 📂 Estrutura recomendada

- `/app_promocao_manual.py`
- `/requirements.txt`
- `/README.md`

---

## 📬 Contato

Desenvolvido para uso jurídico e pericial.
