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
    Identifica a classe (A-G) dentro dos códigos complexos da PC-AL.
    Exemplos encontrados nos seus arquivos:
    - 'PCEE440' -> Classe E
    - 'PCEF440' -> Classe F
    - 'NV08336 - AGPMNE4F40' -> Classe F
    - 'AGPMNJ4G40' -> Classe G
    """
    codigo = codigo.upper()
    
    # 1. Tenta padrão novo (Letra seguida de 40, ex: F40, G40)
    # Ignora 'J4' ou 'N4' se aparecerem antes, foca na letra da classe + carga horária
    match_novo = re.search(r'([A-G])40', codigo)
    if match_novo:
        return match_novo.group(1)
    
    # 2. Tenta padrão antigo (PCE + Letra, ex: PCEE, PCEF)
    match_antigo = re.search(r'PCE([A-G])', codigo)
    if match_antigo:
        return match_antigo.group(1)
        
    return None

def ler_ficha_cadastral(arquivos_pdf):
    """
    Lê os PDFs, procura 'Data Promoção' e o código de nível, e retorna o histórico.
    """
    historico = []
    
    # Regex ajustada para o layout do seu PDF:
    # Procura uma data (XX/XX/XXXX) e, na mesma 'zona' de texto extraído, um código alfanumérico.
    # O pypdf as vezes extrai o texto com quebras, então varremos o texto procurando padrões.
    regex_data = r'(\d{2}/\d{2}/\d{4})'
    # Regex genérica para capturar os códigos de classe que vimos (PCE... ou AGP...)
    regex_codigo = r'(PCE[A-Z]\d+|AGP[A-Z0-9]+|NV\d+.*?[A-Z]40)'
    
    for arquivo in arquivos_pdf:
        try:
            reader = PdfReader(arquivo)
            for page in reader.pages:
                texto = page.extract_text()
                
                # Estratégia: Encontrar todas as datas de promoção mencionadas
                # No seu PDF, o campo é "Data Promoção" seguido do valor.
                # Como o texto pode vir quebrado, vamos procurar linhas que contenham datas
                # e códigos de classe próximos.
                
                # Vamos simplificar: extrair todas as datas e códigos da página
                # e assumir que a 'Data Promoção' é a que está vinculada ao código de Nível.
                # No layout, eles estão lado a lado ou linha abaixo.
                
                matches_data = re.findall(regex_data, texto)
                matches_codigos = re.findall(regex_codigo, texto)
                
                # Se achou código e data na página, tenta parear (heurística simples)
                # O ideal é que a página do mês X tem o status do mês X.
                # Mas o campo "Data Promoção" é histórico (mostra a última).
                # Então, se encontrarmos "16/04/2020" e "Classe F", sabemos que essa mudança ocorreu.
                
                for cod in matches_codigos:
                    classe = extrair_classe_do_codigo(cod)
                    if classe and matches_data:
                        # Pega a data mais provável de ser a de promoção (geralmente a primeira ou a que se repete)
                        # Na sua ficha, a "Data Promoção" aparece explicitamente.
                        # Vamos varrer o texto procurando a string exata "Data Promoção" e pegando a data seguinte.
                        
                        match_especifico = re.search(r'Data Promoção\s*(\d{2}/\d{2}/\d{4})', texto)
                        if match_especifico:
                            data_promo = match_especifico.group(1)
                            historico.append({
                                'Data_Mudanca': pd.to_datetime(data_promo, dayfirst=True),
                                'Classe': classe
                            })
        except Exception as e:
            st.error(f"Erro no arquivo {arquivo.name}: {e}")

    if not historico:
        return pd.DataFrame(columns=['Data_Mudanca', 'Classe'])
    
    # Limpeza: Remove duplicatas (mesma promoção aparece em vários meses)
    df = pd.DataFrame(historico)
    df = df.drop_duplicates().sort_values('Data_Mudanca')
    return df

# --- FUNÇÕES DE RELATÓRIO E CÁLCULO (MANTIDAS) ---
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
    
    if df_calc['Indice'].isnull().any():
         st.warning("⚠️ Atenção: Período sem classe definida encontrado. Assumindo Classe A para o início.")
         df_calc['Indice'] = df_calc['Indice'].fillna(0)
         df_calc['Classe'] = df_calc['Classe'].fillna('A')

    df_calc['Valor_Devido'] = valor_base_a * (1.15 ** df_calc['Indice'])
    df_calc['Diferenca'] = df_calc['Valor_Devido'] - df_calc['Valor_Pago']
    df_calc['Diferenca_Final'] = df_calc['Diferenca'].apply(lambda x: x if x > 0 else 0)
    
    return df_calc

# --- APP PRINCIPAL ---
st.sidebar.title("Cálculo PC/AL")
st.sidebar.info("Versão com Leitura Automática de PDF (Promoções).")

st.sidebar.header("1. Financeiro")
arquivo_fin = st.sidebar.file_uploader("Ficha Financeira (Excel/CSV)", type=['xlsx', 'csv'])

st.sidebar.header("2. Carreira (PDFs)")
arquivos_pdf = st.sidebar.file_uploader("Fichas Cadastrais (PDF)", type=['pdf'], accept_multiple_files=True)

st.sidebar.header("3. Parâmetros")
valor_base_a = st.sidebar.number_input("Valor Base (Classe A)", value=4000.00, step=100.00)
nome = st.sidebar.text_input("Nome", "SERVIDOR")
matricula = st.sidebar.text_input("Matrícula", "000.000-0")
cpf = st.sidebar.text_input("CPF", "000.000.000-00")

st.title("⚖️ Automação de Cálculo: 15% Entre Classes")

if arquivo_fin and arquivos_pdf:
    try:
        # 1. Ler Financeiro
        if arquivo_fin.name.endswith('.csv'):
            df_fin = pd.read_csv(arquivo_fin)
        else:
            df_fin = pd.read_excel(arquivo_fin)
            
        cols_fin = [c for c in df_fin.columns]
        col_data = next((c for c in cols_fin if 'data' in c.lower()), 'Data')
        col_valor = next((c for c in cols_fin if 'valor' in c.lower() or 'pago' in c.lower()), 'Valor_Pago')
        df_fin = df_fin.rename(columns={col_data: 'Data', col_valor: 'Valor_Pago'})
        df_fin['Data'] = pd.to_datetime(df_fin['Data'])
        
        # 2. Ler Carreira (PDF)
        with st.spinner('Lendo Fichas Cadastrais...'):
            df_car = ler_ficha_cadastral(arquivos_pdf)
            
        if df_car.empty:
            st.warning("Não encontrei datas de promoção. Verifique se os PDFs são Fichas Cadastrais válidas.")
        else:
            st.markdown(f"<div class='success-box'><b>Processado!</b> Encontradas {len(df_car)} promoções.</div>", unsafe_allow_html=True)
            st.dataframe(df_car)
            
            # 3. Calcular
            res = calcular(df_fin, df_car, valor_base_a)
            total = res['Diferenca_Final'].sum()
            
            # 4. Resultados
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><small>Cliente</small><br><b>{nome}</b></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><small>Pagamentos</small><br><b>{len(res)}</b></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><small>Classe Atual</small><br><b>{res['Classe'].iloc[-1]}</b></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='total-card'><small>DIFERENÇA TOTAL</small><br><span class='big-font'>R$ {format_currency_br(total)}</span></div>", unsafe_allow_html=True)
            
            st.markdown("---")
            
            tab1, tab2 = st.tabs(["📊 Gráficos", "📥 Exportar"])
            with tab1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Pago', line=dict(color='red')))
                fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Devido', line=dict(color='green', dash='dash')))
                st.plotly_chart(fig, use_container_width=True)
            with tab2:
                c_dl1, c_dl2, c_dl3 = st.columns(3)
                # Excel
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    res.to_excel(writer, index=False)
                c_dl1.download_button("📊 Excel", buffer.getvalue(), f"{nome}_calc.xlsx", "application/vnd.ms-excel")
                # PDF
                pdf_bytes = gerar_pdf(res, nome, matricula, cpf, total)
                c_dl2.download_button("📄 PDF Laudo", pdf_bytes, f"{nome}_laudo.pdf", "application/pdf")
                # TXT
                txt_bytes = gerar_txt_projefweb(res)
                c_dl3.download_button("📝 Projefweb", txt_bytes, f"{nome}_projefweb.txt", "text/plain")
                
    except Exception as e:
        st.error(f"Erro: {e}")
else:
    st.info("Aguardando upload dos arquivos (Financeiro + PDFs Cadastrais).")
