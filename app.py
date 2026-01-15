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
# 1. CONFIGURAÇÃO E CSS
# ==============================================================================
st.set_page_config(
    page_title="Cálculo PC/AL - Profissional", 
    page_icon="⚖️", 
    layout="wide"
)

st.markdown("""
<style>
    .metric-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-top: 4px solid #3498db;
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
        font-weight: 600;
    }
    .total-card {
        background-color: #e8f8f5;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-top: 4px solid #27ae60;
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
    div.stButton > button:first-child {
        background-color: #2980b9;
        color: white;
        font-size: 18px;
        border-radius: 8px;
        padding: 12px 20px;
        border: none;
        width: 100%;
    }
    div.stButton > button:first-child:hover {
        background-color: #1a5276;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. ROBÔS DE EXTRAÇÃO (AGORA REFORÇADOS)
# ==============================================================================

def limpar_moeda(valor):
    """Converte 'R$ 1.000,00' ou '1000.00' para float."""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    
    # Remove aspas e espaços extras que podem vir do CSV
    s = str(valor).replace('"', '').replace("'", "").strip()
    s = s.replace('R$', '').replace(' ', '')
    
    # Detecção de formato: Se tiver ponto no final (ex: 776.60) e sem vírgula, assume decimal ponto
    # Caso contrário, assume padrão BR (remove ponto milhar, troca vírgula decimal)
    if '.' in s and ',' not in s and len(s.split('.')[-1]) == 2:
        pass # Já está em formato inglês provável
    else:
        s = s.replace('.', '').replace(',', '.') # Padrão BR
        
    try: return float(s)
    except: return 0.0

def ler_financeiro_horizontal(arquivo):
    """
    Lê PDF PC-AL com 3 Estratégias:
    1. Tabelas com linhas.
    2. Tabelas por espaçamento (sem linhas).
    3. Texto Bruto (formato CSV/Aspas).
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
            if not match_ano: match_ano = re.search(r'\b(20\d{2})\b', texto[:500])
            if not match_ano: continue
            ano_pag = int(match_ano.group(1))

            # ESTRATÉGIA 1 & 2: TABELAS (Grid e Text)
            tables = page.extract_tables() # Tenta com linhas
            if not tables:
                tables = page.extract_tables(dict(vertical_strategy="text", horizontal_strategy="text")) # Tenta por espaço
            
            sucesso_tabela = False
            if tables:
                for table in tables:
                    header_idx = -1
                    cols_map = {}
                    
                    # Achar cabeçalho
                    for i, row in enumerate(table):
                        row_up = [str(x).upper().replace('"','') if x else "" for x in row]
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
                        sucesso_tabela = True
                        for row in table[header_idx+1:]:
                            for c_idx, m_num in cols_map.items():
                                if c_idx < len(row):
                                    val = limpar_moeda(row[c_idx])
                                    if val > 1200: 
                                        dados.append({'Data': pd.to_datetime(f"{ano_pag}-{m_num:02d}-01"), 'Valor_Pago': val})

            # ESTRATÉGIA 3: TEXTO BRUTO (FALLBACK PARA SEU ARQUIVO ESPECÍFICO)
            # Seu arquivo parece ter linhas como: "Descrição","ValorJan","ValorFev"...
            if not sucesso_tabela:
                linhas = texto.split('\n')
                header_found = False
                cols_indices = {} # Mapeia índice do split -> mês
                
                for linha in linhas:
                    # Limpa aspas extras
                    linha_clean = linha.replace('","', '|').replace('"', '') 
                    parts = linha_clean.split('|')
                    
                    if not header_found:
                        # Tenta achar cabeçalho na linha
                        parts_up = [p.upper() for p in parts]
                        found = 0
                        temp_map = {}
                        for idx, p in enumerate(parts_up):
                            for m_nome, m_num in mapa_meses.items():
                                if m_nome in p:
                                    temp_map[idx] = m_num
                                    found += 1
                        if found >= 3:
                            header_found = True
                            cols_indices = temp_map
                    else:
                        # Processa valores
                        for idx, m_num in cols_indices.items():
                            if idx < len(parts):
                                val = limpar_moeda(parts[idx])
                                if val > 1200:
                                    dados.append({'Data': pd.to_datetime(f"{ano_pag}-{m_num:02d}-01"), 'Valor_Pago': val})

    if dados:
        df = pd.DataFrame(dados)
        df = df.groupby('Data')['Valor_Pago'].max().reset_index()
        return df.sort_values('Data')
    return pd.DataFrame()

def ler_cadastral(arquivos):
    """Lê datas de promoção nos PDFs"""
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
    if arquivo.name.endswith('.pdf'):
        return ler_financeiro_horizontal(arquivo)
    else:
        try:
            if arquivo.name.endswith('.csv'): df = pd.read_csv(arquivo)
            else: df = pd.read_excel(arquivo)
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
# 3. CÁLCULO
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

# ==============================================================================
# 4. EXPORTAÇÃO
# ==============================================================================
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
# 5. INTERFACE DO USUÁRIO
# ==============================================================================
st.sidebar.title("Painel de Controle")

files_fin = st.sidebar.file_uploader("1. Financeiro (PDF/Excel)", type=['pdf', 'xlsx', 'csv'], accept_multiple_files=False)
files_car = st.sidebar.file_uploader("2. Carreira (PDFs)", type=['pdf'], accept_multiple_files=True)

st.sidebar.markdown("---")
base_val = st.sidebar.number_input("Valor Base (Classe A)", 4000.00)
nome = st.sidebar.text_input("Nome", "Ironildo da Silva Costa")
mat = st.sidebar.text_input("Matrícula", "0065998-3")

if st.sidebar.button("🗑️ Limpar Sessão"):
    st.session_state.clear()
    st.experimental_rerun()

st.title("⚖️ Sistema de Cálculo Jurídico")

if files_fin and files_car:
    if st.button("🚀 EXECUTAR CÁLCULOS"):
        with st.spinner("Analisando estrutura dos arquivos..."):
            try:
                df_fin = processar_financeiro(files_fin)
                df_car = ler_cadastral(files_car)
                
                erro = ""
                if df_fin.empty: erro += "- Não consegui extrair dados financeiros (Tente converter o PDF para Excel).\n"
                if df_car.empty: erro += "- Promoções não encontradas nos PDFs cadastrais.\n"
                
                if not erro:
                    res = calcular(df_fin, df_car, base_val)
                    st.session_state['res'] = res
                    st.session_state['ok'] = True
                else:
                    st.error(f"Erro:\n{erro}")
            except Exception as e:
                st.error(f"Erro Crítico: {e}")

if st.session_state.get('ok'):
    res = st.session_state['res']
    tot = res['Diferenca_Final'].sum()
    classe = res['Classe'].iloc[-1]
    
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f"""<div class="metric-card"><div class="metric-label">Cliente</div><div class="metric-value">{nome.split()[0]}</div></div>""", unsafe_allow_html=True)
    with c2: st.markdown(f"""<div class="metric-card"><div class="metric-label">Meses</div><div class="metric-value">{len(res)}</div></div>""", unsafe_allow_html=True)
    with c3: st.markdown(f"""<div class="metric-card"><div class="metric-label">Classe Atual</div><div class="metric-value">{classe}</div></div>""", unsafe_allow_html=True)
    with c4: st.markdown(f"""<div class="total-card"><div class="total-label">Total Final</div><div class="total-value">R$ {fmt_br(tot)}</div></div>""", unsafe_allow_html=True)
    
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["Gráficos", "Dados Detalhados", "Baixar Relatórios"])
    
    with tab1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='#e74c3c')))
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido', line=dict(color='#27ae60', dash='dash')))
        st.plotly_chart(fig, use_container_width=True)
        
    with tab2:
        st.dataframe(res[['Data','Classe','Valor_Pago','Valor_Devido','Diferenca_Final']].style.format({
            'Valor_Pago': 'R$ {:,.2f}', 'Valor_Devido': 'R$ {:,.2f}', 'Diferenca_Final': 'R$ {:,.2f}'
        }))
        
    with tab3:
        c1, c2, c3 = st.columns(3)
        bx = io.BytesIO()
        with pd.ExcelWriter(bx, engine='xlsxwriter') as w: res.to_excel(w, index=False)
        c1.download_button("📊 Excel", bx.getvalue(), f"{nome}.xlsx")
        c2.download_button("📄 PDF", gerar_pdf(res, nome, mat, tot), f"{nome}.pdf")
        c3.download_button("📝 Projefweb", gerar_txt(res), f"{nome}.txt")
