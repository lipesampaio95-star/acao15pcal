import streamlit as st
import pandas as pd
import datetime
from io import BytesIO
from fpdf import FPDF

# -------------------------
# FUNÇÕES DE CÁLCULO E UTILITÁRIAS
# -------------------------

CLASSES = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
NIVEIS = ['I', 'II', 'III', 'IV']

AJUSTES_ANUAIS = {
    2014: 0.00,
    2015: 0.05,
    2018: 0.0295,
    2022: 0.10,
    2025: 0.0393
}

def calcular_base_ano(base_inicial, ano):
    base = base_inicial
    for a, perc in sorted(AJUSTES_ANUAIS.items()):
        if a <= ano:
            base *= (1 + perc)
    return round(base, 2)

def calcular_valor_devido(base_ai, classe, nivel):
    classe_index = CLASSES.index(classe.upper())
    nivel_index = NIVEIS.index(nivel.upper())
    valor = (base_ai * (1.15 ** classe_index)) + (base_ai * 0.05 * nivel_index)
    return round(valor, 2)

def gerar_pdf(df_resultado, nome, matricula, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "LAUDO TÉCNICO PERICIAL", 0, 1, "C")
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Nome: {nome}    Matrícula: {matricula}", 0, 1)
    pdf.cell(0, 10, "", 0, 1)

    pdf.set_fill_color(204, 255, 204)
    pdf.set_font("Arial", 'B', 10)
    col_widths = [25, 20, 30, 30, 30, 30]
    headers = ["Mês/Ano", "Classe", "Nível", "Valor Pago", "Valor Devido", "Diferença"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, 1, 0, 'C', 1)
    pdf.ln()

    pdf.set_font("Arial", '', 9)
    for _, row in df_resultado.iterrows():
        valores = [row["Data"], row["Classe"], row["Nivel"],
                   f'R$ {row["Valor_Pago"]:.2f}', f'R$ {row["Valor_Devido"]:.2f}', f'R$ {row["Diferenca"]:.2f}']
        for i, val in enumerate(valores):
            pdf.cell(col_widths[i], 8, str(val), 1, 0, 'C')
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, f"VALOR TOTAL ACUMULADO DEVIDO: R$ {total:.2f}", 0, 1, "R")
    output = BytesIO()
    pdf.output(output)
    return output.getvalue()

def gerar_txt_projefweb(df):
    output = ""
    for _, row in df.iterrows():
        mes_ano = datetime.datetime.strptime(row["Data"], "%m/%Y").strftime("%m-%Y")
        valor = row["Diferenca"]
        if valor > 0:
            valor_fmt = f"R$ {valor:,.2f}".replace(".", "#").replace(",", ".").replace("#", ",")
            output += f"{mes_ano}\t{valor_fmt}\n"
    return output.encode("utf-8")

# -------------------------
# INTERFACE STREAMLIT
# -------------------------

st.set_page_config(page_title="Cálculo de Diferença de Classe (PC/AL)", layout="wide")
st.title("⚖️ Cálculo de Diferença de Classe (PC/AL)")

with st.sidebar:
    st.header("Parâmetros de Entrada")

    arquivos = st.file_uploader("Ficha Financeira (PDF - um por ano)", type="pdf", accept_multiple_files=True)

    base_classe_a = st.number_input("Base Classe A (R$)", value=3178.00, step=50.0, format="%.2f")
    nome = st.text_input("Nome do Servidor", value="Ex: João da Silva")
    matricula = st.text_input("Matrícula", value="0000000")

    promocoes = []
    manual = st.checkbox("📝 Promoções (Manual)", value=True)
    if manual:
        data = st.text_input("Data da Promoção", value="2016/03/03")
        classe = st.selectbox("Classe", CLASSES)
        if st.button("Registrar Promoção"):
            if "promocoes" not in st.session_state:
                st.session_state.promocoes = []
            st.session_state.promocoes.append((data, classe))
        if "promocoes" in st.session_state:
            st.write("Promoções Registradas:")
            for p in st.session_state.promocoes:
                st.markdown(f"- {p[0]} → Classe {p[1]}")
        if st.button("🧹 Limpar Promoções"):
            st.session_state.promocoes = []

    if st.button("🧽 Limpar Tudo"):
        st.session_state.clear()

# -------------------------
# EXECUÇÃO DO CÁLCULO
# -------------------------

if st.button("🚀 Calcular"):
    if not arquivos:
        st.warning("📂 Envie ao menos um arquivo PDF de ficha financeira.")
    elif "promocoes" not in st.session_state or not st.session_state.promocoes:
        st.warning("📌 Registre pelo menos uma promoção para continuar.")
    else:
        # Simula extração de valores pagos (deveria vir do OCR do PDF)
        dados_pagamentos = []
        for ano_pdf in arquivos:
            ano = 2016  # ← aqui você deve implementar OCR real
            for mes in range(1, 13):
                dados_pagamentos.append({
                    "Data": f"{mes:02d}/{ano}",
                    "Valor_Pago": base_classe_a + (mes * 2)  # SIMULAÇÃO
                })
        df_pagamentos = pd.DataFrame(dados_pagamentos)

        # Constrói DataFrame com classe e nível conforme promoções
        promocoes_ordenadas = sorted(st.session_state.promocoes, key=lambda x: x[0])
        historico_classe = []
        for data_str, classe in promocoes_ordenadas:
            data = datetime.datetime.strptime(data_str, "%Y/%m/%d")
            historico_classe.append((data, classe, "I"))  # FIXO Nível I

        resultados = []
        for _, row in df_pagamentos.iterrows():
            data_ref = datetime.datetime.strptime(row["Data"], "%m/%Y")
            classe = "A"
            nivel = "I"
            for data_promo, classe_promo, nivel_promo in historico_classe:
                if data_ref >= data_promo:
                    classe, nivel = classe_promo, nivel_promo
            base_ano = calcular_base_ano(base_classe_a, data_ref.year)
            devido = calcular_valor_devido(base_ano, classe, nivel)
            diferenca = max(devido - row["Valor_Pago"], 0.0)
            resultados.append({
                "Data": row["Data"],
                "Classe": classe,
                "Nivel": nivel,
                "Valor_Pago": row["Valor_Pago"],
                "Valor_Devido": devido,
                "Diferenca": diferenca
            })

        df_result = pd.DataFrame(resultados)
        total = df_result["Diferenca"].sum()

        st.success("✅ Cálculo concluído com sucesso.")
        st.dataframe(df_result)

        # PDF
        pdf_bytes = gerar_pdf(df_result, nome, matricula, total)
        st.download_button("📄 Baixar Laudo PDF", pdf_bytes, "laudo.pdf", mime="application/pdf")

        # Projefweb
        txt_bytes = gerar_txt_projefweb(df_result)
        st.download_button("📑 Baixar Projefweb TXT", txt_bytes, "projefweb.txt", mime="text/plain")
