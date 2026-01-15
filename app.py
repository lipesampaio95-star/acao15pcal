import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re

# --- CONFIGURAÇÃO (NOME ORIGINAL) ---
st.set_page_config(
    page_title="Cálculo PC/AL", 
    page_icon="⚖️", 
    layout="wide"
)

# --- CSS ---
st.markdown("""
<style>
    .metric-card { background-color: #f8f9fa; border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #e9ecef; }
    .total-card { background-color: #d4efdf; border: 2px solid #27ae60; border-radius: 10px; padding: 15px; text-align: center; }
    div.stButton > button:first-child { background-color: #2E86C1; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
    div.stButton > button:first-child:hover { background-color: #1a5276; }
</style>
""", unsafe_allow_html=True)

# --- 1. LEITOR FINANCEIRO (ESPECIALISTA EM LAYOUT HORIZONTAL) ---
def limpar_moeda(valor):
    """Converte strings (R$ 5.000,00) em float (5000.0)"""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    # Remove tudo que não for número ou vírgula
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '')
    s = s.replace(',', '.') # Troca vírgula decimal por ponto
    try:
        return float(s)
    except:
        return 0.0

def ler_financeiro_pdf(arquivo):
    """
    Lê PDF onde os meses estão nas colunas (Janeiro, Fevereiro...).
    Estratégia:
    1. Acha o ANO na página.
    2. Acha a linha de CABEÇALHO (meses).
    3. Cruza as colunas.
    """
    dados = []
    # Mapa para identificar colunas (Upper case para garantir)
    mapa_meses = {
        'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6,
        'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
    }

    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            
            # A. DESCOBRIR O ANO DA PÁGINA
            # Procura "Ano Comp: 2016" ou "Exercicio 2016"
            match_ano = re.search(r'(?:Ano Comp|Exercício|Ano)[:\s]*(\d{4})', texto, re.IGNORECASE)
            
            # Fallback: Se não achou label, procura o primeiro ano (20xx) no topo da página
            if not match_ano:
                match_ano = re.search(r'\b(20\d{2})\b', texto[:300])
            
            if not match_ano:
                continue # Pula página se não tem ano seguro
                
            ano_pag = int(match_ano.group(1))

            # B. VARRER TABELAS
            tables = page.extract_tables()
            for table in tables:
                header_idx = -1
                cols_indices = {} # {indice_coluna: numero_mes}
                
                # 1. Achar a linha de cabeçalho
                for i, row in enumerate(table):
                    row_str = [str(x).upper() if x else "" for x in row]
                    
                    found_count = 0
                    temp_indices = {}
                    
                    for col_i, cell in enumerate(row_str):
                        # Verifica se a célula contém o nome de um mês
                        for nome_mes, num_mes in mapa_meses.items():
                            if nome_mes in cell:
                                temp_indices[col_i] = num_mes
                                found_count += 1
                                break # Achou um mês, pula pro próximo
                    
                    # Se achou pelo menos 3 meses na mesma linha, é o cabeçalho
                    if found_count >= 3:
                        header_idx = i
                        cols_indices = temp_indices
                        break
                
                # 2. Extrair valores
                if header_idx != -1:
                    # Varre linhas abaixo do cabeçalho
                    for row in table[header_idx+1:]:
                        row = [str(x) if x else "" for x in row]
                        
                        # Para cada coluna identificada como mês
                        for col_i, num_mes in cols_indices.items():
                            if col_i < len(row):
                                val_str = row[col_i]
                                valor = limpar_moeda(val_str)
                                
                                # FILTRO: Valores acima de 1200 (para pegar o subsídio e ignorar descontos/vales)
                                if valor > 1200:
                                    # Cria a data (Dia 1 do mês/ano encontrado)
                                    data = pd.to_datetime(f"{ano_pag}-{num_mes:02d}-01")
                                    dados.append({'Data': data, 'Valor_Pago': valor})

    if dados:
        df = pd.DataFrame(dados)
        # Agrupa por Data e pega o MAIOR valor (assumindo ser o Subsídio bruto)
        # Isso resolve duplicidade se houver linha de "Total" ou outras verbas
        df = df.groupby('Data')['Valor_Pago'].max().reset_index()
        return df.sort_values('Data')

    return pd.DataFrame()

