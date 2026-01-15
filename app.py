import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import pytesseract
import fitz
import io
import re
import datetime

st.set_page_config(page_title="Cálculo PC/AL", layout="wide")

def fmt_br(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def ocr_pdf(file_bytes):
    linhas = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = pix.tobytes("png")
        texto = pytesseract.image_to_string(img, lang="por")
        linhas.extend(texto.splitlines())
    return linhas

def extrair_numeros_linha(linha):
    partes = re.findall(r"[\d\.,]+", linha)
    valores = []
    for p in partes:
        try:
            p = p.replace(".", "").replace(",", ".")
            val = float(p)
            if 0 < val < 100_000:
                valores.append(val)
        except:
            continue
    return valores

def ler_financeiro(file):
    linhas = []
    try:
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    linhas.extend(txt.splitlines())
    except:
        linhas = ocr_pdf(file.read())

    dados = []
    ano_atual = None
    meses_port = ['JANEIRO','FEVEREIRO','MARCO','ABRIL','MAIO','JUNHO','JULHO','AGOSTO','SETEMBRO','OUTUBRO','NOVEMBRO','DEZEMBRO']

    for linha in linhas:
        linha_up = linha.upper()
        ano_match = re.search(r"ANO\s*COMP[:\s]+(20\d{2})", linha_up)
        if ano_match:
            ano_atual = int(ano_match.group(1))

        for idx, mes_nome in enumerate(meses_port):
            if mes_nome in linha_up and ano_atual:
                numeros = extrair_numeros_linha(linha)
                sal = [n for n in numeros if n > 1200]
                if sal:
                    data = pd.to_datetime(f"{ano_atual}-{idx+1:02d}-01")
                    dados.append({"Data": data, "Valor_Pago": sal[0]})
    return pd.DataFrame(dados)

def ler_cadastral(arquivos):
    historico = []
    reg_cod = r"(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)"
    for arq in arquivos:
        try:
            reader = PdfReader(arq)
            for page in reader.pages:
                txt = page.extract_text() or ""
                linhas = txt.splitlines()
                for linha in linhas:
                    match_data = re.search(r"(\d{2}/\d{2}/\d{4})", linha)
                    match_cod = re.search(reg_cod, linha)
                    if match_data and match_cod:
                        data_pg = pd.to_datetime(match_data.group(1), dayfirst=True)
                        cod = match_cod.group(1).upper()
                        m = re.search(r"([A-G])40", cod)
                        if m:
                            classe = m.group(1)
                            historico.append({'Data_Mudanca': data_pg, 'Classe': classe})
        except Exception as e:
            print("Erro ao ler ficha:", e)

    if not historico:
        return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])

    df = pd.DataFrame(historico)
    df = df.drop_duplicates().sort_values('Data_Mudanca').reset_index(drop=True)
    return df

def calcular(df_fin, df_car, base):
    if df_car.empty:
        df_car = pd.DataFrame([{'Data_Mudanca': df_fin['Data'].min(), 'Classe': 'A'}])
    else:
        primeira_data = df_fin['Data'].min()
        if df_car['Data_Mudanca'].min() > primeira_data:
            df_car = pd.concat([pd.DataFrame([{'Data_Mudanca': primeira_data, 'Classe': 'A'}]), df_car], ignore_index=True)
    df_fin = df_fin.groupby('Data', as_index=False).agg({'Valor_Pago': 'sum'})
    df = pd.merge_asof(
        df_fin.sort_values('Data'),
        df_car.sort_values('Data_Mudanca'),
        left_on='Data',
        right_on='Data_Mudanca',
        direction='backward'
    )
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df['Indice'] = df['Classe'].map(mapa).fillna(0)
    df['Classe'] = df['Classe'].fillna('A')
    df['Valor_Devido'] = base * (1.15 ** df['Indice'])
    df['Diferenca'] = df['Valor_Devido'] - df['Valor_Pago']
    df['Diferenca_Final'] = df['Diferenca'].apply(lambda x: x if x > 0 else 0)
    return df

# Interface
st.title("⚖️ Sistema de Cálculo PC/AL")

col1, col2 = st.columns(2)
with col1:
    base = st.number_input("Valor Base da Classe A (R$)", value=4000.00, step=100.0)
    nome = st.text_input("Nome do Servidor", "Servidor Exemplo")
    mat = st.text_input("Matrícula", "000000-0")
with col2:
    fin = st.file_uploader("📂 Ficha Financeira (PDF)", type=["pdf"])
    car = st.file_uploader("📂 Fichas Cadastrais (PDFs)", type=["pdf"], accept_multiple_files=True)

colbtn1, colbtn2 = st.columns(2)
executar = colbtn1.button("🚀 Executar Cálculo")
limpar = colbtn2.button("🗑️ Limpar Tudo")

if limpar:
    st.session_state.clear()
    st.experimental_rerun()

if executar and fin and car:
    st.info("📥 Processando arquivos...")
    df_fin = ler_financeiro(fin)
    df_car = ler_cadastral(car)

    if df_fin.empty or df_car.empty:
        st.error("⚠️ Dados insuficientes. Verifique os PDFs.")
    else:
        res = calcular(df_fin, df_car, base)
        total = res['Diferenca_Final'].sum()

        st.success("✅ Cálculo concluído!")
        st.markdown(f"### Total Devido: {fmt_br(total)}")

        st.dataframe(res)
