# 🧮 Sistema de Cálculo PC/AL (Streamlit Cloud)

Sistema automatizado para calcular diferenças salariais por evolução de classe com base em:

- 📄 Ficha Financeira (PDF)
- 📂 Fichas Cadastrais (PDFs)

## ✅ Funcionalidades

- Leitura automatizada de valores mensais pagos
- Detecção de promoções (Classe A → G)
- Cálculo de valores devidos com base no reajuste de 15% por classe
- Considera adicional de férias (1/3) e 13º salário
- Geração de arquivo `.txt` no padrão **Projefweb**

## 🚀 Como usar no Streamlit Cloud

1. Crie um repositório no GitHub com os arquivos:

   - `app.py`
   - `requirements.txt`
   - `README.md`

2. Acesse [https://streamlit.io/cloud](https://streamlit.io/cloud)

3. Conecte seu GitHub e selecione o repositório

4. Clique em **Deploy**

5. Faça upload dos arquivos necessários e clique em **Executar Cálculo**

## 🛠️ Requisitos Locais

Se quiser rodar localmente:

```bash
pip install -r requirements.txt
streamlit run app.py