# --- 2. LEITOR CADASTRAL (MANTIDO) ---
def extrair_classe(txt):
    txt = txt.upper()
    m = re.search(r'([A-G])40', txt) # Ex: F40
    if m: return m.group(1)
    m = re.search(r'PCE([A-G])', txt) # Ex: PCEF
    if m: return m.group(1)
    return None

def ler_ficha_cadastral(arquivos):
    historico = []
    reg_cod = r'(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)'
    
    for arq in arquivos:
        try:
            reader = PdfReader(arq)
            for page in reader.pages:
                txt = page.extract_text() or ""
                
                # Acha data promocao
                dt_match = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', txt)
                dt_ref = dt_match.group(1) if dt_match else None
                
                # Fallback data
                if not dt_ref:
                    dts = re.findall(r'(\d{2}/\d{2}/\d{4})', txt)
                    if dts: dt_ref = dts[0]
                
                cods = re.findall(reg_cod, txt)
                if dt_ref and cods:
                    for c in cods:
                        cls = extrair_classe(c)
                        if cls:
                            historico.append({'Data_Mudanca': pd.to_datetime(dt_ref, dayfirst=True), 'Classe': cls})
                            break
        except: pass
        
    if not historico: return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    return pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')

# --- 3. CÁLCULO ---
def calcular(df_fin, df_car, base):
    df = pd.merge_asof(df_fin, df_car, left_on='Data', right_on='Data_Mudanca', direction='backward')
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df['Indice'] = df['Classe'].map(mapa).fillna(0)
    df['Classe'] = df['Classe'].fillna('A')
    
    df['Valor_Devido'] = base * (1.15 ** df['Indice'])
    df['Diferenca'] = df['Valor_Devido'] - df['Valor_Pago']
    df['Diferenca_Final'] = df['Diferenca'].apply(lambda x: x if x > 0 else 0)
    return df

# --- 4. EXPORTAÇÃO ---
def format_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class PDF(FPDF):
    def header(self):
        self.set_font('Arial','B',14); self.cell(0,10,'Relatório de Cálculo',0,1,'C'); self.ln(5)
    def footer(self):
        self.set_y(-15); self.set_font('Arial','I',8); self.cell(0,10,f'Pág {self.page_no()}',0,0,'C')

def gera_pdf(df, nome, mat, tot):
    p = PDF(); p.add_page(); p.set_font('Arial','',10)
    p.cell(0,6,f"Servidor: {nome} | Matrícula: {mat}",0,1); p.ln()
    p.set_fill_color(220,255,220); p.set_font('Arial','B',12)
    p.cell(0,10,f"TOTAL: R$ {format_br(tot)}",1,1,'C',1); p.ln()
    p.set_font('Arial','B',9); w=[30,20,35,35,35]; h=['Data','Classe','Pago','Devido','Dif']
    for i,x in enumerate(h): p.cell(w[i],7,x,1,0,'C')
    p.ln(); p.set_font('Arial','',9)
    for _,r in df.iterrows():
        if r['Diferenca_Final']>0: p.set_font('Arial','B',9)
        else: p.set_font('Arial','',9)
        p.cell(w[0],6,r['Data'].strftime('%m/%Y'),1,0,'C')
        p.cell(w[1],6,str(r['Classe']),1,0,'C')
        p.cell(w[2],6,format_br(r['Valor_Pago']),1,0,'R')
        p.cell(w[3],6,format_br(r['Valor_Devido']),1,0,'R')
        p.cell(w[4],6,format_br(r['Diferenca_Final']),1,0,'R')
        p.ln()
    return p.output(dest='S').encode('latin-1','ignore')

def gera_txt(df):
    s = io.StringIO()
    for _,r in df.iterrows():
        if r['Diferenca_Final'] > 0.01: s.write(f"{r['Data'].strftime('%m-%Y')}\tR$ {format_br(r['Diferenca_Final'])}\n")
    return s.getvalue().encode('utf-8')

# --- 5. INTERFACE ---
st.sidebar.title("Cálculo PC/AL")

# Upload
files_fin = st.sidebar.file_uploader("1. Financeiro (PDF/Excel)", type=['pdf','xlsx'], accept_multiple_files=False)
files_car = st.sidebar.file_uploader("2. Carreira (PDFs)", type=['pdf'], accept_multiple_files=True)
base_val = st.sidebar.number_input("Base Classe A (R$)", 4000.0)
nome = st.sidebar.text_input("Nome", "Servidor")
