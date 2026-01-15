import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import pytesseract
from PIL import Image
import io
import re
import fitz  # PyMuPDF
from datetime import datetime

st.set_page_config(page_title="Cálculo PC/AL", page_icon="⚖️", layout="wide")

def limpar_valor(txt):
    if isinstance(txt, (int, float)):
        return float(txt)
    if not txt:
        return 0.0
    t = str(txt).replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(t)
    except:
        return 0.0

def extrair_numeros_linha(linha):
    return [limpar_valor(val) for val in re.findall(r"\d+[.,]\d{2}", linha)]

def ocr_pdf(pdf_bytes):
    texto_total = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            txt = pytesseract.image_to_string(img, lang="por")
            texto_total += txt.splitlines()
    return texto_total

def ler_financeiro(file):
    linhas = []

    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    linhas.extend(txt.splitlines())
    except:
        linhas = []

    if not linhas:
        linhas = ocr_pdf(file.read())

    dados = []
    ano = None
    for linha in linhas:
        if not ano:
            m = re.search(r'(20\d{2})', linha)
            if m:
                ano = int(m.group(1))
        if any(p in linha.upper() for p in ["SUBSÍDIO", "VENC", "REMUN"]):
            numeros = extrair_numeros_linha(linha)
            for i, valor in enumerate(numeros[:12]):
                mes = i + 1
                data = pd.to_datetime(f"{ano}-{mes:02d}-01")
                dados.append({"Data": data, "Valor_Pago": valor})
    return pd.DataFrame(dados)

def ler_carreira(arquivos):
    historico = []
    for arq in arquivos:
        reader = PdfReader(arq)
        for page in reader.pages:
            txt = page.extract_text()
            if not txt:
                continue
            datas = re.findall(r'(\d{2}/\d{2}/\d{4})', txt)
            niveis = re.findall(r'(PCE[A-Z]\d+|AGP[A-Z0-9-]+|NV\d+[A-Z0-9-]*)', txt)
            for dt, cod in zip(datas, niveis):
                dt_obj = pd.to_datetime(dt, dayfirst=True)
                classe_match = re.search(r'([A-G])40', cod.upper())
                if classe_match:
                    historico.append({'Data_Mudanca': dt_obj, 'Classe': classe_match.group(1)})
    df = pd.DataFrame(historico).drop_duplicates().sort_values("Data_Mudanca")
    return df

def calcular_diferencas(fin, car, base):
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df = pd.merge_asof(fin.sort_values("Data"), car.sort_values("Data_Mudanca"),
                       left_on="Data", right_on="Data_Mudanca", direction="backward")
    df["Indice"] = df["Classe"].map(mapa).fillna(0)
    df["Valor_Devido"] = base * (1.15 ** df["Indice"])
    df["Diferenca"] = df["Valor_Devido"] - df["Valor_Pago"]
    df["Diferenca_Final"] = df["Diferenca"].apply(lambda x: x if x > 0 else 0)
    return df

def fmt_br(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class PDF(FPDF):
    def header(self):
        self.set_font('Times', 'B', 14)
        self.cell(0, 10, "LAUDO TÉCNICO PERICIAL", ln=True, align='C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f"Gerado em {datetime.now().strftime('%d/%m/%Y')} - Pág. {self.page_no()}", align='C')

def gerar_pdf(df, nome, matricula, total):
    p = PDF()
    p.add_page()
    p.set_font('Times', '', 12)
    p.cell(0, 10, f"Autor: {nome}", ln=True)
    p.cell(0, 10, f"Matrícula: {matricula}", ln=True)
    p.cell(0, 10, f"Réu: Estado de Alagoas", ln=True)
    p.ln(10)

    p.set_font('Times', 'B', 12)
    p.set_fill_color(212, 239, 223)
    p.cell(140, 10, "TOTAL DEVIDO", 1, 0, 'L', 1)
    p.cell(50, 10, fmt_br(total), 1, 1, 'R', 1)
    p.ln(5)

    headers = ['Mês/Ano', 'Classe', 'Pago', 'Devido', 'Diferença']
    widths = [30, 20, 40, 40, 40]
    p.set_font('Times', 'B', 10)
    for i, h in enumerate(headers):
        p.cell(widths[i], 8, h, 1, 0, 'C')
    p.ln()
    p.set_font('Times', '', 10)
    for _, r in df.iterrows():
        p.cell(widths[0], 8, r["Data"].strftime('%m/%Y'), 1)
        p.cell(widths[1], 8, str(r["Classe"]), 1)
        p.cell(widths[2], 8, fmt_br(r["Valor_Pago"]), 1, 0, 'R')
        p.cell(widths[3], 8, fmt_br(r["Valor_Devido"]), 1, 0, 'R')
        p.cell(widths[4], 8, fmt_br(r["Diferenca_Final"]), 1, 0, 'R')
        p.ln()

    p.ln(10)
    p.cell(0, 10, "__________________________", ln=True)
    p.cell(0, 6, "Assinatura do advogado/perito")
    return p.output(dest='S').encode("latin-1")

def gerar_txt_projefweb(df):
    s = io.StringIO()
    for _, r in df.iterrows():
        if r["Diferenca_Final"] > 0.01:
            data_fmt = r["Data"].strftime("%m-%Y")
            valor_fmt = fmt_br(r["Diferenca_Final"])
            s.write(f"{data_fmt}\t{valor_fmt}\n")
    return s.getvalue().encode("utf-8")

# ====================== INTERFACE STREAMLIT ======================
st.title("⚖️ Cálculo Jurídico PC/AL com OCR")

with st.sidebar:
    fin = st.file_uploader("Ficha Financeira (PDF)", type=["pdf"])
    cars = st.file_uploader("Fichas Cadastrais (PDFs)", type=["pdf"], accept_multiple_files=True)
    base = st.number_input("Valor Base Classe A", value=4000.00)
    nome = st.text_input("Nome", "Ironildo da Silva Costa")
    mat = st.text_input("Matrícula", "0065998-3")
    btn1, btn2 = st.columns(2)
    run = btn1.button("🚀 Executar")
    if btn2.button("🗑️ Limpar"):
        st.session_state.clear()
        st.experimental_rerun()

if run and fin and cars:
    df_fin = ler_financeiro(fin)
    df_car = ler_carreira(cars)
    if df_fin.empty:
        st.error("⚠️ Não foi possível ler a Ficha Financeira.")
    elif df_car.empty:
        st.error("⚠️ Nenhuma promoção foi detectada na(s) Ficha(s) Cadastral(is).")
    else:
        df_calc = calcular_diferencas(df_fin, df_car, base)
        total = df_calc["Diferenca_Final"].sum()

        st.success(f"Cálculo pronto. Total devido: {fmt_br(total)}")
        st.dataframe(df_calc)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_calc["Data"], y=df_calc["Valor_Pago"], name="Pago"))
        fig.add_trace(go.Scatter(x=df_calc["Data"], y=df_calc["Valor_Devido"], name="Devido"))
        fig.update_layout(title="Pago vs Devido", height=400)
        st.plotly_chart(fig, use_container_width=True)

        colpdf, coltxt = st.columns(2)
        colpdf.download_button("📄 Baixar PDF", gerar_pdf(df_calc, nome, mat, total), "laudo.pdf", "application/pdf")
        coltxt.download_button("📑 Baixar TXT Projefweb", gerar_txt_projefweb(df_calc), "projefweb.txt", "text/plain")
