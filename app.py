import streamlit as st
import pandas as pd
from PyPDF2 import PdfReader
from datetime import datetime
import base64
from io import BytesIO
from fpdf import FPDF

st.set_page_config(page_title="Calculadora de Diferença de Classe (PC/AL)", layout="wide")

# ==================== Funções Auxiliares ====================

def reajuste_anual(ano):
    reajustes = {
        2015: 1.05,
        2018: 1.0295,
        2022: 1.10,
        2025: 1.0393
    }
    return reajustes.get(ano, 1.0)

def calcular_base_A_por_ano(base_inicial):
    base_por_ano = {}
    base_atual = base_inicial
    for ano in range(2014, datetime.now().year + 1):
        base_por_ano[ano] = round(base_atual, 2)
        base_atual *= reajuste_anual(ano)
    return base_por_ano

def extrair_valores_pdf(file):
    reader = PdfReader(file)
    texto = ""
    for page in reader.pages:
        texto += page.extract_text() + "\n"
    linhas = texto.split("\n")
    
    ano = None
    for linha in linhas:
        if "Ano Comp:" in linha:
            try:
                ano = int(linha.split(":")[1].strip())
            except:
                pass
    
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
             "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    adicionais_ferias = {}
    pagos = {}

    for i, linha in enumerate(linhas):
        if "133.00 ADICIONAL DE FERIAS" in linha:
            valores = linhas[i + 1].split()
            for j, mes in enumerate(meses):
                try:
                    valor = float(valores[j].replace(".", "").replace(",", "."))
                    if valor > 0:
                        adicionais_ferias[f"{ano}-{j+1:02d}"] = valor
                except:
                    pass

        if "126.00 SUBSIDIO" in linha:
            valores = linhas[i + 1].split()
            for j, mes in enumerate(meses):
                try:
                    valor = float(valores[j].replace(".", "").replace(",", "."))
                    pagos[f"{ano}-{j+1:02d}"] = valor
                except:
                    pass

    return pagos, adicionais_ferias

def calcular_devido(base_A, classe_indice, nivel_indice):
    return (base_A * (1.15 ** classe_indice)) + (base_A * 0.05 * nivel_indice)

def gerar_pdf(servidor, matricula, resultado, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Laudo de Diferenças de Classe", ln=True, align="C")
    
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Servidor: {servidor}", ln=True)
    pdf.cell(0, 10, f"Matrícula: {matricula}", ln=True)
    pdf.ln(10)

    col_widths = [30, 25, 25, 30, 30, 30]
    headers = ["Mês", "Classe", "Nível", "Valor Pago", "Valor Devido", "Diferença"]

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 10, header, 1, 0, "C")
    pdf.ln()

    for _, row in resultado.iterrows():
        pdf.cell(col_widths[0], 10, row["Data"], 1)
        pdf.cell(col_widths[1], 10, row["Classe"], 1)
        pdf.cell(col_widths[2], 10, row["Nível"], 1)
        pdf.cell(col_widths[3], 10, f"{row['Valor Pago']:.2f}", 1)
        pdf.cell(col_widths[4], 10, f"{row['Valor Devido']:.2f}", 1)
        pdf.cell(col_widths[5], 10, f"{row['Diferença']:.2f}", 1)
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Valor Total Acumulado: R$ {total:.2f}", ln=True)

    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()

# ==================== Layout da Página ====================

st.title("⚖️ Cálculo de Diferença de Classe (PC/AL)")

st.sidebar.header("Parâmetros de Entrada")
arquivos = st.sidebar.file_uploader("Ficha Financeira (PDF - um por ano)", type="pdf", accept_multiple_files=True)

base_classe_A = st.sidebar.number_input("Base Classe A (R$)", value=3178.00, step=50.00, format="%.2f")
nome = st.sidebar.text_input("Nome do Servidor", value="Ex: João da Silva")
matricula = st.sidebar.text_input("Matrícula", value="0000000")

st.sidebar.markdown("---")
promocoes_ativas = st.sidebar.checkbox("📌 Promoções (Manual)", value=True)

if 'promocoes' not in st.session_state:
    st.session_state.promocoes = []

if promocoes_ativas:
    data_promocao = st.sidebar.text_input("Data da Promoção", value="2016/03/03")
    classe = st.sidebar.selectbox("Classe", ["A", "B", "C", "D", "E", "F", "G"])

    if st.sidebar.button("Registrar Promoção"):
        st.session_state.promocoes.append({"data": data_promocao, "classe": classe})

    if st.sidebar.button("🗑️ Limpar Promoções"):
        st.session_state.promocoes = []

    for promo in st.session_state.promocoes:
        st.sidebar.markdown(f"- {promo['data']} ➔ Classe {promo['classe']}")

if st.sidebar.button("🧹 Limpar Tudo"):
    st.session_state.promocoes = []
    st.rerun()

# ==================== Execução ====================

if st.button("🚀 Calcular"):
    if not arquivos or not st.session_state.promocoes:
        st.warning("⚠️ Envie os arquivos e registre promoções.")
        st.stop()

    base_ano = calcular_base_A_por_ano(base_classe_A)
    df_final = pd.DataFrame()

    for arquivo in arquivos:
        pagos, ferias = extrair_valores_pdf(arquivo)

        for mes_ref, valor_pago in pagos.items():
            data = datetime.strptime(mes_ref, "%Y-%m")
            if (datetime.now() - data).days > 5 * 365:
                continue  # prescrição de 5 anos

            classe_atual = "A"
            for promo in sorted(st.session_state.promocoes, key=lambda x: x['data']):
                data_promo = datetime.strptime(promo['data'], "%Y/%m/%d")
                if data >= data_promo:
                    classe_atual = promo['classe']

            classe_index = ord(classe_atual.upper()) - ord("A")
            nivel_index = 3  # fixo IV

            ano = data.year
            base_mes = base_ano.get(ano, base_classe_A)
            devido = calcular_devido(base_mes, classe_index, nivel_index)

            if mes_ref in ferias:
                devido += round(devido / 3, 2)  # adicional 1/3 férias

            diferenca = max(0, devido - valor_pago)

            df_final = pd.concat([df_final, pd.DataFrame([{
                "Data": mes_ref,
                "Classe": classe_atual,
                "Nível": "IV",
                "Valor Pago": valor_pago,
                "Valor Devido": devido,
                "Diferença": diferenca
            }])], ignore_index=True)

    total = df_final["Diferença"].sum()

    st.success("✅ Cálculo realizado com sucesso.")
    st.dataframe(df_final)

    pdf_bytes = gerar_pdf(nome, matricula, df_final, total)

    st.download_button("📄 Baixar PDF", data=pdf_bytes, file_name="laudo.pdf", mime="application/pdf")
