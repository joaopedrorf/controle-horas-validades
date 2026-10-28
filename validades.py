"""Regras de vencimento e de horas de voo, separadas das rotas para ficarem fáceis de testar."""
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# O servidor (Render) roda em UTC, mas o aeroclube vive no horário de Brasília.
FUSO = ZoneInfo(os.getenv('FUSO_HORARIO', 'America/Sao_Paulo'))

# Com quantos dias de antecedência o documento passa para "atenção" (amarelo)
DIAS_ATENCAO = 30

# Quando mandar e-mail: 30 dias antes, 7 dias antes e no dia do vencimento
MARCOS_AVISO = (30, 7, 0)

MAX_MINUTOS_VOO = 24 * 60


def agora_local():
    return datetime.now(FUSO).replace(tzinfo=None)


def hoje_local():
    return agora_local().date()


def dias_restantes(vencimento, hoje=None):
    """Positivo = faltam X dias; zero = vence hoje; negativo = vencido há X dias."""
    return (vencimento - (hoje or hoje_local())).days


def situacao(vencimento, hoje=None):
    """'vencido', 'atencao' (vence em até 30 dias) ou 'em_dia'."""
    dias = dias_restantes(vencimento, hoje)
    if dias < 0:
        return 'vencido'
    if dias <= DIAS_ATENCAO:
        return 'atencao'
    return 'em_dia'


def contar_situacoes(documentos, hoje=None):
    contagem = {'vencido': 0, 'atencao': 0, 'em_dia': 0}
    for doc in documentos:
        contagem[situacao(doc.vencimento, hoje)] += 1
    return contagem


def marco_devido(vencimento, hoje=None):
    """Qual lembrete já deveria ter saído para este vencimento (30, 7, 0) ou None.

    Pega o menor marco já alcançado: se o sistema ficou dias sem rodar, manda só
    o aviso mais recente em vez de mandar os três de uma vez.
    """
    dias = dias_restantes(vencimento, hoje)
    alcancados = [m for m in MARCOS_AVISO if dias <= m]
    return min(alcancados) if alcancados else None


# ---------- Horas de voo ----------

def ler_duracao(texto):
    """Aceita '1:30', '1h30', '1,5' ou '1.5'. Devolve minutos (int) ou None se inválido."""
    texto = (texto or '').strip().lower().replace(' ', '')
    m = re.fullmatch(r'(\d{1,2})[:h](\d{2})?', texto)
    if m:
        horas, minutos = int(m.group(1)), int(m.group(2) or 0)
        if minutos >= 60:
            return None
        total = horas * 60 + minutos
    elif re.fullmatch(r'\d{1,2}([.,]\d{1,2})?', texto):
        total = round(float(texto.replace(',', '.')) * 60)
    else:
        return None
    return total if 0 < total <= MAX_MINUTOS_VOO else None


def formatar_horas(minutos):
    """90 vira '1:30' (formato da caderneta). 1234 vira '20:34'."""
    return f"{minutos // 60}:{minutos % 60:02d}"


def totais(voos, hoje=None):
    """Somas de tempo de voo e pousos: total, últimos 30 e 90 dias e por função."""
    hoje = hoje or hoje_local()
    resumo = {'total': 0, 'dias_30': 0, 'dias_90': 0, 'pousos_90': 0, 'por_funcao': {}}
    for voo in voos:
        resumo['total'] += voo.minutos
        resumo['por_funcao'][voo.funcao] = resumo['por_funcao'].get(voo.funcao, 0) + voo.minutos
        if voo.data > hoje - timedelta(days=30):
            resumo['dias_30'] += voo.minutos
        if voo.data > hoje - timedelta(days=90):
            resumo['dias_90'] += voo.minutos
            resumo['pousos_90'] += voo.pousos
    return resumo
