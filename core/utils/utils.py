from df.models import BalanceteItem


def gerar_dados_dre(fundo_id, ano):
    contas_dre = [
        "7.1.1.10.00.001-5", "7.1.1.10.00.016-1", "8.1.5.10.00.001-4", "8.1.9.99.00.001-3",
        "7.1.4.10.10.007-1", "7.1.9.99.00.016-0", "8.1.7.81.00.001-8", "8.1.7.81.00.004-9",
        "8.1.7.54.00.003-8", "8.1.7.54.00.008-3", "8.1.7.48.00.001-3", "8.1.7.54.00.005-2",
        "8.1.7.63.00.001-2", "8.1.7.63.00.002-9", "8.1.7.99.00.001-7"
    ]

    estrutura_dre = {
        "Direitos creditórios sem aquisição substancial de riscos e benefícios": [
            "Rendimentos de  direitos creditórios",
            "(-) Provisão para perdas por redução no valor de recuperação"
        ],
        "Rendas de aplicações interfinanceiras de liquidez": [
            "Letra Financeiras do Tesouro - LFT"
        ],
        "Outras receitas operacionais": [
            "Outras receitas operacionais"
        ],
        "Demais despesas": [
            "Taxa de administração", "Taxa de gestão", "Despesas bancárias",
            "Despesas com publicações", "Taxa de fiscalização CVM",
            "Serviços de auditoria", "Serviços de consultoria", "Outras despesas"
        ]
    }

    itens_ano = BalanceteItem.objects.filter(
        fundo_id=fundo_id,
        ano=ano,
        conta_corrente__conta__in=contas_dre
    )
    itens_ano_anterior = BalanceteItem.objects.filter(
        fundo_id=fundo_id,
        ano=ano - 1,
        conta_corrente__conta__in=contas_dre
    )

    dict_tabela = {}
    resultado_exercicio = 0
    resultado_exercicio_anterior = 0

    for grupo_dre, subgrupos in estrutura_dre.items():
        grupo_data = {}
        soma_atual = 0
        soma_anterior = 0

        for subgrupo in subgrupos:
            valor_atual = sum(
                item.saldo_final for item in itens_ano
                if item.conta_corrente.grupo_df.strip().lower() == subgrupo.strip().lower() # type: ignore
            ) # type: ignore
            valor_anterior = sum(
                item.saldo_final for item in itens_ano_anterior
                if item.conta_corrente.grupo_df.strip().lower() == subgrupo.strip().lower() # type: ignore
            ) # type: ignore
            grupo_data[subgrupo] = {
                "ATUAL": valor_atual,
                "ANTERIOR": valor_anterior
            }
            soma_atual += valor_atual
            soma_anterior += valor_anterior

        grupo_data["SOMA"] = soma_atual
        grupo_data["SOMA_ANTERIOR"] = soma_anterior

        resultado_exercicio += soma_atual
        resultado_exercicio_anterior += soma_anterior

        dict_tabela[grupo_dre] = grupo_data

    return dict_tabela, resultado_exercicio, resultado_exercicio_anterior
