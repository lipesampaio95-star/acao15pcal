import streamlit as st
import pandas as pd
import pdfplumber
import datetime
import io
import re
from fpdf import FPDF

# Configuração da Página
st.set_page_config(page_title="Calculadora PC/AL", page_icon="⚖️", layout="wide")

# ------------------------------------------------------------------------------
# 1. FUNÇÕES DE EXTRAÇÃO E PROCESSAMENTO (BACKEND)
# ------------------------------------------------------------------------------

def extrair_financeiro(file):
    """Extrai dados de subsídio do PDF usando Regex para maior precisão."""
    with pdfplumber.open(file) as pdf:
        tabela = []
        ano = None
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            # Identifica o Ano de Competência na ficha
            match_ano = re.search(r"Ano Comp:\s*(\d{4})", text)
            if match_ano:
                ano = int(match_ano.group(1))

            lines = text.split("\n")
            for line in lines:
                # O código 126.00 identifica a verba de SUBSIDIO na PC/AL
                if "126.00 SUBSIDIO" in line:
                    # Captura todos os valores no formato financeiro (Ex: 15.137,14 ou 3.178,00)
                    valores_encontrados = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})", line)
                    
                    # O Portal do Servidor gera 12 meses + 1 coluna de Total. Pegamos os 12 meses.
                    if len(valores_encontrados) >= 12 and ano:
                        meses = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
                        for i, val in enumerate(valores_encontrados[:12]):
                            val_float = float(val.replace(".", "").replace(",", "."))
                            # Forçamos a data para o padrão YYYY-MM para facilitar o merge
                            data = f"{ano}-{meses[i]}"
                            tabela.append({"Data": data, "Valor_Pago": val_float})
        
        return pd.DataFrame(tabela)

def calcular_base_ano(base_inicial):
    """Evolui a base Classe A Nível I conforme leis de reajuste geral."""
    reajustes = {
        2015: 1.05,    # Lei 7.726/15
        2018: 1.0295,  # Lei 7.964/18
        2022: 1.10,    # Recomposição inflacionária
        2025: 1.0393   # Lei 7.446/25
    }
    base_por_ano = {}
    atual = base_inicial
    for ano in range(2014, datetime.datetime.now().year + 1):
        if ano in reajustes:
            atual *= reajustes[ano]
        base_por_ano[ano] = atual
    return base_por_ano

def calcular_valor_devido(base_A_I, classe_idx, nivel_idx):
    """
    Lógica Lei 7.602/2014:
    - Classes (A-G): Progressão Geométrica de 15% (Base * 1.15 ^ index)
    - Níveis (I-IV): Progressão Aritmética de 5% sobre a base inicial (Base * 0.05 * index)
    """
    valor_classe = base_A_I * (1.15 ** classe_idx)
    valor_nivel = base_A_I * 0.05 * nivel_idx
    return valor_classe + valor_nivel

# ------------------------------------------------------------------------------
# 2. FUNÇÕES DE EXPORTAÇÃO (VISUAL JURÍDICO)
# ------------------------------------------------------------------------------

def gerar_pdf(df, nome, matricula, total):
    pdf = FPDF()
    pdf.add_page()
    
    # Cabeçalho Oficial
    pdf.set_font("Arial", "B", 10)
    pdf.cell(0, 5, "ESTADO DE ALAGOAS", ln=True, align="L")
    pdf.cell(0, 5, "POLÍCIA CIVIL DO ESTADO DE ALAGOAS", ln=True, align="L")
    pdf.line(10, 22, 200, 22)
    pdf.ln(10)

    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "LAUDO PERICIAL DE DIFERENÇAS SALARIAIS", ln=True, align="C")
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 10, f"Servidor: {nome.upper()} | Matrícula: {matricula}", ln=True, align="C")
    pdf.ln(5)

    # Tabela de Cálculos
    pdf.set_fill_color(44, 62, 80) # Azul Marinho Jurídico
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 9)
    headers = ["Mês/Ano", "Classe", "Nível", "Valor Pago", "Valor Devido", "Diferença"]
    widths = [30, 25, 25, 35, 35, 35]
    
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 10, h, 1, 0, "C", True)
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 9)
    
    for _, row in df.iterrows():
        pdf.cell(widths[0], 8, row["Data"], 1, 0, "C")
        pdf.cell(widths[1], 8, row["Classe"], 1, 0, "C")
        pdf.cell(widths[2], 8, row["Nível"], 1, 0, "C")
        pdf.cell(widths[3], 8, f"R$ {row['Valor_Pago']:,.2f}", 1, 0, "R")
        pdf.cell(widths[4], 8, f"R$ {row['Valor_Devido']:,.2f}", 1, 0, "R")
        pdf.cell(widths[5], 8, f"R$ {row['Diferenca']:,.2f}", 1, 1, "R")

    pdf.ln(5)
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(212, 239, 223) # Verde Suave
    pdf.cell(0, 12, f"VALOR TOTAL LÍQUIDO DEVIDO: R$ {total:,.2f}", 1, 1, "C", True)
    
    # Assinatura
    pdf.ln(20)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.cell(0, 10, "Responsável Técnico pelos Cálculos", ln=True, align="C")
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 5, f"Gerado via Sistema Automatizado em {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align="C")

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

