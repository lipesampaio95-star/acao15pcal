import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Cálculo PC/AL - Seguro", page_icon="🚔", layout="wide")
st.markdown("""
<style>
    .metric-card { background-color: #f8f9fa; border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #e9ecef; }
    .total-card { background-color: #d4efdf; border: 2px solid #27ae60; border-radius: 10px; padding: 15px; text-align: center; }
    div.stButton > button:first-child { background-color: #2E86C1; color: white; font-size: 18px; width: 100%; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# --- 1. FUNÇÕES AUXILIARES ---
def limpar_moeda(valor):
    """Converte '5.200,00' ou 'R$ 5.200,00' para float 5200.0"""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

# --- 2. ROBÔ FINANCEIRO (ESPECIALISTA EM LAYOUT HORIZONTAL) ---
def ler_financeiro_pdf(arquivo):
    """
    Lê o PDF da PC-AL onde os meses estão nas colunas (Janeiro, Fevereiro...).
    """
    dados = []
    # Mapeia nomes das colunas para números dos meses
    # Usamos parte do nome para evitar erros de OCR/Leitura (ex: "ANEIRO" pega Janeiro)
    mapa_meses = {
        'ANEIRO': 1, 'EVEREIRO': 2, 'ARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6, 'UNHO': 6,
        'JULHO': 7, 'ULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
    }

    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto_pag = page.extract_text() or ""
            
            # A. Descobrir o ANO desta página
            # Procura "Ano Comp: 2016" ou "Exercicio: 2016"
            match_ano = re.search(r'(?:Ano Comp|Exercício)[:\s]*(\d{4})', texto_pag, re.IGNORECASE)
            if not match_ano:
                # Tenta achar um ano solto no cabeçalho
                match_ano = re.search(r'\b(20\d{2})\b', texto_pag[:300])
            
            if not match_ano: continue # Pula página se não achar ano
            ano_atual = int(match_ano.group(1))

            # B. Extrair Tabelas
            tables = page.extract_tables()
            for table in tables:
                header_index = -1
                cols_indices = {} # Guarda onde está cada mês {indice_coluna: numero_mes}
                
                # 1. Identificar a linha de cabeçalho
                for i, row in enumerate(table):
                    row_str = [str(x).upper() if x else "" for x in row]
                    found = 0
                    temp_indices = {}
                    
                    for col_idx, cell in enumerate(row_str):
                        for k, v in mapa_meses.items():
                            if k in cell:
                                temp_indices[col_idx] = v
                                found += 1
                                break # Achou mês nesta célula, para de testar outros meses
                    
                    if found >= 3: # Se a linha tem pelo menos 3 meses, é o cabeçalho
                        header_index = i
                        cols_indices = temp_indices
                        break
                
                # 2. Ler os dados abaixo do cabeçalho
                if header_index != -1:
                    for row in table[header_index+1:]:
                        row = [str(x) if x else "" for x in row]
                        
                        for col_idx, mes_num in cols_indices.items():
                            if col_idx < len(row):
                                val_str = row[col_idx]
                                valor = limpar_moeda(val_str)
                                
                                # FILTRO: Ignora valores menores que 1200 (descontos, vale, etc)
                                # Assim garantimos pegar o Subsídio/Vencimento
                                if valor > 1200:
                                    dados.append({
                                        'Data': pd.to_datetime(f"{ano_atual}-{mes_num:02d}-01"),
                                        'Valor_Pago': valor
                                    })

    if dados:
        df = pd.DataFrame(dados)
        # Agrupa por data e pega o MAIOR valor encontrado no mês (O Subsídio)
        df = df.groupby('Data')['Valor_Pago'].max().reset_index()
        return df.sort_values('Data')
    
    return pd.DataFrame()

# --- 3. ROBÔ CADASTRAL (MANTIDO) ---
def extrair_classe(txt):
    txt = txt.upper()
    m = re.search(r'([A-G])40', txt) # Padrão novo (ex: F40)
    if m: return m.group(1)
    m = re.search(r'PCE([A-G])', txt) # Padrão antigo (ex: PCEF)
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
                
                # Tenta achar Data Promoção
                match_dt = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', txt)
                dt_ref = match_dt.group(1) if match_dt else None
                
                # Fallback: Se não tem label, pega a primeira data válida da página
                if not dt_ref:
                    all_dts = re.findall(r'(\d{2}/\d{2}/\d{4})', txt)
                    if all_dts: dt_ref = all_dts[0]
                
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

# --- 4. CÁLCULO ---
def calcular(df_fin, df_car, base):
    df = pd.merge_asof(df_fin, df_car, left_on='Data', right_on='Data_Mudanca', direction='backward')
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df['Indice'] = df['Classe'].map(mapa).fillna(0)
    df['Classe'] = df['Classe'].fillna('A')
    
    df['Valor_Devido'] = base * (1.15 ** df['Indice'])
    df['Diferenca'] = df['Valor_Devido'] - df['Valor_Pago']
    df['Diferenca_Final'] = df['Diferenca'].apply(lambda x: x if x > 0 else 0)
    return df

# --- 5. EXPORTAÇÃO ---
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

# --- 6. APP VISUAL ---
st.sidebar.title("Calculadora PC/AL")
st.sidebar.info("Sistema Simplificado e Estável (Sem OCR)")

files_fin = st.sidebar.file_uploader("1. Financeiro (PDF/Excel)", type=['pdf','xlsx'], accept_multiple_files=False)
files_car = st.sidebar.file_uploader("2. Carreira (PDFs)", type=['pdf'], accept_multiple_files=True)
base_val = st.sidebar.number_input("Base Classe A (R$)", 4000.0)
nome = st.sidebar.text_input("Nome", "Servidor")
mat = st.sidebar.text_input("Matrícula", "000000")

if st.sidebar.button("Reset"): st.session_state.clear(); st.experimental_rerun()

st.title("Hub de Cálculo PC/AL")

if files_fin and files_car:
    if st.button("🚀 Executar Cálculos"):
        with st.spinner("Processando..."):
            try:
                # 1. Financeiro
                df_fin = pd.DataFrame()
                if files_fin.name.endswith('.pdf'):
                    df_fin = ler_financeiro_pdf(files_fin)
                else:
                    df_fin = pd.read_excel(files_fin)
                    # Normalização básica de Excel
                    c_dt = next((c for c in df_fin.columns if 'data' in c.lower()), None)
                    c_vl = next((c for c in df_fin.columns if 'valor' in c.lower()), None)
                    if c_dt and c_vl:
                         df_fin = df_fin.rename(columns={c_dt:'Data', c_vl:'Valor_Pago'})
                         df_fin['Data'] = pd.to_datetime(df_fin['Data'])
                
                # 2. Carreira
                df_car = ler_ficha_cadastral(files_car)
                
                # 3. Validar
                if df_fin.empty:
                    st.error("Não encontrei valores na Ficha Financeira. (Verifique se é o PDF padrão com meses nas colunas)")
                elif df_car.empty:
                    st.error("Não encontrei promoções nas Fichas Cadastrais.")
                else:
                    res = calcular(df_fin, df_car, base_val)
                    st.session_state['res'] = res
                    st.session_state['ok'] = True
                    st.success("Calculado com sucesso!")
                    
            except Exception as e:
                st.error(f"Erro: {e}")

if st.session_state.get('ok'):
    res = st.session_state['res']
    tot = res['Diferenca_Final'].sum()
    
    c1, c2 = st.columns(2)
    c1.metric("Meses Calculados", len(res))
    c2.markdown(f"<div class='total-card'>TOTAL: R$ {format_br(tot)}</div>", unsafe_allow_html=True)
    
    t1, t2 = st.tabs(["Dados", "Baixar"])
    with t1:
        st.dataframe(res)
        st.plotly_chart(px.line(res, x='Data', y=['Valor_Pago', 'Valor_Devido']), use_container_width=True)
    with t2:
        c_p, c_x, c_t = st.columns(3)
        c_p.download_button("PDF Laudo", gera_pdf(res, nome, mat, tot), f"{nome}.pdf")
        
        bx = io.BytesIO()
        with pd.ExcelWriter(bx, engine='xlsxwriter') as w: res.to_excel(w, index=False)
        c_x.download_button("Excel", bx.getvalue(), f"{nome}.xlsx")
        
        c_t.download_button("Projefweb", gera_txt(res), f"{nome}.txt")
