from datetime import datetime, timedelta

import avisos
import validades
from modelos import Aviso, Documento, Usuario, db


def hoje():
    return validades.hoje_local()


def test_demo_tem_avisos_pendentes(app):
    pendentes = avisos.pendentes()
    marcos = {(d.dono.email, d.tipo): m for d, m in pendentes}
    # Ver demo.py: INVA da Ana vence em 5 dias, CMA da Carla em 25, CMA do Diego venceu
    assert marcos[('ana@demo.com', 'instrutor')] == 7
    assert marcos[('carla@demo.com', 'cma')] == 30
    assert marcos[('diego@demo.com', 'cma')] == 0
    assert marcos[('eduarda@demo.com', 'habilitacao')] == 0
    # Documentos longe do vencimento não entram
    assert ('ana@demo.com', 'cma') not in marcos


def test_envio_simulado_sem_smtp_registra_e_nao_repete(app):
    quantos = avisos.enviar_pendentes()
    assert quantos == len(Aviso.query.all()) > 0
    assert all(a.simulado for a in Aviso.query.all())
    assert avisos.enviar_pendentes() == 0  # Mesmo dia: nada de novo


def test_envio_real_monta_email_bilingue(app):
    enviados = []
    avisos.enviar_pendentes(enviar=enviados.append)
    assert enviados
    msg = next(m for m in enviados if m['To'] == 'carla@demo.com')
    assert 'admin@demo.com' in msg['Cc']
    assert 'vence em 25 dia(s)' in msg['Subject'] and 'expires in 25 day(s)' in msg['Subject']
    corpo = msg.get_content()
    assert 'Olá, Carla Mendes' in corpo and 'Hello, Carla Mendes' in corpo
    assert not any(a.simulado for a in Aviso.query.all())


def test_documento_renovado_volta_a_receber_aviso(app):
    avisos.enviar_pendentes()
    doc = Documento.query.join(Usuario).filter(Usuario.email == 'diego@demo.com', Documento.tipo == 'cma').one()
    # Renovou por um ano: some dos pendentes
    doc.vencimento = hoje() + timedelta(days=365)
    db.session.commit()
    assert doc not in [d for d, _ in avisos.pendentes()]
    # Um ano depois, faltando 30 dias, o aviso de 30 dias sai de novo
    assert (doc, 30) in avisos.pendentes(hoje() + timedelta(days=335))


def test_dias_sem_rodar_manda_so_o_aviso_mais_recente(app):
    u = Usuario.query.filter_by(email='carla@demo.com').one()
    doc = Documento(usuario_id=u.id, tipo='outro', vencimento=hoje() + timedelta(days=3))
    db.session.add(doc)
    db.session.commit()
    marcos = [m for d, m in avisos.pendentes() if d.id == doc.id]
    assert marcos == [7]


def test_piloto_desativado_nao_recebe(app):
    u = Usuario.query.filter_by(email='diego@demo.com').one()
    u.ativo = False
    db.session.commit()
    assert all(d.dono.email != 'diego@demo.com' for d, _ in avisos.pendentes())


def test_registro_guarda_horario(app):
    momento = datetime(2026, 10, 28, 7, 0)
    avisos.enviar_pendentes(agora=momento)
    assert Aviso.query.first().enviado_em == momento
