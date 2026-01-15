import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from fpdf import FPDF
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Cálculo PC/AL - 15%", 
    page_icon="⚖️",
    layout="wide"
)

# --- CSS PERSONALIZADO ---
st.markdown("""
<style>
    .big-font { font-size:24px !important; font-weight: bold; color: #2E86C1; }
    .metric-card { background-color: #f8f9fa; border-radius: 10px; padding: 15px; text-align: center; border: 1px solid #e9ecef; }
    .total-card { background-color: #d4efdf; border: 2px solid #27ae60; border-radius: 10px; padding: 15px; text-align: center; }
    .warning-box { background-color: #fef9e7; padding: 10px; border-radius: 5px; border-left: 5px solid #f1c40f; }
</style>
""", unsafe_allow_html=True)

# --- FUNÇÕES UTILITÁRIAS ---
def format_currency_br(value):
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def gerar_planilha_modelo():
    """Gera um Excel em branco com as colunas corretas para o usuário baixar."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        # Aba Financeiro
        df_fin = pd.DataFrame({'Data': [], 'Valor_Pago': []})
        df_fin.to_excel(writer, sheet_name='FINANCEIRO', index=False)
        worksheet = writer.sheets['FINANCEIRO']
        worksheet.write_comment('A1', 'Coloque a data do pagamento (ex: 31/01/2020)')
        worksheet.write_comment('B1', 'Valor líquido do subsídio pago')

        # Aba Carreira
        df_car = pd.DataFrame({'Data_Mudanca': [], 'Classe': []})
        df_car.to_excel(writer, sheet_name='CARREIRA', index=False)
        worksheet = writer.sheets['CARREIRA']
        worksheet.write_comment('A1', 'Data que mudou de classe')
        worksheet.write_comment('B1', 'Nova classe (A, B, C...)')
        
    return buffer.getvalue()

# --- CLASSE PDF ---
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
    
    # Cabeçalho do Servidor
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, f"  DADOS DO SERVIDOR", 1, 1, 'L', fill=True)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f"  Nome: {nome} | Matrícula: {matricula} | CPF: {cpf}", 1, 1, 'L')
    pdf.ln(5)
    
    # Resumo Financeiro
    pdf.set_fill_color(212, 239, 223) # Verde
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 12, f"VALOR TOTAL APURADO: R$ {format_currency_br(total)}", 1, 1, 'C', fill=True)
    pdf.ln(10)
    
    # Tabela
    pdf.set_font('Arial', 'B', 9)
    # Larguras: Data, Classe, Pago, Devido, Diferença
    w = [30, 20, 35, 35, 35] 
    headers = ['Mês/Ano', 'Classe', 'Pago (R$)', 'Devido (R$)', 'Diferença (R$)']
    
    for i, h in enumerate(headers):
        pdf.cell(w[i], 7, h, 1, 0, 'C')
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
        
        # Destacar se tiver valor a receber
        if row['Diferenca_Final'] > 0:
            pdf.set_font('Arial', 'B', 9)
            pdf.cell(w[4], 6, val_dif, 1, 0, 'R')
            pdf.set_font('Arial', '', 9)
        else:
            pdf.cell(w[4], 6, val_dif, 1, 0, 'R')
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- LOGICA PROJEFWEB ---
def gerar_txt_projefweb(df):
    output = io.StringIO()
    for _, row in df.iterrows():
        if row['Diferenca_Final'] > 0.01:
            data_fmt = row['Data'].strftime('%m-%Y')
            valor_fmt = f"R$ {format_currency_br(row['Diferenca_Final'])}"
            output.write(f"{data_fmt}\t{valor_fmt}\n")
    return output.getvalue().encode('utf-8')

# --- LÓGICA DE CÁLCULO ---
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
    
    # Tratamento de erro caso classe não esteja mapeada ou esteja vazia
    if df_calc['Indice'].isnull().any():
         st.warning("⚠️ Atenção: Existem meses sem classe definida. Verifique se a primeira data da aba 'CARREIRA' é anterior ao primeiro pagamento.")
         df_calc = df_calc.dropna(subset=['Indice'])

    df_calc['Valor_Devido'] = valor_base_a * (1.15 ** df_calc['Indice'])
    df_calc['Diferenca'] = df_calc['Valor_Devido'] - df_calc['Valor_Pago']
    df_calc['Diferenca_Final'] = df_calc['Diferenca'].apply(lambda x: x if x > 0 else 0)
    
    return df_calc

# --- SIDEBAR ---
st.sidebar.image("https://cdn-icons-png.flaticon.com/512/2230/2230606.png", width=50)
st.sidebar.title("Cálculo Jurídico")
st.sidebar.info("Ferramenta interna para cálculo de diferenças salariais (PC/AL).")

st.sidebar.header("1. Obter Modelo")
st.sidebar.download_button(
    "📥 Baixar Planilha Modelo",
    gerar_planilha_modelo(),
    "modelo_calculo.xlsx",
    "application/vnd.ms-excel"
)

st.sidebar.header("2. Upload de Dados")
arquivo = st.sidebar.file_uploader("Subir Planilha Preenchida", type=['xlsx'])

st.sidebar.header("3. Parâmetros")
valor_base_a = st.sidebar.number_input("Valor Base (Classe A)", value=4000.00, step=100.00)

st.sidebar.markdown("---")
nome = st.sidebar.text_input("Nome do Cliente", "JOÃO DA SILVA")
matricula = st.sidebar.text_input("Matrícula", "000.000-0")
cpf = st.sidebar.text_input("CPF", "000.000.000-00")

# --- MAIN ---
st.title("⚖️ Painel de Cálculo: Diferença de Classes (15%)")

if arquivo:
    try:
        df_fin = pd.read_excel(arquivo, sheet_name='FINANCEIRO')
        df_car = pd.read_excel(arquivo, sheet_name='CARREIRA')
        
        # Validar colunas
        if 'Valor_Pago' not in df_fin.columns or 'Classe' not in df_car.columns:
            st.error("Erro: A planilha não segue o modelo. Baixe o modelo na barra lateral.")
        else:
            df_fin['Data'] = pd.to_datetime(df_fin['Data'])
            df_car['Data_Mudanca'] = pd.to_datetime(df_car['Data_Mudanca'])
            
            # CALCULAR
            res = calcular(df_fin, df_car, valor_base_a)
            total = res['Diferenca_Final'].sum()
            
            # METRICAS
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"<div class='metric-card'><small>Cliente</small><br><b>{nome}</b></div>", unsafe_allow_html=True)
            c2.markdown(f"<div class='metric-card'><small>Período</small><br><b>{len(res)} meses</b></div>", unsafe_allow_html=True)
            c3.markdown(f"<div class='metric-card'><small>Status</small><br><b>Calculado</b></div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='total-card'><small>DIFERENÇA APURADA</small><br><span class='big-font'>R$ {format_currency_br(total)}</span></div>", unsafe_allow_html=True)
            
            st.markdown("---")
            
            # TABS PARA ORGANIZAR
            tab1, tab2, tab3 = st.tabs(["📊 Gráficos", "📋 Tabela Detalhada", "📥 Downloads"])
            
            with tab1:
                col_g1, col_g2 = st.columns([2,1])
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Pago'], name='Valor Pago', line=dict(color='#e74c3c')))
                fig.add_trace(go.Scatter(x=res['Data'], y=res['Valor_Devido'], name='Deveria Receber', line=dict(color='#27ae60', dash='dash')))
                fig.update_layout(title="Evolução do Prejuízo (Pago vs Devido)", hovermode="x unified")
                col_g1.plotly_chart(fig, use_container_width=True)
                
                col_g2.plotly_chart(px.bar(res, x='Data', y='Diferenca_Final', title="Diferença Mensal"), use_container_width=True)

            with tab2:
                st.dataframe(res[['Data', 'Classe', 'Valor_Pago', 'Valor_Devido', 'Diferenca_Final']].style.format({
                    'Valor_Pago': 'R$ {:,.2f}', 
                    'Valor_Devido': 'R$ {:,.2f}', 
                    'Diferenca_Final': 'R$ {:,.2f}'
                }))
                
            with tab3:
                st.subheader("Exportar Resultados")
                d1, d2, d3 = st.columns(3)
                
                # Excel
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='xlsxwriter') as writer:
                    res.to_excel(writer, index=False)
                d1.download_button("📊 Baixar Excel", buffer_excel.getvalue(), f"{nome}_calculo.xlsx", "application/vnd.ms-excel")
                
                # PDF
                pdf_bytes = gerar_pdf(res, nome, matricula, cpf, total)
                d2.download_button("📄 Baixar PDF (Laudo)", pdf_bytes, f"{nome}_laudo.pdf", "application/pdf")
                
                # TXT
                txt_bytes = gerar_txt_projefweb(res)
                d3.download_button("📝 Baixar Projefweb (.txt)", txt_bytes, f"{nome}_projefweb.txt", "text/plain")

    except Exception as e:
        st.error(f"Erro ao processar arquivo: {e}")
else:
    st.info("👈 Comece baixando a planilha modelo na barra lateral e preenchendo os dados.")
