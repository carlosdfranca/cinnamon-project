from datetime import date
import re

from core.processing.dre_service import gerar_dados_dre
from core.processing.dpf_service import gerar_dados_dpf
from core.processing.dmpl_service import gerar_dados_dmpl


def slugify_key(key: str) -> str:
    """
    Transforma nomes longos em chaves seguras para template:
    Ex: "Fluxo de caixa das atividades operacionais" → "fluxo_operacionais"
    """
    key = key.lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = re.sub(r"_+", "_", key)
    return key.strip("_")


def gerar_tabela_dfc(fundo_id: int, data_atual: date, data_anterior: date | None, zerar_anterior: bool = False):
    """
    Retorna um dicionário hierárquico (dict_tabela) no mesmo formato do DFC original,
    porém comparando duas datas específicas de balancete.

    Se zerar_anterior=True, considera que o saldo anterior é zerado (início do fundo),
    e todos os campos 'ANTERIOR' do relatório são retornados como 0.
    """

    # === Importa dados dos demais relatórios ===
    dre_tabela, resultado_exercicio, resultado_exercicio_anterior = gerar_dados_dre(
        fundo_id, data_atual, data_anterior, zerar_anterior=zerar_anterior
    )
    dpf_tabela, _ = gerar_dados_dpf(
        fundo_id, data_atual, data_anterior, zerar_anterior=zerar_anterior
    )
    dados_dmpl = gerar_dados_dmpl(
        fundo_id, data_atual, data_anterior, zerar_anterior=zerar_anterior
    )

    def _int(v):
        try:
            return int(round(v or 0, 0))
        except Exception:
            return 0

    # === Helpers ===
    def pegar_valor_dre(nome):
        for grupo, linhas in dre_tabela.items():
            for label, dados in linhas.items():
                if label.strip().lower() == nome.strip().lower():
                    return _int(dados.get("ATUAL", 0)), (0 if zerar_anterior else _int(dados.get("ANTERIOR", 0)))
        return 0, 0

    def pegar_valor_dpf(nome):
        for sec, grupos in dpf_tabela.items():
            for grupo_label, grupo in grupos.items():
                if isinstance(grupo, dict):
                    for sub_label, valores in grupo.items():
                        if isinstance(valores, dict) and sub_label.strip().lower() == nome.strip().lower():
                            atual = _int(valores.get("ATUAL", 0))
                            anterior = 0 if zerar_anterior else _int(valores.get("ANTERIOR", 0))
                            return atual, anterior
        return 0, 0

    def pegar_grupao(nome):
        for sec, grupos in dpf_tabela.items():
            for grupo_label, grupo in grupos.items():
                if grupo_label.strip().lower() == nome.strip().lower():
                    atual = _int(grupo.get("SOMA", 0))
                    anterior = 0 if zerar_anterior else _int(grupo.get("SOMA_ANTERIOR", grupo.get("ANTERIOR", 0)))
                    return atual, anterior
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
    resultado_ajustado_anterior = 0 if zerar_anterior else (
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
    aumento_dc_ant = 0 if zerar_anterior else (dc_ant - dc_atual) - (rendimento_ant + provisao_ant)

    aumento_receber_atual = outros_receber_ant - outros_receber_atual
    aumento_receber_ant = 0 if zerar_anterior else (outros_receber_ant - outros_receber_atual)

    reducao_pagar_atual = (outros_pagar_atual - outros_pagar_ant) - taxa_adm_atual - taxa_gestao_atual
    reducao_pagar_ant = 0 if zerar_anterior else (outros_pagar_ant - outros_pagar_atual) - taxa_adm_ant - taxa_gestao_ant

    caixa_operacional_atual = (
        resultado_ajustado_atual + aumento_dc_atual + aumento_receber_atual + reducao_pagar_atual
    )
    caixa_operacional_ant = 0 if zerar_anterior else (
        resultado_ajustado_anterior + aumento_dc_ant + aumento_receber_ant + reducao_pagar_ant
    )

    # === BLOCO 3: Financiamento (DMPL)
    emissao_atual = dados_dmpl.get("aplicacoes_valor", 0)
    resgate_atual = -abs(dados_dmpl.get("resgates_valor", 0))
    emissao_ant = 0 if zerar_anterior else dados_dmpl.get("aplicacoes_valor_ant", 0)
    resgate_ant = 0 if zerar_anterior else -abs(dados_dmpl.get("resgates_valor_ant", 0))

    caixa_financiamento_atual = emissao_atual + resgate_atual
    caixa_financiamento_ant = 0 if zerar_anterior else emissao_ant + resgate_ant

    # === BLOCO 4: Variação e Caixa Final ===
    variacao_caixa_atual = caixa_operacional_atual + caixa_financiamento_atual
    variacao_caixa_ant = 0 if zerar_anterior else caixa_operacional_ant + caixa_financiamento_ant

    # --- Grupões DPF para caixa inicial/final
    GRUPAO_DISP = "Disponibilidades"
    GRUPAO_APL = "Aplicações interfinanceiras de liquidez"
    disp_atual, disp_ant = pegar_grupao(GRUPAO_DISP)
    apl_atual, apl_ant = pegar_grupao(GRUPAO_APL)

    caixa_final_atual = (disp_atual or 0) + (apl_atual or 0)
    caixa_inicial_atual = (disp_ant or 0) + (apl_ant or 0)

    caixa_final_ant = 0 if zerar_anterior else caixa_inicial_atual
    caixa_inicial_ant = 0  # sempre zerado (não existe "anterior do anterior")

    # === DICIONÁRIO FINAL ===
    dict_tabela = {
        "fluxo_operacionais": {
            "titulo": "Fluxo de caixa das atividades operacionais",
            "resultado_liquido": {
                "titulo": "Resultado líquido do período",
                "ATUAL": _int(resultado_exercicio),
                "ANTERIOR": 0 if zerar_anterior else _int(resultado_exercicio_anterior),
            },
            "ajustes": {
                "titulo": "Ajustes para reconciliar o resultado líquido com o fluxo de caixa",
                "rendimento_dc": {"titulo": "(-) Rendimento dos direitos creditórios", "ATUAL": rendimento_atual, "ANTERIOR": 0 if zerar_anterior else rendimento_ant},
                "provisao_perdas": {"titulo": "(-) Provisão para perdas por redução no valor de recuperação", "ATUAL": provisao_atual, "ANTERIOR": 0 if zerar_anterior else provisao_ant},
                "taxa_adm": {"titulo": "(+) Taxa de administração não liquidada", "ATUAL": taxa_adm_atual, "ANTERIOR": 0 if zerar_anterior else taxa_adm_ant},
                "taxa_gestao": {"titulo": "(+) Taxa de gestão não liquidada", "ATUAL": taxa_gestao_atual, "ANTERIOR": 0 if zerar_anterior else taxa_gestao_ant},
                "resultado_ajustado": {"titulo": "(=) Resultado ajustado", "ATUAL": resultado_ajustado_atual, "ANTERIOR": 0 if zerar_anterior else resultado_ajustado_anterior},
            },
            "aumento_dc": {"titulo": "(Aumento) em direitos creditórios", "ATUAL": aumento_dc_atual, "ANTERIOR": 0 if zerar_anterior else aumento_dc_ant},
            "aumento_receber": {"titulo": "(Aumento) de outros valores a receber", "ATUAL": aumento_receber_atual, "ANTERIOR": 0 if zerar_anterior else aumento_receber_ant},
            "reducao_pagar": {"titulo": "(Redução) em outros valores a pagar", "ATUAL": reducao_pagar_atual, "ANTERIOR": 0 if zerar_anterior else reducao_pagar_ant},
            "caixa_operacional": {"titulo": "Caixa líquido das atividades operacionais", "ATUAL": caixa_operacional_atual, "ANTERIOR": 0 if zerar_anterior else caixa_operacional_ant},
        },

        "fluxo_financiamento": {
            "titulo": "Fluxo de caixa das atividades de financiamento",
            "emissao": {"titulo": "(+) Emissão de cotas subordinadas", "ATUAL": emissao_atual, "ANTERIOR": 0 if zerar_anterior else emissao_ant},
            "resgate": {"titulo": "(-) Resgate de cotas subordinadas", "ATUAL": resgate_atual, "ANTERIOR": 0 if zerar_anterior else resgate_ant},
            "caixa_financiamento": {"titulo": "Caixa líquido das atividades de financiamento", "ATUAL": caixa_financiamento_atual, "ANTERIOR": 0 if zerar_anterior else caixa_financiamento_ant},
        },

        "variacao_caixa": {"titulo": "Variação no caixa e equivalentes de caixa", "ATUAL": variacao_caixa_atual, "ANTERIOR": 0 if zerar_anterior else variacao_caixa_ant},

        "caixa_inicio": {"titulo": "Caixa e equivalentes de caixa no início do período", "ATUAL": caixa_inicial_atual, "ANTERIOR": 0 if zerar_anterior else caixa_inicial_ant},

        "caixa_final": {"titulo": "Caixa e equivalentes de caixa no final do período", "ATUAL": caixa_final_atual, "ANTERIOR": 0 if zerar_anterior else caixa_final_ant},
    }

    return dict_tabela, variacao_caixa_atual, 0 if zerar_anterior else variacao_caixa_ant
