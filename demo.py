"""Dados de demonstração: um aeroclube fictício com pilotos, documentos e voos.

Os vencimentos e as datas dos voos são calculados a partir de hoje, então o
painel sempre mostra documentos vencidos, perto de vencer e em dia.
"""
from datetime import timedelta

from modelos import Documento, Usuario, Voo, db
import validades

SENHA_DEMO = 'demo123'

USUARIOS = [
    ('Marta Lima', 'admin@demo.com', 'admin'),
    ('Cmte. Ana Souza', 'ana@demo.com', 'piloto'),
    ('Carla Mendes', 'carla@demo.com', 'piloto'),
    ('Diego Rocha', 'diego@demo.com', 'piloto'),
    ('Eduarda Alves', 'eduarda@demo.com', 'piloto'),
]

# (pessoa, tipo, descrição, vence daqui a quantos dias; negativo = já venceu)
DOCUMENTOS = [
    ('ana', 'cma', '2ª classe', 210),
    ('ana', 'habilitacao', 'MNTE', 45),
    ('ana', 'instrutor', 'INVA', 5),
    ('ana', 'ingles', 'Nível 4', 400),
    ('carla', 'cma', '2ª classe', 25),
    ('carla', 'habilitacao', 'MNTE', 300),
    ('diego', 'cma', '2ª classe', -12),
    ('diego', 'habilitacao', 'MNTE', 120),
    ('eduarda', 'cma', '1ª classe', 160),
    ('eduarda', 'habilitacao', 'MNTE', 0),
    ('eduarda', 'ifr', 'IFRA', 80),
]

# (pessoa, quantos dias atrás, matrícula, função, minutos, pousos, observação)
VOOS = [
    ('ana', 2, 'PR-ABC', 'instrutor', 60, 6, 'Instrução: tráfego'),
    ('ana', 2, 'PR-DEF', 'instrutor', 120, 2, 'Navegação'),
    ('ana', 9, 'PR-GHI', 'instrutor', 90, 3, 'Instrução: pane simulada'),
    ('ana', 40, 'PR-ABC', 'comando', 150, 2, 'Traslado'),
    ('ana', 130, 'PR-DEF', 'comando', 1260, 30, 'Horas anteriores'),
    ('carla', 2, 'PR-ABC', 'instrucao', 60, 6, 'Tráfego'),
    ('carla', 15, 'PR-ABC', 'instrucao', 72, 5, 'Toque e arremetida'),
    ('carla', 33, 'PR-GHI', 'instrucao', 90, 2, 'Área'),
    ('diego', 5, 'PR-GHI', 'solo', 54, 4, 'Primeiro solo de área'),
    ('diego', 20, 'PR-ABC', 'instrucao', 90, 3, 'Área'),
    ('diego', 100, 'PR-ABC', 'instrucao', 600, 40, 'Horas anteriores'),
    ('eduarda', 3, 'PR-DEF', 'comando', 126, 2, 'Navegação SBXX-SBYY'),
    ('eduarda', 60, 'PR-DEF', 'comando', 2400, 55, 'Horas anteriores'),
]


def criar_demo():
    """Cria os dados só se o banco estiver vazio. Devolve True se criou."""
    if Usuario.query.first():
        return False

    hoje = validades.hoje_local()
    pessoas = {}
    for nome, email, papel in USUARIOS:
        u = Usuario(nome=nome, email=email, papel=papel)
        u.definir_senha(SENHA_DEMO)
        db.session.add(u)
        pessoas[email.split('@')[0]] = u

    for pessoa, tipo, descricao, dias in DOCUMENTOS:
        db.session.add(Documento(dono=pessoas[pessoa], tipo=tipo, descricao=descricao,
                                 vencimento=hoje + timedelta(days=dias)))

    for pessoa, dias_atras, matricula, funcao, minutos, pousos, obs in VOOS:
        db.session.add(Voo(piloto=pessoas[pessoa], data=hoje - timedelta(days=dias_atras),
                           matricula=matricula, funcao=funcao, minutos=minutos,
                           pousos=pousos, observacao=obs))

    db.session.commit()
    return True
