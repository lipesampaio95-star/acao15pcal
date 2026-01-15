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
st.set_page_config(
    page_title="Cálculo PC/AL - Dashboard", 
    page_icon="⚖️", 
    layout="wide"
)

# --- DESIGN (CSS) ---
st.markdown("""
<style>
    /* Cartões de Métricas */
    .metric-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        border-left: 5px solid #3498db;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #2c3e50;
    }
    .metric-label {
        font-size: 14px;
        color: #7f8c8d;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Cartão de Total (Destaque) */
    .total-card {
        background-color: #d4efdf;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
        border-left: 5px solid #27ae60;
    }
    .total-value {
        font-size: 32px;
        font-weight: bold;
        color: #27ae60;
    }
    
    /* Botão Principal */
    div.stButton > button:first-child {
        background-color: #2980b9;
        color: white;
        font-size: 18px;
        border-radius: 8px;
        width: 100%;
        padding: 10px 0;
    }
    div.stButton > button:first-child:hover {
        background-color: #1a5276;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. ROBÔS DE LEITURA (BACKEND)
# ==============================================================================

def limpar_moeda(valor):
    """Converte 'R$ 5.000,00' para float 5000.0"""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    s = str(valor).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try: return float(s)
    except: return 0.0

def ler_financeiro_pdf_horizontal(arquivo):
    """Lê PDF onde meses estão nas colunas (Janeiro, Fevereiro...)"""
    dados = []
    mapa_meses = {
        'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6,
        'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
    }

    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            # Achar Ano
            match_ano = re.search(r'(?:Ano Comp|Exercício|Ano)[:\s]*(\d{4})', texto, re.IGNORECASE)
            if not match_ano: match_ano = re.search(r'\b(20\d{2})\b', texto[:300]) # Fallback
            
            if not match_ano: continue
            ano_pag = int(match_ano.group(1))

            tables = page.extract_tables()
            for table in tables:
                header_idx = -1
                cols_indices = {}
                
                # Achar linha de meses
                for i, row in enumerate(table):
                    row_str = [str(x).upper() if x else "" for x in row]
                    found = 0
                    temp_map = {}
                    for col_i, cell in enumerate(row_str):
                        for nome_mes, num_mes in mapa_meses.items():
                            if nome_mes in cell:
                                temp_map[col_i] = num_mes
                                found += 1
                                break
                    if found >= 3:
                        header_idx = i
                        cols_indices = temp_map
                        break
                
                # Extrair dados
                if header_idx != -1:
                    for row in table[header_idx+1:]:
                        row = [str(x) if x else "" for x in row]
                        for col_i, num_mes in cols_indices.items():
                            if col_i < len(row):
                                val = limpar_moeda(row[col_i])
                                if val > 1200: # Filtro Subsídio
                                    dados.append({
                                        'Data': pd.to_datetime(f"{ano_pag}-{num_mes:02d}-01"),
                                        'Valor_Pago': val
                                    })
    
    if dados:
        df = pd.DataFrame(dados)
        df = df.groupby('Data')['Valor_Pago'].max().reset_index() # Remove duplicatas pegando o maior valor
        return df.sort_values('Data')
    return pd.DataFrame()

def ler_financeiro_universal(arquivo):
    """Direciona para o leitor correto (PDF ou Excel)"""
    if arquivo.name.endswith('.pdf'):
        return ler_financeiro_pdf_horizontal(arquivo)
    else:
        # Excel ou CSV
        try:
            if arquivo.name.endswith('.csv'): df = pd.read_csv(arquivo)
            else: df = pd.read_excel(arquivo)
            
            # Normalizar colunas
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

def ler_cadastral(arquivos):
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
                if not dt_ref:
                    dts = re.findall(r'(\d{2}/\d{2}/\d{4})', txt)
                    if dts: dt_ref = dts[0]
                
                cods = re.findall(reg_cod, txt)
                if dt_ref and cods:
                    for c in cods:
                        # Extrair letra da classe
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

# ==============================================================================
# 2. CÁLCULO E EXPORTAÇÃO
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
# 3. INTERFACE (FRONTEND)
# ==============================================================================
st.sidebar.title("Configurações")

# Upload Flexível (Restaura funcionalidade Excel/CSV)
files_fin = st.sidebar.file_uploader("1. Financeiro (PDF, Excel, CSV)", type=['pdf', 'xlsx', 'csv'], accept_multiple_files=False)
files_car = st.sidebar.file_uploader("2. Carreira (PDFs)", type=['pdf'], accept_multiple_files=True)

# Parâmetros
st.sidebar.markdown("---")
base_val = st.sidebar.number_input("Base Classe A (R$)", 4000.00)
nome = st.sidebar.text_input("Nome do Servidor", "Ironildo da Silva Costa")
mat = st.sidebar.text_input("Matrícula", "0065998-3")

# Botão de Reset
st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Limpar Tudo"):
    st.session_state.clear()
    st.experimental_rerun()

# --- ÁREA PRINCIPAL ---
st.title("⚖️ Sistema de Cálculo Jurídico (PC/AL)")
st.markdown("Automação de cálculo de diferenças de classe (15%).")

# LÓGICA DE AÇÃO
if files_fin and files_car:
    if st.button("🚀 EXECUTAR CÁLCULOS"):
        with st.spinner("Lendo arquivos e cruzando dados..."):
            try:
                # 1. Leitura
                df_fin = ler_financeiro_universal(files_fin)
                df_car = ler_cadastral(files_car)
                
                # 2. Validação
                erro = ""
                if df_fin.empty: erro += "- Ficha Financeira vazia ou ilegível.\n"
                if df_car.empty: erro += "- Nenhuma promoção encontrada nas Fichas Cadastrais.\n"
                
                if not erro:
                    # 3. Cálculo
                    res = calcular(df_fin, df_car, base_val)
                    st.session_state['res'] = res
                    st.session_state['ok'] = True
                else:
                    st.error(f"Erro na Leitura:\n{erro}")
            except Exception as e:
                st.error(f"Erro Técnico: {e}")

# --- DASHBOARD CENTRAL (RESTAURADO) ---
if st.session_state.get('ok'):
    res = st.session_state['res']
    total = res['Diferenca_Final'].sum()
    classe_atual = res['Classe'].iloc[-1]
    meses_calc = len(res)
    
    st.markdown("---")
    
    # CARTÕES DE MÉTRICAS (Layout bonito)
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Cliente</div>
            <div class="metric-value">{nome.split()[0]}...</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Meses</div>
            <div class="metric-value">{meses_calc}</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Classe Atual</div>
            <div class="metric-value">{classe_atual}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c4:
        st.markdown(f"""
        <div class="total-card">
            <div class="metric-label" style="color: #1e8449;">TOTAL FINAL</div>
            <div class="total-value">R$ {fmt_br(total)}</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ABAS (Gráfico, Dados, Botões)
    tab1, tab2, tab3 = st.tabs(["📊 Análise Visual", "📋 Tabela de Dados", "💾 Exportação (Downloads)"])
    
    with tab1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='#e74c3c', width=2)))
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido', line=dict(color='#27ae60', width=2, dash='dash')))
        fig.update_layout(title="Evolução: Pago vs Devido", height=400)
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        st.dataframe(res[['Data', 'Classe', 'Valor_Pago', 'Valor_Devido', 'Diferenca_Final']].style.format({
            'Valor_Pago': 'R$ {:,.2f}', 
            'Valor_Devido': 'R$ {:,.2f}', 
            'Diferenca_Final': 'R$ {:,.2f}'
        }))
        
    with tab3:
        st.markdown("### Selecione o formato para baixar:")
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        
        # 1. EXCEL
        buffer_xls = io.BytesIO()
        with pd.ExcelWriter(buffer_xls, engine='xlsxwriter') as writer: res.to_excel(writer, index=False)
        col_btn1.download_button("📊 Baixar Excel", buffer_xls.getvalue(), f"{nome}_calculo.xlsx", "application/vnd.ms-excel")
        
        # 2. PDF
        pdf_bytes = gerar_pdf(res, nome, mat, total)
        col_btn2.download_button("📄 Baixar Laudo PDF", pdf_bytes, f"{nome}_laudo.pdf", "application/pdf")
        
        # 3. TEXTO
        txt_bytes = gerar_txt(res)
        col_btn3.download_button("📝 Baixar Projefweb", txt_bytes, f"{nome}_projefweb.txt", "text/plain")

elif not files_fin:
    st.info("👈 Comece fazendo o upload dos arquivos na barra lateral.")
