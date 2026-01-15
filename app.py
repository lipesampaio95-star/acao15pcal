import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Cálculo PC/AL - Pro", page_icon="🚔", layout="wide")

# --- ESTILOS CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #f8f9fa; border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #e9ecef; }
    .total-card { background-color: #d4efdf; border: 2px solid #27ae60; border-radius: 10px; padding: 15px; text-align: center; }
    div.stButton > button:first-child { background-color: #2E86C1; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
    div.stButton > button:first-child:hover { background-color: #1a5276; }
</style>
""", unsafe_allow_html=True)

# --- ROBÔ FINANCEIRO (PDF/EXCEL) ---
def limpar_moeda(valor):
    """Transforma R$ 1.000,00 ou 1.000,00 em float 1000.0"""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    # Remove R$, espaços e pontos de milhar, troca vírgula por ponto
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def ler_financeiro_pdf(arquivo):
    """Lê PDF Financeiro tentando tabelas e depois linhas de texto."""
    dados = []
    log_erro = []
    
    with pdfplumber.open(arquivo) as pdf:
        for i, page in enumerate(pdf.pages):
            # TENTATIVA 1: Extrair Tabelas (Melhor precisão)
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        row = [str(x) if x else "" for x in row]
                        # Procura Data e Valor na mesma linha
                        dt, val = None, None
                        for cell in row:
                            cell = cell.replace('\n', ' ').strip()
                            if not dt and re.search(r'\b\d{2}/\d{4}\b', cell):
                                dt = re.search(r'\b(\d{2}/\d{4})\b', cell).group(1)
                            elif not val and re.match(r'^R?\s?[\d\.]+,[\d]{2}$', cell):
                                v = limpar_moeda(cell)
                                if v > 1200: val = v # Filtro de valor mínimo
                        if dt and val: dados.append({'Data': dt, 'Valor_Pago': val})
            
            # TENTATIVA 2: Se não achou tabela, varre o texto bruto
            if not dados:
                text = page.extract_text()
                if text:
                    for line in text.split('\n'):
                        # Regex procura: Data (MM/YYYY) ...espaço... Valor (X.XXX,XX)
                        match = re.search(r'(\d{2}/\d{4}).*?(\d{1,3}(?:\.\d{3})*,\d{2})', line)
                        if match:
                            dt = match.group(1)
                            val = limpar_moeda(match.group(2))
                            if val > 1200: dados.append({'Data': dt, 'Valor_Pago': val})

    if dados:
        df = pd.DataFrame(dados)
        df['Data'] = pd.to_datetime(df['Data'], format='%m/%Y', errors='coerce')
        return df.dropna().sort_values('Data')
    
    return pd.DataFrame()

# --- ROBÔ CADASTRAL (PDF) ---
def extrair_classe(texto_codigo):
    """Extrai a letra da classe de códigos variados."""
    texto = texto_codigo.upper()
    # Padrão: Letra seguida de 40 (ex: F40, G40)
    match = re.search(r'([A-G])40', texto)
    if match: return match.group(1)
    # Padrão Antigo: PCE + Letra (ex: PCEE)
    match = re.search(r'PCE([A-G])', texto)
    if match: return match.group(1)
    return None

def ler_ficha_cadastral(arquivos):
    historico = []
    # Regex flexível: Pega datas e códigos soltos na página
    reg_data = r'(\d{2}/\d{2}/\d{4})'
    reg_cod = r'(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)'

    for arq in arquivos:
        try:
            reader = PdfReader(arq)
            for page in reader.pages:
                txt = page.extract_text()
                # Acha todas as datas e códigos da página
                datas = re.findall(reg_data, txt)
                codigos = re.findall(reg_cod, txt)
                
                # HEURÍSTICA: Se a página tem uma data de promoção e um código, eles se pertencem.
                # Geralmente a ficha repete o estado atual do servidor todo mês.
                # Vamos pegar o código mais frequente ou o primeiro da página.
                if datas and codigos:
                    # Tenta achar a data específica do campo "Data Promoção" se houver label
                    match_promo = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', txt)
                    data_ref = match_promo.group(1) if match_promo else datas[0]
                    
                    for cod in codigos:
                        cls = extrair_classe(cod)
                        if cls:
                            historico.append({'Data_Mudanca': pd.to_datetime(data_ref, dayfirst=True), 'Classe': cls})
                            # Se achou um válido na página, já serve para marcar o período
                            break
        except Exception as e:
            st.warning(f"Aviso: Não consegui ler o arquivo {arq.name}. Erro: {e}")

    if not historico: return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    return pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')

# --- CÁLCULO E RELATÓRIOS ---
def calcular(df_fin, df_car, base_a):
    df_fin = df_fin.sort_values('Data')
    df_car = df_car.sort_values('Data_Mudanca')
    # Cruzamento temporal
    df = pd.merge_asof(df_fin, df_car, left_on='Data', right_on='Data_Mudanca', direction='backward')
    
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df['Indice'] = df['Classe'].map(mapa).fillna(0) # Se não achar, assume A (0)
    df['Classe'] = df['Classe'].fillna('A')
    
    df['Valor_Devido'] = base_a * (1.15 ** df['Indice'])
    df['Diferenca'] = df['Valor_Devido'] - df['Valor_Pago']
    df['Diferenca_Final'] = df['Diferenca'].apply(lambda x: x if x > 0 else 0)
    return df

def format_br(val): return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Relatório de Cálculo Pericial', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pág {self.page_no()}', 0, 0, 'C')

def gerar_pdf_laudo(df, nome, mat, cpf, tot):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f"Servidor: {nome} | Matrícula: {mat}", 0, 1)
    pdf.ln(5)
    pdf.set_fill_color(220, 255, 220)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"TOTAL A RECEBER: R$ {format_br(tot)}", 1, 1, 'C', 1)
    pdf.ln(5)
    
    # Tabela
    pdf.set_font('Arial', 'B', 9)
    cols = [30, 20, 35, 35, 35]
    headers = ['Data', 'Classe', 'Pago', 'Devido', 'Diferença']
    for i, h in enumerate(headers): pdf.cell(cols[i], 7, h, 1, 0, 'C')
    pdf.ln()
    
    pdf.set_font('Arial', '', 9)
    for _, row in df.iterrows():
        if row['Diferenca_Final'] > 0: pdf.set_font('Arial', 'B', 9)
        else: pdf.set_font('Arial', '', 9)
        
        pdf.cell(cols[0], 6, row['Data'].strftime('%m/%Y'), 1, 0, 'C')
        pdf.cell(cols[1], 6, str(row['Classe']), 1, 0, 'C')
        pdf.cell(cols[2], 6, format_br(row['Valor_Pago']), 1, 0, 'R')
        pdf.cell(cols[3], 6, format_br(row['Valor_Devido']), 1, 0, 'R')
        pdf.cell(cols[4], 6, format_br(row['Diferenca_Final']), 1, 0, 'R')
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'ignore')

def gerar_projefweb(df):
    s = io.StringIO()
    for _, row in df.iterrows():
        if row['Diferenca_Final'] > 0.01:
            s.write(f"{row['Data'].strftime('%m-%Y')}\tR$ {format_br(row['Diferenca_Final'])}\n")
    return s.getvalue().encode('utf-8')

# --- APP ---
st.sidebar.title("Cálculo PC/AL")
file_fin = st.sidebar.file_uploader("1. Financeiro (PDF/Excel)", type=['pdf','xlsx','csv'])
files_car = st.sidebar.file_uploader("2. Carreira (PDFs)", type=['pdf'], accept_multiple_files=True)
val_base = st.sidebar.number_input("Base Classe A (R$)", 4000.00)
nome = st.sidebar.text_input("Nome", "SERVIDOR")
mat = st.sidebar.text_input("Matrícula", "000000")

# Botão Reset
if st.sidebar.button("Limpar"):
    st.session_state.clear()
    st.experimental_rerun()

st.title("⚖️ Automação de Cálculo Jurídico")

# --- LÓGICA DO BOTÃO EXECUTAR ---
if file_fin and files_car:
    if st.button("🚀 Executar Cálculos"):
        with st.spinner("Processando arquivos..."):
            try:
                # 1. Ler Financeiro
                df_fin = pd.DataFrame()
                if file_fin.name.endswith('.pdf'): df_fin = ler_financeiro_pdf(file_fin)
                elif file_fin.name.endswith('.csv'): df_fin = pd.read_csv(file_fin)
                else: df_fin = pd.read_excel(file_fin)
                
                # Padronizar colunas Financeiro
                if not df_fin.empty:
                    # Acha coluna de data e valor dinamicamente
                    c_dt = next((c for c in df_fin.columns if 'data' in c.lower()), 'Data')
                    c_val = next((c for c in df_fin.columns if 'valor' in c.lower() or 'pago' in c.lower()), 'Valor_Pago')
                    df_fin = df_fin.rename(columns={c_dt:'Data', c_val:'Valor_Pago'})
                    df_fin['Data'] = pd.to_datetime(df_fin['Data'])

                # 2. Ler Carreira
                df_car = ler_ficha_cadastral(files_car)

                # 3. Validar e Calcular
                erro_msg = ""
                if df_fin.empty: erro_msg += "- Não consegui ler dados financeiros válidos.\n"
                if df_car.empty: erro_msg += "- Não encontrei datas de promoção ou códigos de classe nos PDFs de carreira.\n"
                
                if not erro_msg:
                    res = calcular(df_fin, df_car, val_base)
                    st.session_state['res'] = res
                    st.session_state['processed'] = True
                    st.success("Cálculo realizado!")
                else:
                    st.error(f"Erro na leitura:\n{erro_msg}")
            
            except Exception as e:
                st.error(f"Erro crítico: {e}")

# --- EXIBIÇÃO DE RESULTADOS ---
if st.session_state.get('processed'):
    res = st.session_state['res']
    total = res['Diferenca_Final'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(res))
    c2.metric("Classe Atual", res['Classe'].iloc[-1])
    c3.markdown(f"<div class='total-card'><b>TOTAL: R$ {format_br(total)}</b></div>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Gráficos", "Downloads"])
    with tab1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='red')))
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido', line=dict(color='green', dash='dash')))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(res)
    with tab2:
        c_xls, c_pdf, c_txt = st.columns(3)
        
        # Excel
        b_xls = io.BytesIO()
        with pd.ExcelWriter(b_xls, engine='xlsxwriter') as w: res.to_excel(w, index=False)
        c_xls.download_button("📥 Excel", b_xls.getvalue(), f"{nome}.xlsx")
        
        # PDF
        b_pdf = gerar_pdf_laudo(res, nome, mat, "000", total)
        c_pdf.download_button("📄 Laudo PDF", b_pdf, f"{nome}_laudo.pdf")
        
        # Projefweb
        b_txt = gerar_projefweb(res)
        c_txt.download_button("📝 Projefweb", b_txt, f"{nome}_projefweb.txt")

elif not file_fin:
    st.info("Aguardando upload dos arquivos.")
