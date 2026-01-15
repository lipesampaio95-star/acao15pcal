import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re

# ==============================================================================
# 1. CONFIGURAÇÃO VISUAL (CSS)
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
div.stButton > button:first-child {
    background-color: #2980b9;
    color: white;
    font-size: 18px;
    border-radius: 8px;
    width: 100%;
    padding: 10px 0;
}
div.stButton > button:first-child:hover {
    background-color: #1a5276;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. FUNÇÕES DE EXTRAÇÃO
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
    for arq in arquivos:
        reader = PdfReader(arq)
        for page in reader.pages:
            txt = page.extract_text()
            datas = re.findall(r"(\d{2}/\d{2}/\d{4})", txt)
            codigos = re.findall(r"AGPMNJ[ABCDEFG]40", txt.upper())
            if datas and codigos:
                historico.append({
                    "Data_Mudanca": pd.to_datetime(datas[0], dayfirst=True),
                    "Classe": codigos[0][-3]
                })
    if historico:
        df = pd.DataFrame(historico).drop_duplicates().sort_values("Data_Mudanca")
        return df
    return pd.DataFrame(columns=["Data_Mudanca", "Classe"])

def calcular(fin, cad, base):
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df = pd.merge_asof(fin, cad, left_on="Data", right_on="Data_Mudanca", direction="backward")
    df["Indice"] = df["Classe"].map(mapa).fillna(0)
    df["Valor_Devido"] = base * (1.15 ** df["Indice"])
    df["Diferenca"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Diferenca_Final"] = df["Diferenca"].apply(lambda x: x if x > 0 else 0)
    return df

# ==============================================================================
# 3. UTILITÁRIOS
# ==============================================================================
def fmt_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class PDF(FPDF):
    def header(self):
        self.set_font('Arial','B',14)
        self.cell(0,10,'Relatório de Cálculo PC/AL',0,1,'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial','I',8)
        self.cell(0,10,f'Pág {self.page_no()}',0,0,'C')

def gerar_pdf(df, nome, mat, total):
    p = PDF(); p.add_page(); p.set_font('Arial','',10)
    p.cell(0,6,f"Servidor: {nome} | Matrícula: {mat}",0,1); p.ln()
    p.set_fill_color(220,255,220); p.set_font('Arial','B',12)
    p.cell(0,10,f"TOTAL: R$ {fmt_br(total)}",1,1,'C',1); p.ln()
    p.set_font('Arial','B',9)
    for _,r in df.iterrows():
        p.set_font('Arial','B',9 if r['Diferenca_Final']>0 else 'Arial')
        p.cell(30,6,r['Data'].strftime('%m/%Y'),1,0,'C')
        p.cell(20,6,str(r['Classe']),1,0,'C')
        p.cell(35,6,fmt_br(r['Valor_Pago']),1,0,'R')
        p.cell(35,6,fmt_br(r['Valor_Devido']),1,0,'R')
        p.cell(35,6,fmt_br(r['Diferenca_Final']),1,0,'R')
        p.ln()
    return p.output(dest='S').encode('latin-1','ignore')

# ==============================================================================
# 4. INTERFACE STREAMLIT
# ==============================================================================
st.sidebar.title("Configurações")
file_fin = st.sidebar.file_uploader("Ficha Financeira", type=["pdf"])
file_car = st.sidebar.file_uploader("Fichas Cadastrais", type=["pdf"], accept_multiple_files=True)

base = st.sidebar.number_input("Valor Base Classe A", value=4000.00)
nome = st.sidebar.text_input("Nome do Servidor", "Ironildo da Silva Costa")
matricula = st.sidebar.text_input("Matrícula", "0065998-3")

st.title("⚖️ Sistema de Cálculo Jurídico (PC/AL)")
st.markdown("Cálculo automatizado de diferenças de classe com base em promoção.")

if file_fin and file_car:
    df_fin = ler_financeiro_universal(file_fin)
    df_car = ler_cadastral(file_car)

    if df_fin.empty:
        st.error("❌ Ficha Financeira vazia ou ilegível (Não achou 'Subsídio' > R$1200 ou ano).")
    elif df_car.empty:
        st.error("❌ Nenhuma promoção identificada na ficha cadastral.")
    else:
        df = calcular(df_fin, df_car, base)
        total = df['Diferenca_Final'].sum()
        classe = df['Classe'].iloc[-1]
        st.success(f"✅ Cálculo finalizado: Total = R$ {fmt_br(total)} | Classe Atual = {classe}")

        st.dataframe(df.style.format({
            "Valor_Pago": "R$ {:,.2f}",
            "Valor_Devido": "R$ {:,.2f}",
            "Diferenca_Final": "R$ {:,.2f}"
        }))

        pdf_bytes = gerar_pdf(df, nome, matricula, total)
        st.download_button("📄 Baixar Relatório PDF", pdf_bytes, f"{nome}_laudo.pdf", "application/pdf")
else:
    st.info("⬅️ Faça o upload da ficha financeira e fichas cadastrais para iniciar.")
