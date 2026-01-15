import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
import pdfplumber
import io
import re

# ==============================================================================
# 1. CONFIGURAÇÃO E CSS (BLINDAGEM DO LAYOUT)
# ==============================================================================
st.set_page_config(
    page_title="Cálculo PC/AL - Profissional", 
    page_icon="⚖️", 
    layout="wide"
)

# Aqui definimos o visual "imutável" do Dashboard
st.markdown("""
<style>
    /* Estilo dos Cards Superiores */
    .metric-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-top: 4px solid #3498db; /* Azul */
    }
    .metric-value {
        font-size: 26px;
        font-weight: 700;
        color: #2c3e50;
        margin-top: 5px;
    }
    .metric-label {
        font-size: 13px;
        color: #95a5a6;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 600;
    }
    
    /* Estilo do Card de Total (Destaque) */
    .total-card {
        background-color: #e8f8f5; /* Verde claro */
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-top: 4px solid #27ae60; /* Verde forte */
    }
    .total-value {
        font-size: 32px;
        font-weight: 800;
        color: #219150;
        margin-top: 5px;
    }
    .total-label {
        font-size: 14px;
        color: #27ae60;
        text-transform: uppercase;
        font-weight: bold;
    }
    
    /* Botão de Ação Principal */
    div.stButton > button:first-child {
        background-color: #2980b9;
        color: white;
        font-size: 18px;
        border-radius: 8px;
        padding: 12px 20px;
        border: none;
        transition: all 0.3s;
    }
    div.stButton > button:first-child:hover {
        background-color: #1a5276;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* Ajuste de tabelas */
    .stDataFrame { border: 1px solid #f0f2f6; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. ROBÔS DE EXTRAÇÃO (LÓGICA)
# ==============================================================================

def limpar_moeda(valor):
    """Converte R$ 1.000,00 para 1000.0"""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def ler_financeiro_horizontal(arquivo):
    """
    Lê PDF PC-AL (Horizontal).
    Procura: Ano no cabeçalho + Meses (Janeiro, Fevereiro...) nas colunas.
    """
    dados = []
    mapa_meses = {
        'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6,
        'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
    }

    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            
            # 1. Identificar Ano
            match_ano = re.search(r'(?:Ano Comp|Exercício|Ano)[:\s]*(\d{4})', texto, re.IGNORECASE)
            if not match_ano: match_ano = re.search(r'\b(20\d{2})\b', texto[:300]) # Fallback
            
            if not match_ano: continue
            ano_pag = int(match_ano.group(1))

            # 2. Varrer Tabelas
            tables = page.extract_tables()
            for table in tables:
                header_idx = -1
                cols_map = {}
                
                # Achar linha de cabeçalho
                for i, row in enumerate(table):
                    row_up = [str(x).upper() if x else "" for x in row]
                    found = 0
                    temp_map = {}
                    for c_idx, cell in enumerate(row_up):
                        for m_nome, m_num in mapa_meses.items():
                            if m_nome in cell:
                                temp_map[c_idx] = m_num
                                found += 1
                                break
                    if found >= 3:
                        header_idx = i
                        cols_map = temp_map
                        break
                
                # Extrair dados
                if header_idx != -1:
                    for row in table[header_idx+1:]:
                        for c_idx, m_num in cols_map.items():
                            if c_idx < len(row):
                                val = limpar_moeda(row[c_idx])
                                if val > 1200: # Filtro de Subsídio
                                    dados.append({
                                        'Data': pd.to_datetime(f"{ano_pag}-{m_num:02d}-01"),
                                        'Valor_Pago': val
                                    })
    
    if dados:
        df = pd.DataFrame(dados)
        # Agrupa pegando o maior valor do mês (evita duplicidade de rubricas)
        df = df.groupby('Data')['Valor_Pago'].max().reset_index()
        return df.sort_values('Data')
    return pd.DataFrame()

def ler_cadastral(arquivos):
    """Lê data de promoção nos PDFs cadastrais"""
    historico = []
    reg_cod = r'(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)'
    
    for arq in arquivos:
        try:
            reader = PdfReader(arq)
            for page in reader.pages:
                txt = page.extract_text() or ""
                
                # Data Promoção
                dt_match = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', txt)
                dt_ref = dt_match.group(1) if dt_match else None
                
                if not dt_ref: # Fallback
                    dts = re.findall(r'(\d{2}/\d{2}/\d{4})', txt)
                    if dts: dt_ref = dts[0]
                
                cods = re.findall(reg_cod, txt)
                if dt_ref and cods:
                    for c in cods:
                        # Extrai Classe (A-G)
                        cls = None
                        c_up = c.upper()
                        m1 = re.search(r'([A-G])40', c_up)
                        if m1: cls = m1.group(1)
                        else:
                            m2 = re.search(r'PCE([A-G])', c_up)
                            if m2: cls = m2.group(1)
                        
                        if cls:
                            historico.append({'Data_Mudanca': pd.to_datetime(dt_ref, dayfirst=True), 'Classe': cls})
                            break
        except: pass
        
    if not historico: return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    return pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')

def processar_financeiro(arquivo):
    """Hub que decide se lê PDF ou Excel/CSV"""
    if arquivo.name.endswith('.pdf'):
        return ler_financeiro_horizontal(arquivo)
    else:
        try:
            if arquivo.name.endswith('.csv'): df = pd.read_csv(arquivo)
            else: df = pd.read_excel(arquivo)
            
            # Normaliza colunas
            cols = [c.lower() for c in df.columns]
            c_dt = next((c for c in df.columns if 'data' in c.lower()), None)
            c_vl = next((c for c in df.columns if 'valor' in c.lower() or 'pago' in c.lower()), None)
            
            if c_dt and c_vl:
                df = df.rename(columns={c_dt: 'Data', c_vl: 'Valor_Pago'})
                df['Data'] = pd.to_datetime(df['Data'])
                df['Valor_Pago'] = df['Valor_Pago'].apply(limpar_moeda)
                return df[['Data', 'Valor_Pago']].dropna().sort_values('Data')
        except: pass
    return pd.DataFrame()

# ==============================================================================
# 3. CÁLCULO E EXPORTAÇÃO
# ==============================================================================
def calcular(df_f, df_c, base):
    df = pd.merge_asof(df_f, df_c, left_on='Data', right_on='Data_Mudanca', direction='backward')
    mapa = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5, 'G':6}
    df['Indice'] = df['Classe'].map(mapa).fillna(0)
    df['Classe'] = df['Classe'].fillna('A')
    
    df['Valor_Devido'] = base * (1.15 ** df['Indice'])
    df['Diferenca'] = df['Valor_Devido'] - df['Valor_Pago']
    df['Diferenca_Final'] = df['Diferenca'].apply(lambda x: x if x > 0 else 0)
    return df

def fmt_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class PDF(FPDF):
    def header(self):
        self.set_font('Arial','B',14); self.cell(0,10,'Relatório de Cálculo Pericial',0,1,'C'); self.ln(5)
    def footer(self):
        self.set_y(-15); self.set_font('Arial','I',8); self.cell(0,10,f'Pág {self.page_no()}',0,0,'C')

def gerar_pdf(df, nome, mat, tot):
    p = PDF(); p.add_page(); p.set_font('Arial','',10)
    p.cell(0,6,f"Servidor: {nome} | Matrícula: {mat}",0,1); p.ln()
    p.set_fill_color(220,255,220); p.set_font('Arial','B',12)
    p.cell(0,10,f"TOTAL: R$ {fmt_br(tot)}",1,1,'C',1); p.ln()
    p.set_font('Arial','B',9); w=[30,20,35,35,35]; h=['Data','Classe','Pago','Devido','Dif']
    for i,x in enumerate(h): p.cell(w[i],7,x,1,0,'C')
    p.ln(); p.set_font('Arial','',9)
    for _,r in df.iterrows():
        if r['Diferenca_Final']>0: p.set_font('Arial','B',9)
        else: p.set_font('Arial','',9)
        p.cell(w[0],6,r['Data'].strftime('%m/%Y'),1,0,'C')
        p.cell(w[1],6,str(r['Classe']),1,0,'C')
        p.cell(w[2],6,fmt_br(r['Valor_Pago']),1,0,'R')
        p.cell(w[3],6,fmt_br(r['Valor_Devido']),1,0,'R')
        p.cell(w[4],6,fmt_br(r['Diferenca_Final']),1,0,'R')
        p.ln()
    return p.output(dest='S').encode('latin-1','ignore')

def gerar_txt(df):
    s = io.StringIO()
    for _,r in df.iterrows():
        if r['Diferenca_Final'] > 0.01: s.write(f"{r['Data'].strftime('%m-%Y')}\tR$ {fmt_br(r['Diferenca_Final'])}\n")
    return s.getvalue().encode('utf-8')

# ==============================================================================
# 4. INTERFACE (FRONTEND)
# ==============================================================================
st.sidebar.title("Painel de Controle")

# Uploads
files_fin = st.sidebar.file_uploader("1. Financeiro (PDF/Excel)", type=['pdf', 'xlsx', 'csv'], accept_multiple_files=False)
files_car = st.sidebar.file_uploader("2. Carreira (PDFs)", type=['pdf'], accept_multiple_files=True)

# Parâmetros
st.sidebar.markdown("---")
base_val = st.sidebar.number_input("Valor Base (Classe A)", 4000.00)
nome = st.sidebar.text_input("Nome do Servidor", "Ironildo da Silva Costa")
mat = st.sidebar.text_input("Matrícula", "0065998-3")

# Reset
st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Limpar Sessão"):
    st.session_state.clear()
    st.experimental_rerun()

# --- CORPO PRINCIPAL ---
st.title("⚖️ Sistema de Cálculo Jurídico")
st.markdown("Cálculo automático de diferença de classes (15%) - PC/AL")

# BOTÃO DE EXECUÇÃO
if files_fin and files_car:
    if st.button("🚀 EXECUTAR CÁLCULOS"):
        with st.spinner("Processando arquivos..."):
            try:
                # 1. Leitura Inteligente
                df_fin = processar_financeiro(files_fin)
                df_car = ler_cadastral(files_car)
                
                # 2. Validação
                erro = ""
                if df_fin.empty: erro += "- Ficha Financeira não lida corretamente (Verifique layout).\n"
                if df_car.empty: erro += "- Nenhuma promoção encontrada nos PDFs.\n"
                
                if not erro:
                    # 3. Cálculo
                    res = calcular(df_fin, df_car, base_val)
                    st.session_state['res'] = res
                    st.session_state['ok'] = True
                else:
                    st.error(f"Erro:\n{erro}")
            except Exception as e:
                st.error(f"Erro Crítico: {e}")

# --- DASHBOARD DE RESULTADOS (BLINDADO) ---
if st.session_state.get('ok'):
    res = st.session_state['res']
    tot = res['Diferenca_Final'].sum()
    classe = res['Classe'].iloc[-1]
    
    st.markdown("---")
    
    # 1. CARTÕES
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""<div class="metric-card"><div class="metric-label">Cliente</div><div class="metric-value">{nome.split()[0]}</div></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="metric-card"><div class="metric-label">Meses</div><div class="metric-value">{len(res)}</div></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="metric-card"><div class="metric-label">Classe Atual</div><div class="metric-value">{classe}</div></div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""<div class="total-card"><div class="total-label">Total a Receber</div><div class="total-value">R$ {fmt_br(tot)}</div></div>""", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 2. ABAS DE DADOS
    tab1, tab2, tab3 = st.tabs(["📊 Gráficos", "📋 Tabela", "💾 Exportar"])
    
    with tab1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='#e74c3c')))
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido', line=dict(color='#27ae60', dash='dash')))
        fig.update_layout(height=400, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        st.dataframe(res[['Data','Classe','Valor_Pago','Valor_Devido','Diferenca_Final']].style.format({
            'Valor_Pago': 'R$ {:,.2f}', 'Valor_Devido': 'R$ {:,.2f}', 'Diferenca_Final': 'R$ {:,.2f}'
        }))
        
    with tab3:
        c1, c2, c3 = st.columns(3)
        # Excel
        bx = io.BytesIO()
        with pd.ExcelWriter(bx, engine='xlsxwriter') as w: res.to_excel(w, index=False)
        c1.download_button("📊 Baixar Excel", bx.getvalue(), f"{nome}.xlsx")
        
        # PDF
        bp = gerar_pdf(res, nome, mat, tot)
        c2.download_button("📄 Baixar Laudo", bp, f"{nome}.pdf")
        
        # TXT
        bt = gerar_txt(res)
        c3.download_button("📝 Baixar Projefweb", bt, f"{nome}.txt")

elif not files_fin:
    st.info("Insira os arquivos no menu lateral para começar.")
