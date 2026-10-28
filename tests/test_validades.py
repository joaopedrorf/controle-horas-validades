from datetime import date

import validades

HOJE = date(2026, 10, 28)


class VooFalso:
    def __init__(self, data, minutos, funcao='comando', pousos=1):
        self.data, self.minutos, self.funcao, self.pousos = data, minutos, funcao, pousos


def test_situacao_vencido_atencao_em_dia():
    assert validades.situacao(date(2026, 10, 27), HOJE) == 'vencido'
    assert validades.situacao(date(2026, 10, 28), HOJE) == 'atencao'   # vence hoje ainda vale
    assert validades.situacao(date(2026, 11, 27), HOJE) == 'atencao'   # 30 dias
    assert validades.situacao(date(2026, 11, 28), HOJE) == 'em_dia'    # 31 dias


def test_dias_restantes():
    assert validades.dias_restantes(date(2026, 11, 4), HOJE) == 7
    assert validades.dias_restantes(date(2026, 10, 18), HOJE) == -10


def test_marco_devido():
    assert validades.marco_devido(date(2027, 1, 1), HOJE) is None
    assert validades.marco_devido(date(2026, 11, 27), HOJE) == 30
    assert validades.marco_devido(date(2026, 11, 10), HOJE) == 30
    assert validades.marco_devido(date(2026, 11, 4), HOJE) == 7
    assert validades.marco_devido(date(2026, 10, 30), HOJE) == 7
    assert validades.marco_devido(HOJE, HOJE) == 0
    assert validades.marco_devido(date(2026, 9, 1), HOJE) == 0


def test_ler_duracao_formatos_aceitos():
    assert validades.ler_duracao('1:30') == 90
    assert validades.ler_duracao('1h30') == 90
    assert validades.ler_duracao('2h') == 120
    assert validades.ler_duracao('1,5') == 90
    assert validades.ler_duracao('0.2') == 12
    assert validades.ler_duracao(' 0:45 ') == 45


def test_ler_duracao_recusa_invalidos():
    for texto in ('', 'abc', '1:75', '0:00', '0', '25:00', '-1', '1:3'):
        assert validades.ler_duracao(texto) is None, texto


def test_formatar_horas():
    assert validades.formatar_horas(90) == '1:30'
    assert validades.formatar_horas(5) == '0:05'
    assert validades.formatar_horas(1234) == '20:34'


def test_totais():
    voos = [
        VooFalso(date(2026, 10, 27), 60, 'instrucao', 3),
        VooFalso(date(2026, 9, 20), 90, 'solo', 2),      # 38 dias atrás: entra só nos 90
        VooFalso(date(2026, 6, 1), 600, 'comando', 9),   # fora dos 90 dias
    ]
    resumo = validades.totais(voos, HOJE)
    assert resumo['total'] == 750
    assert resumo['dias_30'] == 60
    assert resumo['dias_90'] == 150
    assert resumo['pousos_90'] == 5
    assert resumo['por_funcao'] == {'instrucao': 60, 'solo': 90, 'comando': 600}
