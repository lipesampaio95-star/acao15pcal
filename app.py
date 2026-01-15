import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re
from datetime import datetime

st.set_page_config(page_title="Cálculo PC/AL", page_icon="⚖️", layout="wide")

# ============================ FUNÇÕES UTILITÁRIAS =============================

def limpar_valor(texto):
    if isinstance(texto, (int, float)):
        return float(texto)
    if not texto:
        return 0.0
    t = str(texto).replace('"', '').replace("'", "").replace('R$', '').replace('.', '').replace(',', '.').strip()
    try:
        return float(t)
    except:
        return 0.0

def extrair_numeros_linha(linha_texto):
    partes = re.split(r'[\s\t]+', linha_texto)
    valores = [limpar_valor(p) for p in partes if limpar_valor(p) > 0]
    return valores

def ler_financeiro(arquivo):
    linhas = []
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if texto:
                linhas.extend(texto.split('\n'))

    dados = []
    ano_atual = None
    for linha in linhas:
        linha_upper = linha.upper()
        if "SUBSÍDIO" in linha_upper and not any(x in linha_upper for x in ["ALIMENT", "TRANSP"]):
            if not ano_atual:
                ano_match = re.search(r'\b(20[1-3][0-9])\b', linha)
                if ano_match:
                    ano_atual = int(ano_match.group(1))
            numeros = extrair_numeros_linha(linha)
            if len(numeros) >= 1:
                for i, val in enumerate(numeros[:12]):
                    data = pd.to_datetime(f"{ano_atual}-{i+1:02d}-01")
                    dados.append({'Data': data, 'Valor_Pago': val})
    return pd.DataFrame(dados)

def ler_carreira(arquivos):
    historico = []
    for arq in arquivos:
        reader = PdfReader(arq)
        for page in reader.pages:
            texto = page.extract_text()
            if not texto:
                continue
            datas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
            niveis = re.findall(r'(PCE[A-Z]\d+|AGP[A-Z0-9-]+|NV\d+[A-Z0-9-]*)', texto)
            for dt, cod in zip(datas, niveis):
                dt_obj = pd.to_datetime(dt, dayfirst=True)
                classe_match = re.search(r'([A-G])40', cod.upper())
                if classe_match:
                    historico.append({'Data_Mudanca': dt_obj, 'Classe': classe_match.group(1)})
    df = pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')
    return df

def calcular_diferencas(fin, car, base):
    mapa = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}
    df = pd.merge_asof(fin.sort_values('Data'), car.sort_values('Data_Mudanca'),
                       left_on='Data', right_on='Data_Mudanca', direction='backward')
    df['Indice'] = df['Classe'].map(mapa).fillna(0)
    df['Valor_Devido'] = base * (1.15 ** df['Indice'])
    df['Diferenca'] = df['Valor_Devido'] - df['Valor_Pago']
    df['Diferenca_Final'] = df['Diferenca'].apply(lambda x: x if x > 0 else 0)
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
        self.cell(0, 10, f"Documento gerado em {datetime.now().strftime('%d/%m/%Y')} - Pág. {self.page_no()}", align='C')

def gerar_pdf(df, nome, matricula, total):
    p = PDF()
    p.add_page()
    p.set_font('Times', '', 12)
    p.cell(0, 10, f"Autor: {nome}", ln=True)
    p.cell(0, 10, f"Matrícula: {matricula}", ln=True)
    p.cell(0, 10, f"Réu: Estado de Alagoas", ln=True)
    p.ln(10)

    # Quadro Resumo
    p.set_font('Times', 'B', 12)
    p.set_fill_color(212, 239, 223)
    p.cell(0, 10, "Quadro Resumo", ln=True)
    p.cell(140, 10, "TOTAL DEVIDO", 1, 0, 'L', 1)
    p.cell(50, 10, fmt_br(total), 1, 1, 'R', 1)
    p.ln(5)

    # Tabela detalhada
    p.set_font('Times', 'B', 10)
    headers = ['Mês/Ano', 'Classe', 'Pago', 'Devido', 'Diferença']
    widths = [30, 20, 40, 40, 40]
    for i, h in enumerate(headers):
        p.cell(widths[i], 8, h, 1, 0, 'C')
    p.ln()
    p.set_font('Times', '', 10)
    for _, r in df.iterrows():
        p.cell(widths[0], 8, r['Data'].strftime('%m/%Y'), 1)
        p.cell(widths[1], 8, str(r['Classe']), 1)
        p.cell(widths[2], 8, fmt_br(r['Valor_Pago']), 1, 0, 'R')
        p.cell(widths[3], 8, fmt_br(r['Valor_Devido']), 1, 0, 'R')
        p.cell(widths[4], 8, fmt_br(r['Diferenca_Final']), 1, 0, 'R')
        p.ln()

    p.ln(15)
    p.cell(0, 10, "__________________________", ln=True)
    p.cell(0, 6, "Assinatura do advogado/perito")
    return p.output(dest='S').encode('latin-1')

def gerar_projefweb_txt(df):
    s = io.StringIO()
    for _, r in df.iterrows():
        if r['Diferenca_Final'] > 0.01:
            data_fmt = r['Data'].strftime('%m-%Y')
            valor_fmt = fmt_br(r['Diferenca_Final'])
            s.write(f"{data_fmt}\t{valor_fmt}\n")
    return s.getvalue().encode('utf-8')

# ============================== INTERFACE STREAMLIT ==============================
st.title("⚖️ Sistema de Cálculo Jurídico PC/AL")

with st.sidebar:
    st.header("Parâmetros")
    fin_file = st.file_uploader("📁 Ficha Financeira", type=["pdf"])
    car_files = st.file_uploader("📄 Fichas Cadastrais", type=["pdf"], accept_multiple_files=True)
    base_val = st.number_input("Valor Base Classe A (R$)", value=4000.00)
    nome = st.text_input("Nome do Autor", "Ironildo da Silva Costa")
    matricula = st.text_input("Matrícula", "0065998-3")
    col1, col2 = st.columns(2)
    executar = col1.button("🚀 Executar Cálculo")
    if col2.button("🗑️ Limpar Tudo"):
        st.session_state.clear()
        st.experimental_rerun()

if executar and fin_file and car_files:
    df_fin = ler_financeiro(fin_file)
    df_car = ler_carreira(car_files)
    if df_fin.empty or df_car.empty:
        st.error("Erro: Dados insuficientes. Verifique os PDFs.")
    else:
        res = calcular_diferencas(df_fin, df_car, base_val)
        total = res['Diferenca_Final'].sum()

        st.success(f"Cálculo executado. Total devido: {fmt_br(total)}")

        st.dataframe(res[['Data', 'Classe', 'Valor_Pago', 'Valor_Devido', 'Diferenca_Final']])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name="Pago", line=dict(color="red")))
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name="Devido", line=dict(color="green")))
        fig.update_layout(title="Evolução: Pago x Devido", height=400)
        st.plotly_chart(fig, use_container_width=True)

        colpdf, coltxt = st.columns(2)
        colpdf.download_button("📄 Baixar Laudo PDF", gerar_pdf(res, nome, matricula, total), "laudo.pdf", "application/pdf")
        coltxt.download_button("📑 Baixar Projefweb TXT", gerar_projefweb_txt(res), "projefweb.txt", "text/plain")
