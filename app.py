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
            if 0 < val < 100_000:  # Limite de sanidade
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
    ano_detectado = None
    for linha in linhas:
        if not ano_detectado:
            match = re.search(r"(20\d{2})", linha)
            if match:
                ano_detectado = int(match.group(1))
        numeros = extrair_numeros_linha(linha)
        numeros_salario = [n for n in numeros if n > 1200]
        if len(numeros_salario) >= 3 and ano_detectado:
            for i, valor in enumerate(numeros_salario[:12]):
                mes = i + 1
                data = pd.to_datetime(f"{ano_detectado}-{mes:02d}-01")
                dados.append({"Data": data, "Valor_Pago": valor})
    return pd.DataFrame(dados)

def ler_cadastral(arquivos):
    historico = []
    reg_cod = r'(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)'
    for arq in arquivos:
        try:
            reader = PdfReader(arq)
            for page in reader.pages:
                txt = page.extract_text() or ""
                dt_match = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', txt)
                dt_ref = dt_match.group(1) if dt_match else None
                if not dt_ref:
                    dts = re.findall(r'(\d{2}/\d{2}/\d{4})', txt)
                    if dts: dt_ref = dts[0]
                cods = re.findall(reg_cod, txt)
                if dt_ref and cods:
                    for c in cods:
                        cls = None
                        c_up = c.upper()
                        m1 = re.search(r'([A-G])40', c_up)
                        if m1: cls = m1.group(1)
                        else:
                            m2 = re.search(r'PCE([A-G])', c_up)
                            if m2: cls = m2.group(1)
                        if cls:
                            historico.append({
                                'Data_Mudanca': pd.to_datetime(dt_ref, dayfirst=True),
                                'Classe': cls
                            })
                            break
        except:
            pass
    if not historico:
        return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    df = pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')
    return df

def calcular(df_fin, df_car, base):
    df_car = df_car.sort_values('Data_Mudanca')

    data_inicio = df_fin['Data'].min()
    if df_car.empty or data_inicio < df_car['Data_Mudanca'].min():
        classe_inicial = {'Data_Mudanca': data_inicio, 'Classe': 'A'}
        df_car = pd.concat([pd.DataFrame([classe_inicial]), df_car], ignore_index=True)
        df_car = df_car.sort_values('Data_Mudanca')

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

class PDF(FPDF):
    def header(self):
        self.set_font('Arial','B',14)
        self.cell(0,10,'MEMÓRIA DE CÁLCULO ATUALIZADA',0,1,'C')
        self.ln(5)
        self.line(10, 25, 200, 25)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial','I',8)
        data = datetime.datetime.now().strftime('%d/%m/%Y')
        self.cell(0,10,f'Documento gerado eletronicamente em {data} para fins processuais.',0,0,'C')

def gerar_pdf(df, nome, mat, total):
    p = PDF()
    p.add_page()
    p.set_font('Arial', '', 10)
    p.cell(0, 6, f"Servidor: {nome} | Matrícula: {mat}", 0, 1)
    p.ln()
    p.set_fill_color(220,255,220)
    p.set_font('Arial','B',12)
    p.cell(0,10,f"TOTAL DEVIDO: {fmt_br(total)}",1,1,'C',1)
    p.ln()
    p.set_font('Arial','B',9)
    w = [30,20,35,35,35]
    h = ['Data','Classe','Pago','Devido','Diferença']
    for i,x in enumerate(h): p.cell(w[i],7,x,1,0,'C')
    p.ln()
    p.set_font('Arial','',9)
    for _,r in df.iterrows():
        p.cell(w[0],6,r['Data'].strftime('%m/%Y'),1,0,'C')
        p.cell(w[1],6,str(r['Classe']),1,0,'C')
        p.cell(w[2],6,fmt_br(r['Valor_Pago']),1,0,'R')
        p.cell(w[3],6,fmt_br(r['Valor_Devido']),1,0,'R')
        p.cell(w[4],6,fmt_br(r['Diferenca_Final']),1,0,'R')
        p.ln()
    return p.output(dest='S').encode('latin-1','ignore')

def gerar_txt_projefweb(df):
    s = io.StringIO()
    for _,r in df.iterrows():
        if r["Diferenca_Final"] > 0.01:
            data_fmt = r["Data"].strftime("%m-%Y")
            valor_fmt = fmt_br(r["Diferenca_Final"])
            s.write(f"{data_fmt}\t{valor_fmt}\n")
    return s.getvalue().encode("utf-8")

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

        colpdf, coltxt = st.columns(2)
        colpdf.download_button("📄 Baixar Laudo PDF", gerar_pdf(res, nome, mat, total), "laudo.pdf", "application/pdf")
        coltxt.download_button("📑 Baixar Projefweb TXT", gerar_txt_projefweb(res), "projefweb.txt", "text/plain")
