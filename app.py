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

# --- ROBÔ FINANCEIRO (CORRIGIDO PARA O SEU LAYOUT) ---
def limpar_moeda(valor):
    """Transforma R$ 1.000,00 ou 1.000,00 em float 1000.0"""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    # Remove R$, espaços e pontos de milhar, troca vírgula por ponto
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def ler_financeiro_pdf(arquivo):
    """
    Lê PDF Financeiro no formato MATRICIAL (Horizontal).
    Procura 'Ano Comp: 20XX' e colunas 'Janeiro', 'Fevereiro'...
    """
    dados = []
    meses_map = {
        'Janeiro': 1, 'Fevereiro': 2, 'Março': 3, 'Abril': 4, 'Maio': 5, 'Junho': 6,
        'Julho': 7, 'Agosto': 8, 'Setembro': 9, 'Outubro': 10, 'Novembro': 11, 'Dezembro': 12
    }
    
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto_pag = page.extract_text()
            
            # 1. Tentar descobrir o ANO desta página
            # Procura por "Ano Comp: 2016" ou "Exercicio: 2016"
            match_ano = re.search(r'Ano Comp:\s*(\d{4})', texto_pag)
            if not match_ano:
                match_ano = re.search(r'(\d{4})', texto_pag) # Tentativa genérica se falhar
                
            ano_pag = int(match_ano.group(1)) if match_ano else None
            
            # 2. Extrair Tabelas
            tables = page.extract_tables()
            for table in tables:
                # Procura a linha de cabeçalho com os meses
                header_index = -1
                col_indices = {}
                
                for idx, row in enumerate(table):
                    row_str = [str(x) if x else "" for x in row]
                    # Verifica se esta linha tem nomes de meses
                    found_months = 0
                    for col_i, cell in enumerate(row_str):
                        for mes_nome, mes_num in meses_map.items():
                            if mes_nome in cell:
                                col_indices[mes_num] = col_i
                                found_months += 1
                    
                    if found_months > 3: # Se achou mais de 3 meses, é o cabeçalho
                        header_index = idx
                        break
                
                # Se achou cabeçalho e temos o ano, vamos extrair os valores
                if header_index != -1 and ano_pag:
                    # Varre as linhas abaixo do cabeçalho
                    for row in table[header_index+1:]:
                        row = [str(x) if x else "" for x in row]
                        
                        # Heurística para achar a linha do SALÁRIO BASE:
                        # Geralmente é a linha com valores consistentes > 1200
                        # Vamos iterar as colunas mapeadas
                        for mes_num, col_idx in col_indices.items():
                            if col_idx < len(row):
                                val_str = row[col_idx]
                                val = limpar_moeda(val_str)
                                
                                # Filtro: Ignora valores pequenos (descontos, auxílios menores)
                                # Ajuste este valor (1200) se o salário base for menor
                                if val > 1200: 
                                    data_str = f"01/{mes_num:02d}/{ano_pag}"
                                    dados.append({
                                        'Data': data_str,
                                        'Valor_Pago': val
                                    })

    if dados:
        df = pd.DataFrame(dados)
        df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y')
        # Remove duplicatas (caso pegue a linha de Totais ou repetições)
        # Mantém o maior valor encontrado para aquele mês (assumindo que seja o Vencimento/Subsídio)
        df = df.groupby('Data')['Valor_Pago'].max().reset_index()
        return df.sort_values('Data')
    
    return pd.DataFrame()

# --- ROBÔ CADASTRAL (MANTIDO E FUNCIONAL) ---
def extrair_classe(texto_codigo):
    texto = texto_codigo.upper()
    match = re.search(r'([A-G])40', texto)
    if match: return match.group(1)
    match = re.search(r'PCE([A-G])', texto)
    if match: return match.group(1)
    return None

