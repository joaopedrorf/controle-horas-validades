"""Lembretes de vencimento por e-mail.

Uma vez por dia (ver .github/workflows/avisos.yml ou o botão "Enviar agora"),
o sistema procura documentos que chegaram a 30 dias, 7 dias ou ao dia do
vencimento e manda um e-mail para o piloto, com cópia para a secretaria.

Sem servidor de e-mail configurado (SMTP_HOST vazio, como na demonstração),
o aviso é só registrado na tela como "simulado".
"""
import os
import smtplib
from email.message import EmailMessage

from modelos import Aviso, Documento, Usuario, db
import validades
from textos import TEXTOS


def pendentes(hoje=None):
    """Lista de (documento, marco) que ainda não foram avisados."""
    hoje = hoje or validades.hoje_local()
    lista = []
    documentos = Documento.query.join(Usuario).filter(Usuario.ativo.is_(True)) \
        .order_by(Documento.vencimento).all()
    for doc in documentos:
        marco = validades.marco_devido(doc.vencimento, hoje)
        if marco is None:
            continue
        # O vencimento entra na conta: documento renovado volta a receber avisos
        ja_enviado = any(a.marco == marco and a.vencimento == doc.vencimento for a in doc.avisos)
        if not ja_enviado:
            lista.append((doc, marco))
    return lista


def nome_documento(doc, idioma):
    nome = TEXTOS[idioma]['tipo_' + doc.tipo]
    return f"{nome} ({doc.descricao})" if doc.descricao else nome


def montar_email(doc, hoje, remetente, copias):
    """E-mail bilíngue: português primeiro, inglês embaixo (como no resto do sistema)."""
    dias = validades.dias_restantes(doc.vencimento, hoje)
    data = doc.vencimento.strftime('%d/%m/%Y')
    pt, en = TEXTOS['pt'], TEXTOS['en']
    if dias > 0:
        assunto = ' / '.join(t['email_assunto_vence'].format(doc=nome_documento(doc, i), dias=dias)
                             for i, t in TEXTOS.items())
        corpo_pt = pt['email_vence'].format(nome=doc.dono.nome, doc=nome_documento(doc, 'pt'), dias=dias, data=data)
        corpo_en = en['email_vence'].format(nome=doc.dono.nome, doc=nome_documento(doc, 'en'), dias=dias,
                                            data=doc.vencimento.strftime('%Y-%m-%d'))
    else:
        assunto = ' / '.join(t['email_assunto_venceu'].format(doc=nome_documento(doc, i))
                             for i, t in TEXTOS.items())
        corpo_pt = pt['email_venceu'].format(nome=doc.dono.nome, doc=nome_documento(doc, 'pt'), data=data)
        corpo_en = en['email_venceu'].format(nome=doc.dono.nome, doc=nome_documento(doc, 'en'),
                                             data=doc.vencimento.strftime('%Y-%m-%d'))

    msg = EmailMessage()
    msg['Subject'] = assunto
    msg['From'] = remetente
    msg['To'] = doc.dono.email
    if copias:
        msg['Cc'] = ', '.join(copias)
    msg.set_content(f"{corpo_pt}\n\n---\n\n{corpo_en}\n")
    return msg


def configuracao_smtp():
    return {
        'host': os.getenv('SMTP_HOST', ''),
        'porta': int(os.getenv('SMTP_PORTA', '587')),
        'usuario': os.getenv('SMTP_USUARIO', ''),
        'senha': os.getenv('SMTP_SENHA', ''),
        'remetente': os.getenv('EMAIL_REMETENTE', 'avisos@exemplo.com'),
    }


def enviar_pendentes(hoje=None, agora=None, enviar=None):
    """Envia os avisos pendentes e registra cada um. Devolve quantos saíram.

    `enviar` permite trocar o envio real nos testes.
    """
    hoje = hoje or validades.hoje_local()
    agora = agora or validades.agora_local()
    config = configuracao_smtp()
    simulado = not config['host'] and enviar is None
    copias = [u.email for u in Usuario.query.filter_by(papel='admin', ativo=True).all()]

    lista = pendentes(hoje)
    if lista and not simulado and enviar is None:
        servidor = smtplib.SMTP(config['host'], config['porta'], timeout=20)
        servidor.starttls()
        if config['usuario']:
            servidor.login(config['usuario'], config['senha'])
        enviar = servidor.send_message
    else:
        servidor = None

    try:
        for doc, marco in lista:
            if not simulado:
                enviar(montar_email(doc, hoje, config['remetente'],
                                    [c for c in copias if c != doc.dono.email]))
            db.session.add(Aviso(documento_id=doc.id, marco=marco, vencimento=doc.vencimento,
                                 enviado_em=agora, simulado=simulado))
            db.session.commit()  # Um por um: se o e-mail 3 falhar, os 2 primeiros ficam registrados
    finally:
        if servidor:
            servidor.quit()
    return len(lista)
