import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re
import datetime

# ========== CONFIGURAÇÃO DA PÁGINA ==========
st.set_page_config(page_title="Cálculo PC/AL", page_icon="⚖️", layout="wide")

# ========== FUNÇÕES AUXILIARES ==========

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

def ler_financeiro(file):
    linhas = []
    if file.name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    linhas += txt.splitlines()
    else:
        return pd.DataFrame()

    dados = []
    ano = None
    for i, linha in enumerate(linhas):
        up = linha.upper()
        if not ano:
            m = re.search(r"(20\d{2})", up)
            if m:
                ano = int(m.group(1))
        valores = extrair_numeros_linha(linha)
        for v in valores:
            if ano:
                mes = (i % 12) + 1
                data = pd.to_datetime(f"{ano}-{mes:02d}-01")
                tipo = "Subsídio"
                if "FÉRIA" in up or v > 1.32 * 4000:
                    tipo = "Férias"
                elif "13" in up or "GRAT" in up or "NATAL" in up:
                    tipo = "13º"
                dados.append({
                    "Data": data,
                    "Valor_Pago": v,
                    "Tipo": tipo
                })
    df = pd.DataFrame(dados)
    if not df.empty:
        return df.groupby(["Data", "Tipo"]).sum().reset_index().sort_values("Data")
    return pd.DataFrame()

def ler_cadastral(arquivos):
    historico = []
    regex_codigo = r'(PCE[A-G]|AGPMNE[1-9]?[A-G]40|AGPMNJ[1-9]?[A-G]40|NV\d{5}-AGPMN[A-Z][1-9]?[A-G]40)'
    for arq in arquivos:
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
    if historico:
        return pd.DataFrame(historico).drop_duplicates().sort_values("Data_Mudanca")
    return pd.DataFrame(columns=["Data_Mudanca", "Classe"])

def calcular(fin, cad, base):
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df = pd.merge_asof(fin.sort_values("Data"), cad.sort_values("Data_Mudanca"), left_on="Data", right_on="Data_Mudanca", direction="backward")
    df["Indice"] = df["Classe"].map(mapa).fillna(0)
    df["Valor_Devido"] = base * (1.15 ** df["Indice"])
    df["Diferenca"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Diferenca_Final"] = df["Diferenca"].apply(lambda x: x if x > 0 else 0)
    return df

def gerar_txt_projefweb(df):
    s = io.StringIO()
    for _, r in df.iterrows():
        if r["Diferenca_Final"] > 0.01:
            data_fmt = r["Data"].strftime("%m-%Y")
            valor_fmt = f"R$ {r['Diferenca_Final']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            s.write(f"{data_fmt}\t{valor_fmt}\n")
    return s.getvalue().encode("utf-8")

class LaudoPDF(FPDF):
    def header(self):
        self.set_font("Times", "B", 12)
        self.cell(0, 10, "LAUDO TÉCNICO PERICIAL", 0, 1, "C")
        self.set_font("Times", "", 10)
        self.cell(0, 6, "Processo nº: 0000000-00.2023.8.02.0000", 0, 1, "L")
        self.cell(0, 6, "Autor: Ironildo da Silva Costa", 0, 1, "L")
        self.cell(0, 6, "Réu: Estado de Alagoas", 0, 1, "L")
        self.cell(0, 6, f"Matrícula: 0065998-3", 0, 1, "L")
        self.ln(2)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-20)
        self.set_font("Arial", "I", 8)
        self.cell(0, 5, f"Documento gerado eletronicamente em {datetime.date.today().strftime('%d/%m/%Y')} para fins processuais.", 0, 1, "C")
        self.cell(0, 5, f"Página {self.page_no()}", 0, 0, "C")

def gerar_pdf_juridico(df):
    pdf = LaudoPDF()
    pdf.add_page()
    pdf.set_fill_color(242, 243, 244)
    pdf.set_font("Times", "B", 11)
    pdf.cell(0, 10, "Quadro Resumo", 0, 1, "L")

    total = df["Diferenca_Final"].sum()
    pdf.set_font("Times", "B", 12)
    pdf.set_fill_color(212, 239, 223)
    pdf.cell(60, 8, "TOTAL DEVIDO", 1, 0, "L", 1)
    pdf.cell(0, 8, f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 1, 1, "R", 1)
    pdf.ln(5)

    headers = ["Mês/Ano", "Classe", "Pago", "Devido", "Diferença"]
    widths = [25, 25, 35, 35, 35]
    pdf.set_font("Times", "B", 10)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 8, h, 1, 0, "C")
    pdf.ln()

    pdf.set_font("Times", "", 10)
    for _, r in df.iterrows():
        pdf.cell(widths[0], 7, r["Data"].strftime("%m/%Y"), 1, 0, "C")
        pdf.cell(widths[1], 7, str(r["Classe"]), 1, 0, "C")
        pdf.cell(widths[2], 7, f"R$ {r['Valor_Pago']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 1, 0, "R")
        pdf.cell(widths[3], 7, f"R$ {r['Valor_Devido']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 1, 0, "R")
        pdf.cell(widths[4], 7, f"R$ {r['Diferenca_Final']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), 1, 1, "R")

    pdf.ln(10)
    pdf.cell(0, 6, "____________________________________", 0, 1, "L")
    pdf.cell(0, 6, "Assinatura do advogado/perito", 0, 1, "L")
    return pdf.output(dest="S").encode("latin-1")

# ========== INTERFACE ==========
st.sidebar.title("Configurações")
file_fin = st.sidebar.file_uploader("Ficha Financeira", type=["pdf"])
file_car = st.sidebar.file_uploader("Fichas Cadastrais", type=["pdf"], accept_multiple_files=True)
base = st.sidebar.number_input("Base Classe A", value=4000.00)
nome = st.sidebar.text_input("Nome do Servidor", "Ironildo da Silva Costa")
matricula = st.sidebar.text_input("Matrícula", "0065998-3")

col1, col2 = st.columns([1, 1])
executar = col1.button("🚀 Executar Cálculo")
limpar = col2.button("🗑️ Limpar Tudo")

if limpar:
    st.session_state.clear()
    st.experimental_rerun()

st.title("⚖️ Cálculo Jurídico Automatizado (PC/AL)")

if executar:
    if not file_fin or not file_car:
        st.warning("Envie ambos os arquivos para iniciar.")
    else:
        df_fin = ler_financeiro(file_fin)
        df_car = ler_cadastral(file_car)
        if df_fin.empty or df_car.empty:
            st.error("Erro ao extrair dados. Verifique os arquivos.")
        else:
            df_calc = calcular(df_fin, df_car, base)
            st.success("✅ Cálculo realizado com sucesso.")
            st.dataframe(df_calc)

            colpdf, coltxt = st.columns(2)
            pdf_bytes = gerar_pdf_juridico(df_calc)
            txt_bytes = gerar_txt_projefweb(df_calc)

            colpdf.download_button("📄 Baixar Laudo PDF", pdf_bytes, "laudo.pdf", "application/pdf")
coltxt.download_button("📑 Baixar Projefweb TXT", txt_bytes, "projefweb.txt", "text/plain")
