import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re

# ==============================================================================
# 1. CONFIGURAÇÃO VISUAL
# ==============================================================================
st.set_page_config(page_title="Cálculo PC/AL", page_icon="⚖️", layout="wide")

st.markdown("""
<style>
.metric-card {
    background-color: #fff;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
    border-left: 5px solid #3498db;
}
.metric-value {
    font-size: 24px;
    font-weight: bold;
    color: #2c3e50;
}
.metric-label {
    font-size: 14px;
    color: #7f8c8d;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.total-card {
    background-color: #d4efdf;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
    border-left: 5px solid #27ae60;
}
.total-value {
    font-size: 32px;
    font-weight: bold;
    color: #27ae60;
}
div.stButton > button {
    font-size: 18px !important;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. FUNÇÕES AUXILIARES
# ==============================================================================

def limpar_valor(txt):
    if isinstance(txt, (int, float)):
        return float(txt)
    if not txt:
        return 0.0
    t = str(txt).replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(t)
    except:
        return 0.0

def extrair_numeros_linha(linha):
    numeros = re.findall(r"\d+\.\d{2}|\d+,\d{2}|\d+", linha)
    return [limpar_valor(n) for n in numeros if limpar_valor(n) > 1200]

def ler_financeiro_universal(file):
    linhas = []
    if file.name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    linhas += text.splitlines()
    else:
        return pd.DataFrame()

    ano_atual = None
    dados = []

    for linha in linhas:
        up = linha.upper()
        if not ano_atual:
            m = re.search(r"(20\d{2})", up)
            if m:
                ano = int(m.group(1))
                if 2000 < ano < 2040:
                    ano_atual = ano

        if "SUBSÍDIO" in up or "SUBSIDIO" in up:
            if "ALIMENT" in up or "TRANSP" in up:
                continue
            nums = extrair_numeros_linha(linha)
            for i, v in enumerate(nums[:12]):
                dados.append({
                    "Data": pd.to_datetime(f"{ano_atual}-{i+1:02d}-01"),
                    "Valor_Pago": v
                })

    if dados:
        df = pd.DataFrame(dados).groupby("Data").max().reset_index()
        return df.sort_values("Data")
    return pd.DataFrame()

def ler_cadastral(arquivos):
    historico = []
    regex_codigo = r'(PCE[A-G]|AGPMNE[1-9]?[A-G]40|AGPMNJ[1-9]?[A-G]40|NV\d{5}-AGPMN[A-Z][1-9]?[A-G]40)'

    for arq in arquivos:
        try:
            reader = PdfReader(arq)
            for page in reader.pages:
                txt = page.extract_text()
                if not txt:
                    continue
                datas = re.findall(r'Data Promo[çc][ãa]o\s*(\d{2}/\d{2}/\d{4})', txt)
                if not datas:
                    datas = re.findall(r'(\d{2}/\d{2}/\d{4})', txt)
                codigos = re.findall(regex_codigo, txt.upper())

                for i in range(min(len(datas), len(codigos))):
                    data_str = datas[i]
                    cod = codigos[i].upper()
                    classe = None
                    m1 = re.search(r'PCE([A-G])', cod)
                    m2 = re.search(r'AGPMN[A-Z]\d*([A-G])40', cod)
                    if m1:
                        classe = m1.group(1)
                    elif m2:
                        classe = m2.group(1)

                    if classe:
                        historico.append({
                            'Data_Mudanca': pd.to_datetime(data_str, dayfirst=True),
                            'Classe': classe
                        })
        except:
            pass

    if historico:
        df = pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')
        return df

    return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])

def calcular(fin, cad, base):
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df = pd.merge_asof(fin, cad, left_on="Data", right_on="Data_Mudanca", direction="backward")
    df["Indice"] = df["Classe"].map(mapa).fillna(0)
    df["Valor_Devido"] = base * (1.15 ** df["Indice"])
    df["Diferenca"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Diferenca_Final"] = df["Diferenca"].apply(lambda x: x if x > 0 else 0)
    return df

def fmt_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==============================================================================
# 3. INTERFACE STREAMLIT
# ==============================================================================
st.sidebar.title("Configurações")
file_fin = st.sidebar.file_uploader("Ficha Financeira (PDF)", type=["pdf"])
file_car = st.sidebar.file_uploader("Fichas Cadastrais (PDF)", type=["pdf"], accept_multiple_files=True)
base = st.sidebar.number_input("Valor Base Classe A", value=4000.00)
nome = st.sidebar.text_input("Nome do Servidor", "Ironildo da Silva Costa")
matricula = st.sidebar.text_input("Matrícula", "0065998-3")

col1, col2 = st.columns([1, 1])
executar = col1.button("🚀 Executar Cálculo")
limpar = col2.button("🗑️ Limpar Tudo")

if limpar:
    st.session_state.clear()
    st.experimental_rerun()

st.title("⚖️ Sistema de Cálculo Jurídico (PC/AL)")
st.markdown("Automação de cálculo de diferenças salariais por classe funcional.")

if executar:
    if not file_fin or not file_car:
        st.error("⚠️ Você precisa enviar a Ficha Financeira e pelo menos uma Ficha Cadastral.")
    else:
        df_fin = ler_financeiro_universal(file_fin)
        df_car = ler_cadastral(file_car)

        if df_fin.empty:
            st.error("❌ Ficha Financeira inválida: verifique se há valores de subsídio e ano.")
        elif df_car.empty:
            st.error("❌ Nenhuma promoção válida encontrada na ficha cadastral.")
        else:
            df = calcular(df_fin, df_car, base)
            total = df["Diferenca_Final"].sum()
            classe = df["Classe"].iloc[-1]

            st.success(f"✅ Cálculo concluído. Total devido: R$ {fmt_br(total)} | Classe atual: {classe}")
            st.dataframe(df)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['Data'], y=df['Valor_Pago'], name='Pago', line=dict(color='red')))
            fig.add_trace(go.Scatter(x=df['Data'], y=df['Valor_Devido'], name='Devido', line=dict(color='green')))
            fig.update_layout(title="Comparativo de Valores", xaxis_title="Data", yaxis_title="Valor")
            st.plotly_chart(fig, use_container_width=True)
