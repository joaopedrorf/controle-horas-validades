from datetime import timedelta

from conftest import entrar
from modelos import Aviso, Documento, Usuario, Voo, db
import validades


def doc_de(email, tipo):
    return Documento.query.join(Usuario).filter(Usuario.email == email, Documento.tipo == tipo).one()


def test_login_e_painel_do_piloto(client):
    resposta = entrar(client, 'diego@demo.com')
    assert 'Olá, Diego Rocha' in resposta.text
    assert 'Vencido' in resposta.text          # CMA do Diego venceu há 12 dias
    assert 'venceu há 12 dia(s)' in resposta.text


def test_login_errado(client):
    assert 'incorretos' in entrar(client, 'diego@demo.com', 'errada').text


def test_paginas_pedem_login(client):
    for pagina in ('/', '/voos', '/documentos', '/pilotos', '/avisos'):
        assert client.get(pagina).status_code == 302


def test_painel_em_ingles(client):
    entrar(client, 'diego@demo.com')
    client.get('/idioma/en')
    resposta = client.get('/')
    assert 'Hello, Diego Rocha' in resposta.text
    assert 'expired 12 day(s) ago' in resposta.text


def test_registrar_voo(client):
    entrar(client, 'carla@demo.com')
    dados = {'data': validades.hoje_local().isoformat(), 'matricula': 'pr-abc', 'funcao': 'solo',
             'tempo': '1:12', 'pousos': '4', 'observacao': 'Primeiro solo'}
    resposta = client.post('/voos', data=dados, follow_redirects=True)
    assert 'Voo registrado' in resposta.text
    voo = Voo.query.filter_by(observacao='Primeiro solo').one()
    assert (voo.matricula, voo.minutos, voo.pousos) == ('PR-ABC', 72, 4)


def test_voo_com_tempo_invalido_ou_no_futuro(client):
    entrar(client, 'carla@demo.com')
    amanha = (validades.hoje_local() + timedelta(days=1)).isoformat()
    resposta = client.post('/voos', data={'data': amanha, 'matricula': 'PR-ABC', 'funcao': 'solo', 'tempo': '1:99'})
    assert resposta.status_code == 400
    assert 'futuro' in resposta.text and 'Tempo de voo inválido' in resposta.text
    assert 'PR-ABC' in resposta.text  # O formulário volta preenchido


def test_piloto_nao_apaga_voo_de_outro(client):
    entrar(client, 'carla@demo.com')
    voo_do_diego = Voo.query.join(Usuario).filter(Usuario.email == 'diego@demo.com').first()
    client.post(f'/voos/{voo_do_diego.id}/excluir')
    assert db.session.get(Voo, voo_do_diego.id) is not None


def test_cadastrar_e_renovar_documento(client):
    entrar(client, 'diego@demo.com')
    client.post('/documentos', data={'tipo': 'ingles', 'descricao': 'Nível 4', 'vencimento': '2029-05-01'})
    doc = doc_de('diego@demo.com', 'ingles')
    assert doc.descricao == 'Nível 4'

    cma = doc_de('diego@demo.com', 'cma')
    novo = validades.hoje_local() + timedelta(days=365)
    resposta = client.post(f'/documentos/{cma.id}/renovar', data={'vencimento': novo.isoformat()}, follow_redirects=True)
    assert 'Vencimento atualizado' in resposta.text
    assert cma.vencimento == novo


def test_documento_com_dados_invalidos(client):
    entrar(client, 'diego@demo.com')
    resposta = client.post('/documentos', data={'tipo': 'passaporte', 'vencimento': 'amanhã'}, follow_redirects=True)
    assert 'Confira os dados' in resposta.text


def test_piloto_nao_mexe_em_documento_de_outro(client):
    entrar(client, 'carla@demo.com')
    cma_diego = doc_de('diego@demo.com', 'cma')
    client.post(f'/documentos/{cma_diego.id}/excluir')
    client.post('/documentos', data={'tipo': 'outro', 'vencimento': '2030-01-01', 'usuario_id': cma_diego.usuario_id})
    assert db.session.get(Documento, cma_diego.id) is not None
    assert not Documento.query.filter_by(usuario_id=cma_diego.usuario_id, tipo='outro').first()


def test_piloto_nao_ve_paginas_da_secretaria(client):
    entrar(client, 'carla@demo.com')
    for pagina in ('/pilotos', '/avisos'):
        resposta = client.get(pagina, follow_redirects=True)
        assert 'permissão' in resposta.text


def test_painel_da_secretaria(client):
    resposta = entrar(client, 'admin@demo.com')
    assert 'Validades do aeroclube' in resposta.text
    assert 'Diego Rocha' in resposta.text      # CMA vencido aparece
    assert 'Proficiência em inglês' not in resposta.text  # Em dia não aparece na lista de atenção


def test_secretaria_cadastra_documento_para_piloto(client):
    entrar(client, 'admin@demo.com')
    carla = Usuario.query.filter_by(email='carla@demo.com').one()
    resposta = client.post('/documentos', data={'tipo': 'ifr', 'vencimento': '2028-03-01', 'usuario_id': carla.id},
                           follow_redirects=True)
    assert 'Carla Mendes' in resposta.text  # Volta para a página da piloto
    assert doc_de('carla@demo.com', 'ifr')


def test_secretaria_cadastra_e_desativa_piloto(client):
    entrar(client, 'admin@demo.com')
    client.post('/pilotos', data={'nome': 'Fábio Nunes', 'email': 'fabio@demo.com', 'senha': 'senha-longa', 'papel': 'piloto'})
    fabio = Usuario.query.filter_by(email='fabio@demo.com').one()
    client.post(f'/pilotos/{fabio.id}/alternar')
    assert not fabio.ativo
    assert 'senha precisa' in client.post('/pilotos', data={'nome': 'X', 'email': 'x@x.com', 'senha': 'curta'},
                                          follow_redirects=True).text


def test_secretaria_envia_avisos_pela_tela(client):
    entrar(client, 'admin@demo.com')
    pagina = client.get('/avisos').text
    assert 'Modo demonstração' in pagina and '7 dias antes' in pagina
    resposta = client.post('/avisos/enviar', follow_redirects=True)
    assert 'aviso(s) enviado(s)' in resposta.text
    assert 'Simulado' in resposta.text
    assert Aviso.query.count() > 0
    assert 'Nenhum aviso pendente' in client.get('/avisos').text


def test_pagina_404_amigavel(client):
    resposta = client.get('/nao-existe')
    assert resposta.status_code == 404
    assert 'Página não encontrada' in resposta.text