def gerar_projefweb_txt(df):
    output = io.StringIO()
    for _, row in df.iterrows():
        # Formato: MM-AAAA [TAB] R$ Valor
        if row['Diferenca'] > 0:
            # Reverte Data de YYYY-MM para MM-YYYY
            mes_ano = f"{row['Data'][5:]}-{row['Data'][:4]}"
            valor = f"R$ {row['Diferenca']:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',')
            output.write(f"{mes_ano}\t{valor}\n")
    return output.getvalue().encode('utf-8')

# ------------------------------------------------------------------------------
# 3. INTERFACE STREAMLIT (FRONTEND)
# ------------------------------------------------------------------------------

st.title("⚖️ Sistema Jurídico PC/AL")
st.markdown("Cálculo Automático de Interstícios (Lei 7.602/14)")

with st.sidebar:
    st.header("1. Documentos")
    arquivos = st.file_uploader("Fichas Financeiras (PDF)", type=["pdf"], accept_multiple_files=True)
    
    st.header("2. Parâmetros")
    base_classe_A = st.number_input("Base Classe A Nível I (2014)", value=3178.00)
    nome = st.text_input("Nome do Servidor")
    matricula = st.text_input("Matrícula")

    st.header("3. Histórico de Promoções")
    if "historico" not in st.session_state: st.session_state.historico = []
    
    c_data = st.text_input("Data Promoção (AAAA-MM-DD)", "2016-03-01")
    c_classe = st.selectbox("Classe", ["A", "B", "C", "D", "E", "F", "G"])
    c_nivel = st.selectbox("Nível", ["I", "II", "III", "IV"])
    
    if st.button("➕ Registrar Promoção"):
        st.session_state.historico.append((c_data, c_classe, c_nivel))
    
    if st.button("🗑️ Limpar"):
        st.session_state.historico = []
        st.rerun()

    for item in sorted(st.session_state.historico):
        st.caption(f"📅 {item[0]} | Cl: {item[1]} | Nív: {item[2]}")

# EXECUÇÃO DO CÁLCULO
if st.button("🚀 EXECUTAR CÁLCULO") and arquivos and st.session_state.historico:
    try:
        # Extração
        dfs = [extrair_financeiro(f) for f in arquivos]
        df_fin = pd.concat(dfs).sort_values(by="Data").drop_duplicates(subset="Data")

        # Processamento das Promoções (Ajuste de Data para Merge)
        promo_df = pd.DataFrame(st.session_state.historico, columns=["Data", "Classe", "Nivel"])
        promo_df["Data"] = pd.to_datetime(promo_df["Data"]).dt.to_period('M').dt.to_timestamp()
        
        # Cria range completo de meses entre a primeira promoção e hoje
        data_inicio = promo_df["Data"].min()
        data_fim = pd.to_datetime(datetime.datetime.now())
        all_months = pd.date_range(data_inicio, data_fim, freq='MS')
        
        df_hist = pd.DataFrame({"Data": all_months})
        df_hist = pd.merge(df_hist, promo_df, on="Data", how="left").ffill()
        df_hist["Data"] = df_hist["Data"].dt.strftime("%Y-%m")

        # Merge Final
        df_final = pd.merge(df_fin, df_hist, on="Data", how="inner")
        
        # Cálculos Matemáticos
        base_ano_map = calcular_base_ano(base_classe_A)
        df_final["Ano"] = df_final["Data"].str[:4].astype(int)
        df_final["Base_Ref"] = df_final["Ano"].map(base_ano_map)
        
        df_final["Cl_Idx"] = df_final["Classe"].map(lambda x: ord(x.upper()) - ord("A"))
        df_final["Nv_Idx"] = df_final["Nivel"].map({"I": 0, "II": 1, "III": 2, "IV": 3})
        
        df_final["Valor_Devido"] = df_final.apply(
            lambda r: calcular_valor_devido(r["Base_Ref"], r["Cl_Idx"], r["Nv_Idx"]), axis=1
        )
        
        df_final["Diferenca"] = (df_final["Valor_Devido"] - df_final["Valor_Pago"]).clip(lower=0)
        total_acumulado = df_final["Diferenca"].sum()

        # Exibição
        st.success(f"Cálculo concluído! Total: R$ {total_acumulado:,.2f}")
        st.dataframe(df_final[["Data", "Classe", "Nivel", "Valor_Pago", "Valor_Devido", "Diferenca"]].style.format(precision=2))

        # Downloads
        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📑 Baixar Laudo PDF", gerar_pdf(df_final, nome, matricula, total_acumulado), "laudo_pericial.pdf")
        with col2:
            st.download_button("📂 Exportar Projefweb", gerar_projefweb_txt(df_final), "importacao_projefweb.txt")

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
