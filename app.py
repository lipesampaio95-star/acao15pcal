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
    page_title="Cálculo PC/AL - Automático", 
    page_icon="🚔",
    layout="wide"
)

# --- CSS E ESTILO ---
st.markdown("""
<style>
    .big-font { font-size:24px !important; font-weight: bold; color: #2E86C1; }
    .metric-card { background-color: #f8f9fa; border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #e9ecef; }
    .total-card { background-color: #d4efdf; border: 2px solid #27ae60; border-radius: 10px; padding: 15px; text-align: center; }
    .success-box { background-color: #d4efdf; padding: 10px; border-radius: 5px; border-left: 5px solid #27ae60; }
    
    /* Estilo do Botão de Executar */
    div.stButton > button:first-child {
        background-color: #2E86C1;
        color: white;
        font-size: 18px;
        font-weight: bold;
        width: 100%;
        padding: 10px;
        border-radius: 8px;
    }
    div.stButton > button:first-child:hover {
        background-color: #1a5276;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES DE LEITURA (ROBÔS) ---

def limpar_moeda(valor_str):
    """Converte strings financeiras sujas em float."""
    if isinstance(valor_str, (int, float)): return float(valor_str)
    if not valor_str: return 0.0
    # Remove símbolos, pontos de milhar e espaços
    limpo = str(valor_str).replace('R$', '').replace('.', '').replace(' ', '')
    # Troca vírgula decimal por ponto
    limpo = limpo.replace(',', '.')
    try:
        return float(limpo)
    except:
        return 0.0

def ler_financeiro_pdf(arquivo):
    """Lê tabelas de Ficha Financeira via pdfplumber."""
    dados = []
    with pdfplumber.open(arquivo) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    row = [x if x else "" for x in row]
                    
                    data_encontrada = None
                    valor_encontrado = None
                    
                    for cell in row:
                        cell_clean = str(cell).replace('\n', ' ').strip()
                        
                        # Procura Data (MM/AAAA)
                        if not data_encontrada:
                            match_data = re.search(r'\b(\d{2}/\d{4})\b', cell_clean)
                            if match_data:
                                data_encontrada = match_data.group(1)
                                continue
                        
                        # Procura Valor (R$ X.XXX,XX)
                        # Filtro: Ignora valores menores que 1200 para não pegar descontos
                        if re.match(r'^R?\s?[\d\.]+,[\d]{2}$', cell_clean):
                            v = limpar_moeda(cell_clean)
                            if v > 1200: 
                                valor_encontrado = v
                    
                    if data_encontrada and valor_encontrado:
                        dados.append({'Data': data_encontrada, 'Valor_Pago': valor_encontrado})
    
    if dados:
        df = pd.DataFrame(dados)
        df['Data'] = pd.to_datetime(df['Data'], format='%m/%Y', errors='coerce')
        return df.dropna().sort_values('Data')
    
    return pd.DataFrame()

def extrair_classe_do_codigo(codigo):
    """Extrai A, B, C... de códigos como AGPMNJ4F40."""
    codigo = codigo.upper()
    match_novo = re.search(r'([A-G])40', codigo)
    if match_novo: return match_novo.group(1)
    match_antigo = re.search(r'PCE([A-G])', codigo)
    if match_antigo: return match_antigo.group(1)
    return None

def ler_ficha_cadastral(arquivos_pdf):
    """Lê Fichas Cadastrais via pypdf."""
    historico = []
    regex_codigo = r'(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)'
    
    for arquivo in arquivos_pdf:
        try:
            reader = PdfReader(arquivo)
            for page in reader.pages:
                texto = page.extract_text()
                matches_codigos = re.findall(regex_codigo, texto)
                match_data_promo = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', texto)
                
                if matches_codigos and match_data_promo:
                    data = match_data_promo.group(1)
                    # Assume o primeiro código válido encontrado na página
                    for cod in matches_codigos:
                        classe = extrair_classe_do_codigo(cod)
                        if classe:
                            historico.append({
                                'Data_Mudanca': pd.to_datetime(data, dayfirst=True),
                                'Classe': classe
                            })
                            break 
        except Exception as e:
            st.error(f"Erro no PDF {arquivo.name}: {e}")

    if not historico: return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    return pd.DataFrame(historico).drop_duplicates().sort_values('Data_Mudanca')

# --- FUNÇÕES DE CÁLCULO E EXPORTAÇÃO ---

def format_currency_br(value):
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Relatório de Cálculo Pericial', 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.cell(0, 5, 'Objeto: Diferença de Classes (15%) - PC/AL', 0, 1, 'C')
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def gerar_pdf(df, nome, matricula, cpf, total):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, f"  DADOS DO SERVIDOR", 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"  Nome: {nome} | Matrícula: {matricula} | CPF: {cpf}", 1, 1, 'L')
    pdf.ln(5)
    pdf.set_fill_color(212, 239, 223)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 12, f"VALOR TOTAL APURADO: R$ {format_currency_br(total)}", 1, 1, 'C', fill=True)
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 9)
    w = [30, 20, 35, 35, 35] 
    headers = ['Mês/Ano', 'Classe', 'Pago (R$)', 'Devido (R$)', 'Diferença (R$)']
    for i, h in enumerate(headers): pdf.cell(w[i], 7, h, 1, 0, 'C')
    pdf.ln()
    pdf.set_font('Arial', '', 9)
    for _, row in df.iterrows():
        data_str = row['Data'].strftime('%m/%Y')
        val_pago = format_currency_br(row['Valor_Pago'])
        val_devido = format_currency_br(row['Valor_Devido'])
        val_dif = format_currency_br(row['Diferenca_Final'])
        pdf.cell(w[0], 6, data_str, 1, 0, 'C')
        pdf.cell(w[1], 6, str(row['Classe']), 1, 0, 'C')
        pdf.cell(w[2], 6, val_pago, 1, 0, 'R')
        pdf.cell(w[3], 6, val_devido, 1, 0, 'R')
        if row['Diferenca_Final'] > 0:
            pdf.set_font('Arial', 'B', 9)
            pdf.cell(w[4], 6, val_dif, 1, 0, 'R')
            pdf.set_font('Arial', '', 9)
        else:
            pdf.cell(w[4], 6, val_dif, 1, 0, 'R')
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'ignore')

def gerar_txt_projefweb(df):
    output = io.StringIO()
    for _, row in df.iterrows():
        if row['Diferenca_Final'] > 0.01:
            data_fmt = row['Data'].strftime('%m-%Y')
            valor_fmt = f"R$ {format_currency_br(row['Diferenca_Final'])}"
            output.write(f"{data_fmt}\t{valor_fmt}\n")
    return output.getvalue().encode('utf-8')

def calcular(df_fin, df_car, valor_base_a):
    df_fin = df_fin.sort_values('Data')
    df_car = df_car.sort_values('Data_Mudanca')
    
    df_calc = pd.merge_asof(
        df_fin, df_car,
        left_on='Data', right_on='Data_Mudanca',
        direction='backward'
    )
    
    mapa = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}
    df_calc['Indice'] = df_calc['Classe'].map(mapa)
    
    if df_calc['Indice'].isnull().any():
         df_calc['Indice'] = df_calc['Indice'].fillna(0)
         df_calc['Classe'] = df_calc['Classe'].fillna('A')

    df_calc['Valor_Devido'] = valor_base_a * (1.15 ** df_calc['Indice'])
    df_calc['Diferenca'] = df_calc['Valor_Devido'] - df_calc['Valor_Pago']
    df_calc['Diferenca_Final'] = df_calc['Diferenca'].apply(lambda x: x if x > 0 else 0)
    
    return df_calc

# --- APP PRINCIPAL (INTERFACE) ---
st.sidebar.title("Cálculo PC/AL")
st.sidebar.info("Sistema de Triagem Automática (PDF+Excel)")

# 1. Inputs de Arquivos
st.sidebar.header("1. Documentos")
arquivo_fin = st.sidebar.file_uploader("Ficha Financeira (PDF/Excel)", type=['xlsx', 'csv', 'pdf'])
arquivos_pdf = st.sidebar.file_uploader("Fichas Cadastrais (PDFs)", type=['pdf'], accept_multiple_files=True)

# 2. Parâmetros
st.sidebar.header("2. Dados do Processo")
valor_base_a = st.sidebar.number_input("Valor Base (Classe A)", value=4000.00, step=100.00)
nome = st.sidebar.text_input("Nome", "SERVIDOR PC/AL")
matricula = st.sidebar.text_input("Matrícula", "000.000-0")
cpf = st.sidebar.text_input("CPF", "000.000.000-00")

# 3. Botão de Reset
if st.sidebar.button("🗑️ Limpar Sessão"):
    for key in st.session_state.keys():
        del st.session_state[key]
    st.experimental_rerun()

# --- CORPO PRINCIPAL ---
st.title("⚖️ Automação de Cálculos Judiciais")

# =========================================================
# LÓGICA DO BOTÃO "EXECUTAR" E SESSION STATE
# =========================================================

# Só mostra o botão se tiver arquivos carregados
if arquivo_fin and arquivos_pdf:
    if st.button("🚀 Executar Cálculos"):
        with st.spinner('Processando arquivos e cruzando dados...'):
            try:
                # 1. Leitura do Financeiro
                df_fin = pd.DataFrame()
                if arquivo_fin.name.endswith('.pdf'):
                    df_fin = ler_financeiro_pdf(arquivo_fin)
                elif arquivo_fin.name.endswith('.csv'):
                    df_fin = pd.read_csv(arquivo_fin)
                else:
                    df_fin = pd.read_excel(arquivo_fin)
                
                # Normalização de colunas
                if not df_fin.empty:
                    cols = [c for c in df_fin.columns]
                    col_data = next((c for c in cols if 'data' in c.lower()), 'Data')
                    col_valor = next((c for c in cols if 'valor' in c.lower() or 'pago' in c.lower()), 'Valor_Pago')
                    df_fin = df_fin.rename(columns={col_data: 'Data', col_valor: 'Valor_Pago'})
                    df_fin['Data'] = pd.to_datetime(df_fin['Data'])

                # 2. Leitura da Carreira (PDFs)
                df_car = ler_ficha_cadastral(arquivos_pdf)
                
                # 3. Execução do Cálculo
                if not df_fin.empty and not df_car.empty:
                    res = calcular(df_fin, df_car, valor_base_a)
                    total = res['Diferenca_Final'].sum()
                    
                    # SALVAR NO ESTADO (CRUCIAL!)
                    st.session_state['resultado'] = res
                    st.session_state['total'] = total
                    st.session_state['processado'] = True
                    st.success("Cálculo finalizado com sucesso!")
                else:
                    st.error("Erro: Não foi possível extrair dados válidos. Verifique a qualidade dos PDFs.")
                    
            except Exception as e:
                st.error(f"Erro no processamento: {e}")

# =========================================================
# EXIBIÇÃO DOS RESULTADOS (PERSISTENTE)
# =========================================================

if st.session_state.get('processado'):
    res = st.session_state['resultado']
    total = st.session_state['total']
    
    # Dashboard
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"<div class='metric-card'><small>Cliente</small><br><b>{nome}</b></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><small>Registros</small><br><b>{len(res)} meses</b></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><small>Classe Atual</small><br><b>{res['Classe'].iloc[-1]}</b></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='total-card'><small>TOTAL A RECEBER</small><br><span class='big-font'>R$ {format_currency_br(total)}</span></div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["📊 Gráficos e Tabela", "📥 Downloads Oficiais"])
    
    with tab1:
        st.subheader("Evolução Financeira")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='red')))
        fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido (Lei)', line=dict(color='green', dash='dash')))
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("Ver Tabela Detalhada"):
            st.dataframe(res[['Data', 'Classe', 'Valor_Pago', 'Valor_Devido', 'Diferenca_Final']].style.format({
                'Valor_Pago': 'R$ {:,.2f}', 'Valor_Devido': 'R$ {:,.2f}', 'Diferenca_Final': 'R$ {:,.2f}'
            }))

    with tab2:
        st.subheader("Exportar Relatórios")
        c_dl1, c_dl2, c_dl3 = st.columns(3)
        
        # 1. EXCEL
        buffer_excel = io.BytesIO()
        with pd.ExcelWriter(buffer_excel, engine='xlsxwriter') as writer: res.to_excel(writer, index=False)
        c_dl1.download_button("📊 Planilha Excel", buffer_excel.getvalue(), f"{nome}_calculo.xlsx", "application/vnd.ms-excel")
        
        # 2. PDF (LAUDO)
        pdf_bytes = gerar_pdf(res, nome, matricula, cpf, total)
        c_dl2.download_button("📄 Laudo PDF", pdf_bytes, f"{nome}_laudo.pdf", "application/pdf")
        
        # 3. PROJEFWEB (TXT)
        txt_bytes = gerar_txt_projefweb(res)
        c_dl3.download_button("📝 Arq. Projefweb", txt_bytes, f"{nome}_projefweb.txt", "text/plain")

elif not arquivo_fin:
    st.info("👋 Olá! Faça o upload dos arquivos na barra lateral para começar.")
