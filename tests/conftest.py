import os
import sys

# Banco em memória e sem dados de exemplo automáticos durante os testes
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['DEMO'] = '0'
os.environ.pop('SMTP_HOST', None)

# Permite importar app.py, validades.py etc. a partir da pasta tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from demo import criar_demo  # noqa: E402
from modelos import db  # noqa: E402


@pytest.fixture
def app():
    app = create_app({'TESTING': True, 'TESTING_SEM_CSRF': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                      'AVISOS_TOKEN': 'token-de-teste'})
    with app.app_context():
        criar_demo()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def entrar(client, email, senha='demo123'):
    return client.post('/login', data={'email': email, 'senha': senha}, follow_redirects=True)
