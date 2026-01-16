
import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
from fpdf import FPDF
from datetime import datetime

st.set_page_config(page_title="Cálculo PC/AL", layout="wide")

def fmt_br(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

MESES = ['JANEIRO','FEVEREIRO','MARÇO','ABRIL','MAIO','JUNHO','JULHO','AGOSTO','SETEMBRO','OUTUBRO','NOVEMBRO','DEZEMBRO']
MAPA_MESES = {m.upper(): i+1 for i, m in enumerate(MESES)}
MAPA_CLASSES = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}

# ======================== FINANCEIRO ==========================

def ler_ficha_financeira_estruturada(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        texto = ""
        for page in pdf.pages:
            texto += page.extract_text() + "\n"

    linhas = texto.splitlines()
    ano = None
    dados = {}

    for linha in linhas:
        if "ANO COMP" in linha.upper():
            m = re.search(r'(20\d{2})', linha)
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
        if mes in dados:
            data = pd.to_datetime(f"{ano}-{mes:02d}-01")
            subsidio = dados[mes].get("SUBSIDIO", 0.0)
            ferias = dados[mes].get("FERIAS", 0.0)
            decimo = dados[mes].get("13SAL", 0.0)
            pago = subsidio + ferias + decimo
            registros.append({"Data": data, "Valor_Pago": pago})
    return pd.DataFrame(registros)

# ======================== CARREIRA ==========================

def ler_carreira(pdf_files):
    historico = []
    regex_cod = r"(AGP[A-Z0-9]+|PCE[A-Z]\d+|NV\d+.*?[A-G]40)"
    for file in pdf_files:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                texto = page.extract_text()
                if not texto: continue
                linhas = texto.splitlines()
                for linha in linhas:
                    dt_match = re.search(r'(\d{2}/\d{2}/\d{4})', linha)
                    cod_match = re.search(regex_cod, linha)
                    if dt_match and cod_match:
                        classe_match = re.search(r'([A-G])40', cod_match.group(1))
                        if classe_match:
                            data = pd.to_datetime(dt_match.group(1), dayfirst=True)
                            classe = classe_match.group(1)
                            historico.append({'Data_Mudanca': data, 'Classe': classe})
    if not historico:
        return pd.DataFrame(columns=["Data_Mudanca", "Classe"])
    return pd.DataFrame(historico).drop_duplicates().sort_values("Data_Mudanca")

# ======================== CÁLCULO ==========================

def calcular(df_fin, df_car, base):
    if df_car.empty:
        df_car = pd.DataFrame([{"Data_Mudanca": df_fin["Data"].min(), "Classe": "A"}])
    elif df_car["Data_Mudanca"].min() > df_fin["Data"].min():
        primeira = {"Data_Mudanca": df_fin["Data"].min(), "Classe": "A"}
        df_car = pd.concat([pd.DataFrame([primeira]), df_car], ignore_index=True)

    df = pd.merge_asof(df_fin.sort_values("Data"), df_car.sort_values("Data_Mudanca"), left_on="Data", right_on="Data_Mudanca", direction="backward")
    df["Indice"] = df["Classe"].map(MAPA_CLASSES).fillna(0)
    df["Valor_Devido"] = base * (1.15 ** df["Indice"])
    df["Diferenca"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Diferenca_Final"] = df["Diferenca"].apply(lambda x: x if x > 0 else 0)
    return df

# ======================== EXPORTAÇÃO ==========================

def gerar_txt(df):
    s = io.StringIO()
    for _, r in df.iterrows():
        if r["Diferenca_Final"] > 0:
            s.write(f"{r['Data'].strftime('%m-%Y')}\tR$ {fmt_br(r['Diferenca_Final'])}\n")
    return s.getvalue().encode("utf-8")

def gerar_pdf(df, nome, mat, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "LAUDO TÉCNICO PERICIAL", 0, 1, "C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 8, f"Servidor: {nome} - Matrícula: {mat}", 0, 1)
    pdf.ln(5)
    pdf.set_fill_color(212, 239, 223)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, f"TOTAL DEVIDO: R$ {fmt_br(total)}", 1, 1, "C", 1)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 9)
    col = ["Mês", "Classe", "Pago", "Devido", "Diferença"]
    w = [25, 20, 35, 35, 35]
    for i, c in enumerate(col): pdf.cell(w[i], 7, c, 1, 0, "C")
    pdf.ln()
    pdf.set_font("Arial", "", 8)
    for _, r in df.iterrows():
        pdf.cell(w[0], 6, r["Data"].strftime("%m/%Y"), 1)
        pdf.cell(w[1], 6, str(r["Classe"]), 1, 0, "C")
        pdf.cell(w[2], 6, f"R$ {fmt_br(r['Valor_Pago'])}", 1, 0, "R")
        pdf.cell(w[3], 6, f"R$ {fmt_br(r['Valor_Devido'])}", 1, 0, "R")
        pdf.cell(w[4], 6, f"R$ {fmt_br(r['Diferenca_Final'])}", 1, 0, "R")
        pdf.ln()
    return pdf.output(dest='S').encode("latin-1")

# ======================== UI ==========================

st.title("⚖️ Cálculo PC/AL - Estrutura Fixa")

col1, col2 = st.columns(2)
with col1:
    fin = st.file_uploader("📄 Ficha Financeira", type=["pdf"])
with col2:
    car = st.file_uploader("📂 Ficha(s) Cadastral(is)", type=["pdf"], accept_multiple_files=True)

base = st.number_input("💰 Base Classe A (R$)", value=4000.00)
nome = st.text_input("👤 Nome do Servidor")
mat = st.text_input("🆔 Matrícula")

col_exec, col_clear = st.columns(2)
executar = col_exec.button("🚀 Executar Cálculo")
limpar = col_clear.button("🗑️ Limpar Dados")

if limpar:
    st.session_state.clear()
    st.experimental_rerun()

if executar and fin and car:
    df_fin = ler_ficha_financeira_estruturada(fin)
    df_car = ler_carreira(car)
    if df_fin.empty or df_car.empty:
        st.error("⚠️ Dados insuficientes.")
    else:
        res = calcular(df_fin, df_car, base)
        total = res["Diferenca_Final"].sum()
        st.success(f"✅ Total Devido: R$ {fmt_br(total)}")
        st.dataframe(res)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📄 Baixar PDF", gerar_pdf(res, nome, mat, total), "laudo.pdf", "application/pdf")
        with col2:
            st.download_button("📑 Baixar Projefweb TXT", gerar_txt(res), "projefweb.txt", "text/plain")