def ler_ficha_cadastral(arquivos):
    historico = []
    reg_data = r'(\d{2}/\d{2}/\d{4})'
    reg_cod = r'(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)'

    for arq in arquivos:
        try:
            reader = PdfReader(arq)
            for page in reader.pages:
                txt = page.extract_text()
                # Tenta achar Data Promoção especificamente
                match_promo = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', txt)
                
                # Se não achar com label, pega a primeira data da página (fallback)
                data_ref = match_promo.group(1) if match_promo else None
                if not data_ref:
                    all_dates = re.findall(reg_data, txt)
                    if all_dates: data_ref = all_dates[0]
                
                codigos = re.findall(reg_cod, txt)
                
                if data_ref and codigos:
                    for cod in codigos:
                        cls = extrair_classe(cod)
                        if cls:
                            historico.append({'Data_Mudanca': pd.to_datetime(data_ref, dayfirst=True), 'Classe': cls})
                            break
        except Exception as e:
            st.warning(f"Erro ao ler PDF cadastral: {e}")

    if not historico: return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    return pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')

# --- CÁLCULO E RELATÓRIOS ---
def calcular(df_fin, df_car, base_a):
    df_fin = df_fin.sort_values('Data')
    df_car = df_car.sort_values('Data_Mudanca')
    
    # Cruzamento temporal (Backward)
    df = pd.merge_asof(df_fin, df_car, left_on='Data', right_on='Data_Mudanca', direction='backward')
    
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df['Indice'] = df['Classe'].map(mapa).fillna(0)
    df['Classe'] = df['Classe'].fillna('A') # Default se não achar
    
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

if st.sidebar.button("Limpar"):
    st.session_state.clear()
    st.experimental_rerun()

st.title("⚖️ Automação de Cálculo Jurídico")

# --- LÓGICA DE EXECUÇÃO ---
if file_fin and files_car:
    if st.button("🚀 Executar Cálculos"):
        with st.spinner("Processando..."):
            try:
                # 1. FINANCEIRO
                df_fin = pd.DataFrame()
                if file_fin.name.endswith('.pdf'): 
                    df_fin = ler_financeiro_pdf(file_fin)
                elif file_fin.name.endswith('.csv'): 
                    df_fin = pd.read_csv(file_fin)
                else: 
                    df_fin = pd.read_excel(file_fin)
                
                # Normalização (caso venha de Excel e não PDF)
                if not df_fin.empty and 'Valor_Pago' not in df_fin.columns:
                    c_dt = next((c for c in df_fin.columns if 'data' in c.lower()), 'Data')
                    c_val = next((c for c in df_fin.columns if 'valor' in c.lower() or 'pago' in c.lower()), 'Valor_Pago')
                    df_fin = df_fin.rename(columns={c_dt:'Data', c_val:'Valor_Pago'})
                    df_fin['Data'] = pd.to_datetime(df_fin['Data'])

                # 2. CARREIRA
                df_car = ler_ficha_cadastral(files_car)

                # 3. VALIDAÇÃO
                erro = ""
                if df_fin.empty: erro += "Não consegui ler os valores financeiros (Tente converter o PDF para Excel se persistir).\n"
                if df_car.empty: erro += "Não identifiquei as datas de promoção nos arquivos cadastrais.\n"
                
                if not erro:
                    res = calcular(df_fin, df_car, val_base)
                    st.session_state['res'] = res
                    st.session_state['processed'] = True
                    st.success("Sucesso!")
                else:
                    st.error(f"Erro:\n{erro}")
            
            except Exception as e:
                st.error(f"Erro crítico: {e}")

# --- RESULTADOS ---
if st.session_state.get('processed'):
    res = st.session_state['res']
    tot = res['Diferenca_Final'].sum()
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Meses", len(res))
    c2.metric("Classe Fim", res['Classe'].iloc[-1])
    c3.markdown(f"<div class='total-card'>TOTAL: R$ {format_br(tot)}</div>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["Gráficos", "Downloads"])
    with t1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='red')))
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido', line=dict(color='green', dash='dash')))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(res)
    with t2:
        c_x, c_p, c_t = st.columns(3)
        b_x = io.BytesIO()
        with pd.ExcelWriter(b_x, engine='xlsxwriter') as w: res.to_excel(w, index=False)
        c_x.download_button("Excel", b_x.getvalue(), f"{nome}.xlsx")
        
        b_p = gerar_pdf_laudo(res, nome, mat, "000", tot)
        c_p.download_button("Laudo PDF", b_p, f"{nome}.pdf")
        
        b_t = gerar_projefweb(res)
        c_t.download_button("Projefweb", b_t, f"{nome}.txt")

elif not file_fin:
    st.info("Aguardando arquivos...")
