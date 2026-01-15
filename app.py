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
# 1. CONFIGURAÇÃO E LAYOUT (RESTAURADO)
# ==============================================================================
st.set_page_config(
    page_title="Cálculo PC/AL", 
    page_icon="⚖️", 
    layout="wide"
)

# CSS Restaurado (Dashboard Visual)
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
# 2. FUNÇÕES DE LEITURA (AGORA LÊ EXCEL MATRICIAL)
# ==============================================================================

def limpar_moeda(valor):
    """Converte valores sujos em float"""
    if isinstance(valor, (int, float)): return float(valor)
    if not valor: return 0.0
    s = str(valor).replace('R$', '').replace(' ', '').strip()
    # Tenta detectar formato brasileiro vs americano
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'): # 1.000,00
            s = s.replace('.', '').replace(',', '.')
        else: # 1,000.00
            s = s.replace(',', '')
    elif ',' in s: # 1000,00
        s = s.replace(',', '.')
    
    try: return float(s)
    except: return 0.0

def ler_excel_matricial(arquivo):
    """
    Lê o Excel que tem o mesmo visual do PDF (Meses nas colunas).
    Lógica: Varre o arquivo linha a linha procurando blocos de anos.
    """
    # Lê tudo como string para facilitar a busca
    df_raw = pd.read_excel(arquivo, header=None, dtype=str)
    
    dados = []
    ano_atual = None
    
    mapa_meses = {
        'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6,
        'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
    }
    
    # 1. Encontrar onde estão os cabeçalhos de meses
    # Iterar linhas
    for idx, row in df_raw.iterrows():
        texto_linha = " ".join([str(x) for x in row.values if pd.notna(x)]).upper()
        
        # A. Tentar capturar o ANO (olhando para o texto da linha)
        # Procura "Ano Comp: 2016" ou apenas "2016" solto perto de "Ficha Financeira"
        match_ano = re.search(r'(?:ANO|EXERCICIO).*?(\d{4})', texto_linha)
        if match_ano:
            ano_atual = int(match_ano.group(1))
        
        # Se não achou ano na linha, mas a linha tem "JANEIRO", tenta olhar linhas anteriores
        if "JANEIRO" in texto_linha and "DEZEMBRO" in texto_linha:
            # Se ainda não temos ano, tenta olhar 5 linhas pra cima
            if not ano_atual:
                for i in range(1, 10):
                    if idx - i >= 0:
                        prev_row = " ".join([str(x) for x in df_raw.iloc[idx-i].values if pd.notna(x)])
                        m_ano = re.search(r'(\d{4})', prev_row)
                        if m_ano:
                            ano_atual = int(m_ano.group(1))
                            break
            
            # B. Identificar colunas dos meses nesta linha de cabeçalho
            cols_map = {}
            for col_idx, cell in enumerate(row):
                cell_str = str(cell).upper()
                for mes_nome, mes_num in mapa_meses.items():
                    if mes_nome in cell_str:
                        cols_map[col_idx] = mes_num
                        break
            
            # C. Varrer as linhas de DADOS logo abaixo deste cabeçalho
            # Vamos ler até encontrar outro cabeçalho ou muitas linhas vazias
            if ano_atual and cols_map:
                sub_idx = idx + 1
                while sub_idx < len(df_raw):
                    row_data = df_raw.iloc[sub_idx]
                    txt_data = " ".join([str(x) for x in row_data.values if pd.notna(x)]).upper()
                    
                    # Se achar outro cabeçalho, para este bloco
                    if "JANEIRO" in txt_data and "DEZEMBRO" in txt_data:
                        break
                        
                    # Filtro: Pegar linhas de Subsídio
                    # Pode estar como "126.00 SUBSIDIO" ou apenas "SUBSIDIO"
                    if "SUBSIDIO" in txt_data or "SUBSÍDIO" in txt_data:
                        for col_i, num_mes in cols_map.items():
                            if col_i < len(row_data):
                                val = limpar_moeda(row_data[col_i])
                                if val > 1200: # Filtro segurança
                                    dados.append({
                                        'Data': pd.to_datetime(f"{ano_atual}-{num_mes:02d}-01"),
                                        'Valor_Pago': val
                                    })
                    sub_idx += 1
                    if sub_idx - idx > 50: break # Segurança para não ler infinito

    if dados:
        df = pd.DataFrame(dados)
        df = df.groupby('Data')['Valor_Pago'].max().reset_index()
        return df.sort_values('Data')
    
    return pd.DataFrame()

