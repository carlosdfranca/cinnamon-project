from core.processing.dre_service import gerar_dados_dre
from core.processing.dpf_service import gerar_dados_dpf
from core.processing.dmpl_service import gerar_dados_dmpl
import re


def slugify_key(key: str) -> str:
    """
    Transforma nomes longos em chaves seguras para template:
    Ex: "Fluxo de caixa das atividades operacionais" → "fluxo_operacionais"
    """
    key = key.lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key)
    return key.strip("_")


def gerar_tabela_dfc(fundo_id: int, ano: int):
    """
    Retorna um dicionário hierárquico (dict_tabela) simplificado
    com chaves slugificadas (compatíveis com template engine).
    """

    dre_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(fundo_id, ano)
    dpf_tabela, _ = gerar_dados_dpf(fundo_id, ano)
    dados_dmpl = gerar_dados_dmpl(fundo_id, ano)

    def _int(v): return int(round(v or 0, 0))

    # === Helpers ===
    def pegar_valor_dre(nome):
        for grupo, linhas in dre_tabela.items():
            for label, dados in linhas.items():
                if label.strip().lower() == nome.strip().lower():
                    return _int(dados.get("ATUAL", 0)), _int(dados.get("ANTERIOR", 0))
        return 0, 0

    def pegar_valor_dpf(nome):
        for sec, grupos in dpf_tabela.items():
            for grupo_label, grupo in grupos.items():
                if isinstance(grupo, dict):
                    for sub_label, valores in grupo.items():
                        if isinstance(valores, dict) and sub_label.strip().lower() == nome.strip().lower():
                            return _int(valores.get("ATUAL", 0)), _int(valores.get("ANTERIOR", 0))
        return 0, 0

    def pegar_grupao(nome):
        for sec, grupos in dpf_tabela.items():
            for grupo_label, grupo in grupos.items():
                if grupo_label.strip().lower() == nome.strip().lower():
                    return _int(grupo.get("SOMA", 0)), _int(grupo.get("SOMA_ANTERIOR", grupo.get("ANTERIOR", 0)))
        return 0, 0

    # === BLOCO 1: Resultado Líquido do Período ===
    rendimento_atual, rendimento_ant = pegar_valor_dre("Resultado com recebíveis")
    provisao_atual, provisao_ant = pegar_valor_dre("(-) Provisão para operações de crédito")
    taxa_adm_atual, taxa_adm_ant = pegar_valor_dpf("Taxa de Administração")
    taxa_gestao_atual, taxa_gestao_ant = pegar_valor_dpf("Taxa de Gestão")

    rendimento_atual *= -1
    rendimento_ant *= -1
    provisao_atual *= -1
    provisao_ant *= -1

    resultado_ajustado_atual = (
        resultado_exercicio + rendimento_atual + provisao_atual + taxa_adm_atual + taxa_gestao_atual
    )
    resultado_ajustado_anterior = (
        resultado_exercicio_anterior + rendimento_ant + provisao_ant + taxa_adm_ant + taxa_gestao_ant
    )

    # === BLOCO 2: Variações Operacionais ===
    GRUPAO_DC = "Direitos Creditórios sem aquisição substancial dos riscos e benefícios"
    GRUPAO_OUTROS_RECEBER = "Outros Valores"
    GRUPAO_OUTROS_PAGAR = "Passivo Circulante"

    dc_atual, dc_ant = pegar_grupao(GRUPAO_DC)
    outros_receber_atual, outros_receber_ant = pegar_grupao(GRUPAO_OUTROS_RECEBER)
    outros_pagar_atual, outros_pagar_ant = pegar_grupao(GRUPAO_OUTROS_PAGAR)

    aumento_dc_atual = (dc_ant - dc_atual) - (rendimento_atual + provisao_atual)
    aumento_dc_ant = (dc_ant - dc_atual) - (rendimento_ant + provisao_ant)
    aumento_receber_atual = outros_receber_ant - outros_receber_atual
    aumento_receber_ant = outros_receber_ant - outros_receber_atual
    reducao_pagar_atual = outros_pagar_atual - outros_pagar_ant
    reducao_pagar_ant = outros_pagar_ant - outros_pagar_atual

    caixa_operacional_atual = (
        resultado_ajustado_atual + aumento_dc_atual + aumento_receber_atual + reducao_pagar_atual
    )
    caixa_operacional_ant = (
        resultado_ajustado_anterior + aumento_dc_ant + aumento_receber_ant + reducao_pagar_ant
    )

    # === BLOCO 3: Financiamento (DMPL)
    emissao_atual = dados_dmpl.get("aplicacoes_valor", 0)
    resgate_atual = -abs(dados_dmpl.get("resgates_valor", 0))
    emissao_ant = dados_dmpl.get("aplicacoes_valor_ant", 0)
    resgate_ant = -abs(dados_dmpl.get("resgates_valor_ant", 0))

    variacao_resgates_atual = 0
    variacao_resgates_ant = 0

    caixa_financiamento_atual = emissao_atual + resgate_atual + variacao_resgates_atual
    caixa_financiamento_ant = emissao_ant + resgate_ant + variacao_resgates_ant

    # === BLOCO 4: Variação e Caixa Final ===
    variacao_caixa_atual = caixa_operacional_atual + caixa_financiamento_atual
    variacao_caixa_ant = caixa_operacional_ant + caixa_financiamento_ant

    # --- Grupões DPF para caixa inicial/final
    GRUPAO_DISP = "Disponibilidades"
    GRUPAO_APL = "Aplicações interfinanceiras de liquidez"
    disp_atual, disp_ant = pegar_grupao(GRUPAO_DISP)
    apl_atual, apl_ant = pegar_grupao(GRUPAO_APL)

    caixa_final_atual = (disp_atual or 0) + (apl_atual or 0)
    caixa_inicial_atual = (disp_ant or 0) + (apl_ant or 0)

    caixa_final_ant = caixa_inicial_atual  # fim do ano anterior
    caixa_inicial_ant = 0

    # === DICIONÁRIO FINAL COM CHAVES SEGURAS ===
    dict_tabela = {
        "fluxo_operacionais": {
            "titulo": "Fluxo de caixa das atividades operacionais",
            "resultado_liquido": {
                "titulo": "Resultado líquido do período",
                "ATUAL": _int(resultado_exercicio),
                "ANTERIOR": _int(resultado_exercicio_anterior),
            },
            "ajustes": {
                "titulo": "Ajustes para reconciliar o resultado líquido com o fluxo de caixa",
                "rendimento_dc": {"titulo": "(-) Rendimento dos direitos creditórios", "ATUAL": rendimento_atual, "ANTERIOR": rendimento_ant},
                "provisao_perdas": {"titulo": "(-) Provisão para perdas por redução no valor de recuperação", "ATUAL": provisao_atual, "ANTERIOR": provisao_ant},
                "taxa_adm": {"titulo": "(+) Taxa de administração não liquidada", "ATUAL": taxa_adm_atual, "ANTERIOR": taxa_adm_ant},
                "taxa_gestao": {"titulo": "(+) Taxa de gestão não liquidada", "ATUAL": taxa_gestao_atual, "ANTERIOR": taxa_gestao_ant},
                "resultado_ajustado": {"titulo": "(=) Resultado ajustado", "ATUAL": resultado_ajustado_atual, "ANTERIOR": resultado_ajustado_anterior},
            },
            "aumento_dc": {"titulo": "(Aumento) em direitos creditórios", "ATUAL": aumento_dc_atual, "ANTERIOR": aumento_dc_ant},
            "aumento_receber": {"titulo": "(Aumento) de outros valores a receber", "ATUAL": aumento_receber_atual, "ANTERIOR": aumento_receber_ant},
            "reducao_pagar": {"titulo": "(Redução) em outros valores a pagar", "ATUAL": reducao_pagar_atual, "ANTERIOR": reducao_pagar_ant},
            "caixa_operacional": {"titulo": "Caixa líquido das atividades operacionais", "ATUAL": caixa_operacional_atual, "ANTERIOR": caixa_operacional_ant},
        },

        "fluxo_financiamento": {
            "titulo": "Fluxo de caixa das atividades de financiamento",
            "emissao": {"titulo": "(+) Emissão de cotas subordinadas", "ATUAL": emissao_atual, "ANTERIOR": emissao_ant},
            "resgate": {"titulo": "(-) Resgate de cotas subordinadas", "ATUAL": resgate_atual, "ANTERIOR": resgate_ant},
            "variacoes_resgates": {"titulo": "(-) Variações nos resgates de cotas subordinadas", "ATUAL": variacao_resgates_atual, "ANTERIOR": variacao_resgates_ant},
            "caixa_financiamento": {"titulo": "Caixa líquido das atividades de financiamento", "ATUAL": caixa_financiamento_atual, "ANTERIOR": caixa_financiamento_ant},
        },

        "variacao_caixa": {"titulo": "Variação no caixa e equivalentes de caixa", "ATUAL": variacao_caixa_atual, "ANTERIOR": variacao_caixa_ant},

        "caixa_inicio": {"titulo": "Caixa e equivalentes de caixa no início do período", "ATUAL": caixa_inicial_atual, "ANTERIOR": caixa_inicial_ant},

        "caixa_final": {"titulo": "Caixa e equivalentes de caixa no final do período", "ATUAL": caixa_final_atual, "ANTERIOR": caixa_final_ant},
    }

    return dict_tabela, variacao_caixa_atual, variacao_caixa_ant
