from conftest import entrar
from modelos import Usuario
from seguranca import LimitadorDeTentativas


def test_senhas_ficam_guardadas_como_hash(app):
    carla = Usuario.query.filter_by(email='carla@demo.com').one()
    assert 'demo123' not in carla.senha_hash
    assert carla.senha_hash.startswith(('scrypt:', 'pbkdf2:'))


def test_limitador_bloqueia_e_libera_depois_da_janela():
    tempo = [0]
    limitador = LimitadorDeTentativas(maximo=3, janela=60, relogio=lambda: tempo[0])
    for _ in range(3):
        limitador.registrar_falha('x')
    assert limitador.bloqueado('x')
    tempo[0] = 61
    assert not limitador.bloqueado('x')


def test_login_bloqueia_apos_cinco_erros(client):
    for _ in range(5):
        entrar(client, 'carla@demo.com', 'errada')
    resposta = client.post('/login', data={'email': 'carla@demo.com', 'senha': 'demo123'})
    assert resposta.status_code == 429


def test_cabecalhos_de_seguranca(client):
    resposta = client.get('/login')
    assert resposta.headers['X-Frame-Options'] == 'DENY'
    assert "frame-ancestors 'none'" in resposta.headers['Content-Security-Policy']


def test_csrf_recusa_formulario_sem_token(app):
    app.config['TESTING_SEM_CSRF'] = False
    resposta = app.test_client().post('/login', data={'email': 'carla@demo.com', 'senha': 'demo123'})
    assert resposta.status_code == 400


def test_tarefa_de_avisos_exige_token(client):
    assert client.post('/tarefas/avisos').status_code == 404
    assert client.post('/tarefas/avisos', headers={'Authorization': 'Bearer errado'}).status_code == 404
    resposta = client.post('/tarefas/avisos', headers={'Authorization': 'Bearer token-de-teste'})
    assert resposta.status_code == 200
    assert resposta.json['enviados'] > 0


def test_tarefa_de_avisos_desligada_sem_token_configurado(app, client):
    app.config['AVISOS_TOKEN'] = ''
    assert client.post('/tarefas/avisos', headers={'Authorization': 'Bearer '}).status_code == 404


def test_saude(client):
    assert client.get('/saude').json == {'status': 'ok'}
