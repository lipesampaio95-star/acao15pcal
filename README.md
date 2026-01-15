# ⚖️ Sistema de Cálculo PC/AL - Versão Cronológica por Promoção

Este sistema permite calcular automaticamente diferenças remuneratórias de servidores públicos com base na **progressão funcional** (promoções por classe) conforme fichas **financeiras** e **cadastrais** em formato PDF.

---

## ✅ Funcionalidades

- 📂 Leitura de ficha financeira (valores pagos por mês).
- 🧾 Leitura da ficha cadastral (datas de promoção e classe).
- 📅 Identificação correta do mês/ano em que a promoção passa a valer.
- 🧠 Cálculo do valor devido com base na classe correta mês a mês.
- 📄 Exportação em:
  - Laudo técnico PDF
  - Planilha Excel (opcional)
  - TXT no padrão do sistema **Projefweb**

---

## 📦 Como Executar

1. Instale os pacotes:

```bash
pip install -r requirements.txt
```

2. Execute com Streamlit:

```bash
streamlit run app_cronologia_promocao_mensal.py
```

---

## 📁 Uploads Esperados

- **Ficha Financeira**: PDF com colunas de meses e campo "Ano Comp".
- **Ficha Cadastral**: Um ou mais PDFs com datas de promoção e códigos como `AGPMNJ4F40`, `PCEG440`, etc.

---

## 🧮 Fórmula Aplicada

Para cada mês:

```
Valor Devido = BaseClasseA * (1.15 ^ Nível)
```

Diferença = Valor Devido - Valor Pago

---

## 📌 Observações Técnicas

- Datas como `01/11/2022` são aplicadas a partir do mês **11/2022**.
- A classe anterior se mantém até a nova promoção.
- O valor base da Classe A é configurável na interface.

---

## 👨‍⚖️ Aplicação

Sistema ideal para gerar cálculos em ações judiciais, perícias técnicas, defesas administrativas e projeções de impacto financeiro.

---
