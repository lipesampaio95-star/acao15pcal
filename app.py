
import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from fpdf import FPDF
from datetime import datetime

st.set_page_config(page_title="Cálculo PC/AL", layout="wide")

# Utilitários
def fmt_br(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

MAPA_CLASSES = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}
MESES = ['JANEIRO','FEVEREIRO','MARÇO','ABRIL','MAIO','JUNHO','JULHO','AGOSTO','SETEMBRO','OUTUBRO','NOVEMBRO','DEZEMBRO']

# ====================== Leitura Estruturada Ficha Financeira ======================
def ler_ficha_financeira_anual(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        texto = ""
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    linhas = texto.splitlines()
    ano = None
    dados = {}

    for linha in linhas:
        if "ANO COMP" in linha.upper():
            m = re.search(r"(20\d{2})", linha)
            if m:
                ano = int(m.group(1))

        if linha.strip().startswith("126.00 SUBSIDIO"):
            valores = re.findall(r'\d{1,3}(?:\.\d{3})*,\d{2}', linha)
            for i, val in enumerate(valores[:12]):
                mes = i + 1
                valor = float(val.replace(".", "").replace(",", "."))
                dados.setdefault(mes, {})["SUBSIDIO"] = valor

        if linha.strip().startswith("133.00 ADICIONAL DE FERIAS"):
            valores = re.findall(r'\d{1,3}(?:\.\d{3})*,\d{2}', linha)
            for i, val in enumerate(valores[:12]):
                mes = i + 1
                valor = float(val.replace(".", "").replace(",", "."))
                dados.setdefault(mes, {})["FERIAS"] = valor

        if linha.strip().startswith("200.40 13. SALARIO"):
            valores = re.findall(r'\d{1,3}(?:\.\d{3})*,\d{2}', linha)
            for i, val in enumerate(valores[:12]):
                mes = i + 1
                valor = float(val.replace(".", "").replace(",", "."))
                dados.setdefault(mes, {})["13SAL"] = valor

    registros = []
    for mes in range(1, 13):
        if mes in dados and ano:
            data = pd.to_datetime(f"{ano}-{mes:02d}-01")
            subsidio = dados[mes].get("SUBSIDIO", 0.0)
            ferias = dados[mes].get("FERIAS", 0.0)
            decimo = dados[mes].get("13SAL", 0.0)
            pago = subsidio + ferias + decimo
            registros.append({"Data": data, "Valor_Pago": pago})

    return pd.DataFrame(registros)

# ====================== Cálculo das Diferenças ======================
def calcular(df_fin, df_car, base):
    df = pd.merge_asof(df_fin.sort_values("Data"), df_car.sort_values("Data_Mudanca"), left_on="Data", right_on="Data_Mudanca", direction="backward")
    df["Indice"] = df["Classe"].map(MAPA_CLASSES).fillna(0)
    df["Valor_Devido"] = base * (1.15 ** df["Indice"])
    df["Diferenca"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Diferenca_Final"] = df["Diferenca"].apply(lambda x: x if x > 0 else 0)
    return df

# ====================== Geração de Arquivos ======================
def gerar_txt_projefweb(df):
    s = io.StringIO()
    for _, r in df.iterrows():
        if r["Diferenca_Final"] > 0:
            s.write(f"{r['Data'].strftime('%m-%Y')}\tR$ {fmt_br(r['Diferenca_Final'])}\n")
    return s.getvalue().encode("utf-8")

class PDF(FPDF):
    def header(self):
        self.set_font("Times", "B", 14)
        self.cell(0, 10, "LAUDO TÉCNICO PERICIAL", 0, 1, "C")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Gerado em {datetime.now().strftime('%d/%m/%Y')}", 0, 0, "C")

def gerar_pdf(df, nome, mat, total):
    p = PDF()
    p.add_page()
    p.set_font("Arial", "", 10)
    p.cell(0, 6, f"Servidor: {nome} - Matrícula: {mat}", 0, 1)
    p.ln(3)
    p.set_font("Arial", "B", 11)
    p.set_fill_color(212, 239, 223)
    p.cell(0, 8, f"TOTAL DEVIDO: R$ {fmt_br(total)}", 1, 1, "C", 1)
    p.ln(4)
    p.set_font("Arial", "B", 9)
    colunas = ["Data", "Classe", "Pago", "Devido", "Diferença"]
    larguras = [25, 20, 35, 35, 35]
    for i, c in enumerate(colunas): p.cell(larguras[i], 7, c, 1, 0, "C")
    p.ln()
    p.set_font("Arial", "", 9)
    for _, r in df.iterrows():
        p.cell(larguras[0], 6, r["Data"].strftime("%m/%Y"), 1)
        p.cell(larguras[1], 6, r["Classe"], 1, 0, "C")
        p.cell(larguras[2], 6, f"R$ {fmt_br(r['Valor_Pago'])}", 1, 0, "R")
        p.cell(larguras[3], 6, f"R$ {fmt_br(r['Valor_Devido'])}", 1, 0, "R")
        p.cell(larguras[4], 6, f"R$ {fmt_br(r['Diferenca_Final'])}", 1, 0, "R")
        p.ln()
    return p.output(dest="S").encode("latin-1")

# ====================== INTERFACE ======================
st.title("⚖️ Cálculo PC/AL - Promoções Manuais")

st.markdown("**1. Faça upload dos PDFs da Ficha Financeira (um por ano):**")
arquivos = st.file_uploader("📄 Ficha(s) Financeira(s)", type=["pdf"], accept_multiple_files=True)

st.markdown("**2. Informe as promoções manualmente (uma por linha no formato MÊS/ANO - CLASSE):**")
exemplo = "01/2016 - E\n04/2020 - F\n04/2025 - G"
entrada = st.text_area("Promoções", value=exemplo, height=120)

st.markdown("**3. Parâmetros adicionais:**")
base = st.number_input("💰 Valor Classe A", value=4000.00)
nome = st.text_input("👤 Nome do Servidor")
mat = st.text_input("🆔 Matrícula")

col_exec, col_clear = st.columns(2)
executar = col_exec.button("🚀 Executar Cálculo")
limpar = col_clear.button("🗑️ Limpar Dados")

if limpar:
    st.session_state.clear()
    st.experimental_rerun()

if executar and arquivos and entrada:
    # Processar promoções
    linhas = entrada.strip().splitlines()
    historico = []
    for linha in linhas:
        partes = linha.strip().split("-")
        if len(partes) == 2:
            data_str = partes[0].strip()
            classe = partes[1].strip().upper()
            try:
                dt = pd.to_datetime("01/" + data_str, dayfirst=True)
                historico.append({"Data_Mudanca": dt, "Classe": classe})
            except:
                pass
    df_car = pd.DataFrame(historico).sort_values("Data_Mudanca")

    # Processar todos os PDFs
    df_total = pd.DataFrame()
    for arq in arquivos:
        df_fin = ler_ficha_financeira_anual(arq)
        df_total = pd.concat([df_total, df_fin], ignore_index=True)

    if df_total.empty or df_car.empty:
        st.error("⚠️ Dados insuficientes para cálculo.")
    else:
        resultado = calcular(df_total, df_car, base)
        total = resultado["Diferenca_Final"].sum()
        st.success(f"✅ Total devido: R$ {fmt_br(total)}")
        st.dataframe(resultado)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 Baixar PDF", gerar_pdf(resultado, nome, mat, total), "laudo.pdf", "application/pdf")
        with col2:
            st.download_button("📑 Baixar TXT", gerar_txt_projefweb(resultado), "projefweb.txt", "text/plain")
