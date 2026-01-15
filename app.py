import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
from pypdf import PdfReader
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
</style>
""", unsafe_allow_html=True)

# --- ROBÔ DE LEITURA DE PDF (NOVO) ---
def extrair_classe_do_codigo(codigo):
    """
    Tenta extrair a letra da classe (A-G) de códigos como 'PCEF440' ou 'AGPMNJ4G40'.
    Lógica: Procura letras A-G seguidas de '40' ou '440'.
    """
    codigo = codigo.upper()
    # Padrão 1: Códigos novos (ex: ...F40)
    match_novo = re.search(r'([A-G])40', codigo)
    if match_novo:
        return match_novo.group(1)
    
    # Padrão 2: Códigos antigos (ex: PCEE440 -> Classe E)
    match_antigo = re.search(r'PCE([A-G])', codigo)
    if match_antigo:
        return match_antigo.group(1)
        
    return None

def ler_ficha_cadastral(arquivos_pdf):
    """
    Lê múltiplos PDFs da Ficha Cadastral e extrai o histórico de promoções.
    Retorna um DataFrame com [Data_Mudanca, Classe].
    """
    historico = []
    
    # Regex para capturar data e o código do nível na mesma linha ou próximas
    # Exemplo no texto: "4 16/04/2020 PCEF440 - PC ESPECIAL..."
    regex_linha = r'(\d{2}/\d{2}/\d{4})\s+([A-Z0-9\-]+)'
    
    for arquivo in arquivos_pdf:
        try:
            reader = PdfReader(arquivo)
            for page in reader.pages:
                texto = page.extract_text()
                # Procurar todas as ocorrências de data + código
                matches = re.findall(regex_linha, texto)
                for data_str, codigo_sujo in matches:
                    classe = extrair_classe_do_codigo(codigo_sujo)
                    if classe:
                        historico.append({
                            'Data_Mudanca': pd.to_datetime(data_str, dayfirst=True),
                            'Classe': classe
                        })
        except Exception as e:
            st.error(f"Erro ao ler PDF {arquivo.name}: {e}")

    if not historico:
        return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    
    # Criar DataFrame, remover duplicatas e ordenar
    df = pd.DataFrame(historico)
    df = df.drop_duplicates().sort_values('Data_Mudanca')
    return df

# --- FUNÇÕES DE CÁLCULO E EXPORTAÇÃO (MANTIDAS) ---
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
    # Dados
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, f"  DADOS DO SERVIDOR", 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"  Nome: {nome} | Matrícula: {matricula} | CPF: {cpf}", 1, 1, 'L')
    pdf.ln(5)
    # Resumo
    pdf.set_fill_color(212, 239, 223)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 12, f"VALOR TOTAL APURADO: R$ {format_currency_br(total)}", 1, 1, 'C', fill=True)
    pdf.ln(10)
    # Tabela
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
    
    # Merge asof
    df_calc = pd.merge_asof(
        df_fin, df_car,
        left_on='Data', right_on='Data_Mudanca',
        direction='backward'
    )
    
    mapa = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6}
    df_calc['Indice'] = df_calc['Classe'].map(mapa)
    
    # Se não achou classe (período anterior à primeira data), assume A
    if df_calc['Indice'].isnull().any():
         st.warning("⚠️ Aviso: Existem pagamentos anteriores à primeira data de promoção encontrada. Assumindo Classe A para esse período.")
         df_calc['Indice'] = df_calc['Indice'].fillna(0) # Classe A default
         df_calc['Classe'] = df_calc['Classe'].fillna('A')

    df_calc['Valor_Devido'] = valor_base_a * (1.15 ** df_calc['Indice'])
    df_calc['Diferenca'] = df_calc['Valor_Devido'] - df_calc['Valor_Pago']
    df_calc['Diferenca_Final'] = df_calc['Diferenca'].apply(lambda x: x if x > 0 else 0)
    
    return df_calc

# --- APP PRINCIPAL ---
st.sidebar.title("Cálculo PC/AL")
st.sidebar.info("Agora com leitura automática de Fichas Cadastrais (PDF).")

# INPUT 1: FINANCEIRO
st.sidebar.header("1. Financeiro")
arquivo_fin = st.sidebar.file_uploader("Ficha Financeira (Excel/CSV)", type=['xlsx', 'csv'])

# INPUT 2: CARREIRA (PDF)
st.sidebar.header("2. Carreira (PDFs)")
arquivos_pdf = st.sidebar.file_uploader("Fichas Cadastrais (PDF)", type=['pdf'], accept_multiple_files=True)

# PARÂMETROS
st.sidebar.header("3. Parâmetros")
valor_base_a = st.sidebar.number_input("Valor Base (Classe A)", value=4000.00, step=100.00)
nome = st.sidebar.text_input("Nome", "SERVIDOR PC/AL")
matricula = st.sidebar.text_input("Matrícula", "000.000-0")
cpf = st.sidebar.text_input("CPF", "000.000.000-00")

st.title("⚖️ Automação de Cálculo: 15% Entre Classes")

# LÓGICA DE PROCESSAMENTO
if arquivo_fin and arquivos_pdf:
    try:
        # 1. Carregar Financeiro
        if arquivo_fin.name.endswith('.csv'):
            df_fin = pd.read_csv(arquivo_fin)
        else:
            df_fin = pd.read_excel(arquivo_fin)
            
        # Normalizar colunas financeiras (flexibilidade)
        cols_fin = [c for c in df_fin.columns]
        # Tenta achar coluna de data e valor
        col_data = next((c for c in cols_fin if 'data' in c.lower()), 'Data')
        col_valor = next((c for c in cols_fin if 'valor' in c.lower() or 'pago' in c.lower()), 'Valor_Pago')
        
        df_fin = df_fin.rename(columns={col_data: 'Data', col_valor: 'Valor_Pago'})
        df_fin['Data'] = pd.to_datetime(df_fin['Data'])
        
        # 2. Processar PDFs de Carreira
        with st.spinner('Lendo Fichas Cadastrais...'):
            df_car = ler_ficha_cadastral(arquivos_pdf)
            
        if df_car.empty:
            st.error("Não foi possível encontrar datas de promoção nos PDFs. Verifique se são Fichas Cadastrais válidas.")
        else:
            st.markdown(f"<div class='success-box'><b>Sucesso!</b> Encontradas {len(df_car)} mudanças de classe nos PDFs.</div>", unsafe_allow_html=True)
            with st.expander("Ver Histórico de Carreira Extraído"):
                st.dataframe(df_car)
            
            # 3. Calcular
            res = calcular(df_fin, df_car, valor_base_a)
            total = res['Diferenca_Final'].sum()
            
            # --- DASHBOARD ---
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><small>Cliente</small><br><b>{nome}</b></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><small>Meses Analisados</small><br><b>{len(res)}</b></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><small>Última Classe</small><br><b>{res['Classe'].iloc[-1]}</b></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='total-card'><small>TOTAL A RECEBER</small><br><span class='big-font'>R$ {format_currency_br(total)}</span></div>", unsafe_allow_html=True)
            
            st.markdown("---")
            
            # GRÁFICOS
            tab1, tab2 = st.tabs(["📊 Visualização", "📥 Exportação"])
            
            with tab1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='red')))
                fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido (Lei)', line=dict(color='green', dash='dash')))
                st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                col_dl1, col_dl2, col_dl3 = st.columns(3)
                
                # Excel
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='xlsxwriter') as writer:
                    res.to_excel(writer, index=False)
                col_dl1.download_button("📊 Baixar Excel", buffer_excel.getvalue(), f"{nome}_calculo.xlsx", "application/vnd.ms-excel")
                
                # PDF
                pdf_bytes = gerar_pdf(res, nome, matricula, cpf, total)
                col_dl2.download_button("📄 Baixar Laudo (PDF)", pdf_bytes, f"{nome}_laudo.pdf", "application/pdf")
                
                # TXT
                txt_bytes = gerar_txt_projefweb(res)
                col_dl3.download_button("📝 Baixar Projefweb (TXT)", txt_bytes, f"{nome}_projefweb.txt", "text/plain")

    except Exception as e:
        st.error(f"Erro no processamento: {str(e)}")
else:
    st.info("👈 Por favor, faça o upload da Ficha Financeira (Excel) e das Fichas Cadastrais (PDF) na barra lateral.")