def ler_financeiro_pdf_horizontal(arquivo):
    """Lê PDF (mantido caso o usuário use PDF)"""
    dados = []
    mapa_meses = {'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6, 'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12}
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            match_ano = re.search(r'(?:Ano Comp|Exercício|Ano)[:\s]*(\d{4})', texto, re.IGNORECASE)
            if not match_ano: match_ano = re.search(r'\b(20\d{2})\b', texto[:300])
            if not match_ano: continue
            ano_pag = int(match_ano.group(1))
            tables = page.extract_tables()
            for table in tables:
                header_idx = -1
                cols_indices = {}
                for i, row in enumerate(table):
                    row_str = [str(x).upper() if x else "" for x in row]
                    found = 0
                    temp = {}
                    for col_i, cell in enumerate(row_str):
                        for k, v in mapa_meses.items():
                            if k in cell:
                                temp[col_i] = v
                                found += 1
                    if found >= 3:
                        header_idx = i
                        cols_indices = temp
                        break
                if header_idx != -1:
                    for row in table[header_idx+1:]:
                        row = [str(x) if x else "" for x in row]
                        txt_row = " ".join(row).upper()
                        if "SUBSIDIO" in txt_row or "SUBSÍDIO" in txt_row:
                            for col_i, num_mes in cols_indices.items():
                                if col_i < len(row):
                                    val = limpar_moeda(row[col_i])
                                    if val > 1200:
                                        dados.append({'Data': pd.to_datetime(f"{ano_pag}-{num_mes:02d}-01"), 'Valor_Pago': val})
    if dados:
        df = pd.DataFrame(dados)
        df = df.groupby('Data')['Valor_Pago'].max().reset_index()
        return df.sort_values('Data')
    return pd.DataFrame()

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
                            historico.append({'Data_Mudanca': pd.to_datetime(dt_ref, dayfirst=True), 'Classe': cls})
                            break
        except: pass
    if not historico: return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    return pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')

# ==============================================================================
# 3. CÁLCULO E EXPORTAÇÃO
# ==============================================================================
def calcular(df_fin, df_car, base):
    df = pd.merge_asof(df_fin, df_car, left_on='Data', right_on='Data_Mudanca', direction='backward')
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
        self.set_font('Arial','B',14); self.cell(0,10,'Relatório de Cálculo PC/AL',0,1,'C'); self.ln(5)
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
# 4. INTERFACE RESTAURADA
# ==============================================================================
st.sidebar.title("Configurações")

# Upload Flexível
files_fin = st.sidebar.file_uploader("1. Financeiro (PDF ou Excel)", type=['pdf', 'xlsx'], accept_multiple_files=False)
files_car = st.sidebar.file_uploader("2. Carreira (PDFs)", type=['pdf'], accept_multiple_files=True)

st.sidebar.markdown("---")
base_val = st.sidebar.number_input("Base Classe A (R$)", 4000.00)
nome = st.sidebar.text_input("Nome do Servidor", "Ironildo da Silva Costa")
mat = st.sidebar.text_input("Matrícula", "0065998-3")

st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Limpar Tudo"):
    st.session_state.clear()
    st.experimental_rerun()

st.title("Cálculo PC/AL")

# LÓGICA DE EXECUÇÃO
if files_fin and files_car:
    if st.button("🚀 EXECUTAR CÁLCULOS"):
        with st.spinner("Processando..."):
            try:
                # 1. Leitura Inteligente (PDF ou Excel)
                if files_fin.name.endswith('.xlsx'):
                    df_fin = ler_excel_matricial(files_fin)
                else:
                    df_fin = ler_financeiro_pdf_horizontal(files_fin)
                
                # 2. Leitura Carreira
                df_car = ler_cadastral(files_car)
                
                # 3. Validação
                erro = ""
                if df_fin.empty: erro += "- Não consegui extrair 'Subsídio' do Financeiro. Verifique se o arquivo tem cabeçalho de meses e linha de Subsídio.\n"
                if df_car.empty: erro += "- Nenhuma promoção encontrada nas Fichas Cadastrais.\n"
                
                if not erro:
                    res = calcular(df_fin, df_car, base_val)
                    st.session_state['res'] = res
                    st.session_state['ok'] = True
                else:
                    st.error(f"Erro na Leitura:\n{erro}")
            except Exception as e:
                st.error(f"Erro Técnico: {e}")

# DASHBOARD RESTAURADO
if st.session_state.get('ok'):
    res = st.session_state['res']
    total = res['Diferenca_Final'].sum()
    classe_atual = res['Classe'].iloc[-1]
    meses_calc = len(res)
    
    st.markdown("---")
    
    # Cartões
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Cliente</div>
            <div class="metric-value">{nome.split()[0]}...</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Meses</div>
            <div class="metric-value">{meses_calc}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Classe Atual</div>
            <div class="metric-value">{classe_atual}</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="total-card">
            <div class="metric-label" style="color: #1e8449;">TOTAL FINAL</div>
            <div class="total-value">R$ {fmt_br(total)}</div>
        </div>""", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Abas
    tab1, tab2, tab3 = st.tabs(["📊 Análise Visual", "📋 Tabela de Dados", "💾 Exportação"])
    
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
        st.markdown("### Selecione o formato:")
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        
        # Excel
        buffer_xls = io.BytesIO()
        with pd.ExcelWriter(buffer_xls, engine='xlsxwriter') as writer: res.to_excel(writer, index=False)
        col_btn1.download_button("📊 Baixar Excel", buffer_xls.getvalue(), f"{nome}_calculo.xlsx", "application/vnd.ms-excel")
        
        # PDF
        pdf_bytes = gerar_pdf(res, nome, mat, total)
        col_btn2.download_button("📄 Baixar Laudo PDF", pdf_bytes, f"{nome}_laudo.pdf", "application/pdf")
        
        # Texto
        txt_bytes = gerar_txt(res)
        col_btn3.download_button("📝 Baixar Projefweb", txt_bytes, f"{nome}_projefweb.txt", "text/plain")

elif not files_fin:
    st.info("👈 Faça o upload dos arquivos na barra lateral.")
