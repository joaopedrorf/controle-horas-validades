import hmac
import os
import secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from modelos import FUNCOES, PAPEIS, TIPOS_DOCUMENTO, Aviso, Documento, Usuario, Voo, db
import avisos
import validades
from seguranca import LimitadorDeTentativas, aplicar_cabecalhos
from textos import TEXTOS

load_dotenv()


def endereco_banco():
    """SQLite local por padrão; no Render, usa o DATABASE_URL do Postgres se existir."""
    url = os.getenv('DATABASE_URL', 'sqlite:///controle.db')
    # O Render entrega 'postgres://', mas o SQLAlchemy só aceita 'postgresql://'
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


def create_app(config=None):
    app = Flask(__name__)
    # Sem SECRET_KEY definida, cria uma aleatória: nunca usa uma chave fixa conhecida.
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or secrets.token_hex(32)
    app.config['SQLALCHEMY_DATABASE_URI'] = endereco_banco()
    app.config['DEMO'] = os.getenv('DEMO', '1') == '1'
    # Senha que o agendador diário (GitHub Actions) usa para pedir o envio dos avisos
    app.config['AVISOS_TOKEN'] = os.getenv('AVISOS_TOKEN', '')
    em_producao = bool(os.getenv('RENDER')) or os.getenv('COOKIE_SEGURO') == '1'
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=em_producao,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=em_producao,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    app.limitador = LimitadorDeTentativas()
    if config:
        app.config.update(config)

    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def carregar_usuario(usuario_id):
        return db.session.get(Usuario, int(usuario_id))

    @login_manager.unauthorized_handler
    def sem_login():
        flash(textos()['precisa_login'], 'erro')
        return redirect(url_for('login'))

    with app.app_context():
        db.create_all()
        if app.config['DEMO']:
            from demo import criar_demo
            criar_demo()

    registrar_rotas(app)

    @app.cli.command('criar-demo')
    def comando_criar_demo():
        """flask --app app criar-demo: preenche o banco com dados de exemplo."""
        from demo import criar_demo
        print('Dados criados.' if criar_demo() else 'O banco já tem dados.')

    @app.cli.command('enviar-avisos')
    def comando_enviar_avisos():
        """flask --app app enviar-avisos: manda os lembretes de vencimento do dia."""
        print(f'{avisos.enviar_pendentes()} aviso(s) enviado(s).')

    return app


# ---------- Idioma e segurança ----------

def idioma_atual():
    idioma = session.get('idioma', 'pt')
    return idioma if idioma in TEXTOS else 'pt'


def textos():
    return TEXTOS[idioma_atual()]


def token_csrf():
    """Token secreto por sessão: impede que outro site envie formulários em nome do usuário."""
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(16)
    return session['csrf']


def somente_admin():
    if not current_user.is_admin:
        abort(403)


def pode_mexer(usuario_id):
    """O piloto mexe só nos próprios registros; a secretaria mexe em todos."""
    if usuario_id != current_user.id and not current_user.is_admin:
        abort(403)


def ler_data(texto):
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def mostrar_data(dia):
    """28/10/2026 em português, 2026-10-28 em inglês (sem confusão de mês e dia)."""
    return dia.strftime('%d/%m/%Y' if idioma_atual() == 'pt' else '%Y-%m-%d')


def iniciais(nome):
    nome = nome.removeprefix('Cmte.').strip()  # 'Cmte. Ana Souza' vira 'AS'
    partes = nome.split()
    return ''.join(p[0] for p in (partes[:1] + partes[-1:] if len(partes) > 1 else partes)) or '?'


def contas_demo():
    from demo import USUARIOS
    return USUARIOS


def documentos_ativos():
    """Documentos de todos os pilotos ativos, do que vence primeiro ao último."""
    return Documento.query.join(Usuario).filter(Usuario.ativo.is_(True)) \
        .order_by(Documento.vencimento).all()


def entrar_na_sessao(usuario):
    """Começa uma sessão nova no login (evita reaproveitar uma sessão antiga)."""
    idioma = idioma_atual()
    session.clear()
    session['idioma'] = idioma
    session.permanent = True
    login_user(usuario)


def registrar_rotas(app):

    @app.before_request
    def conferir_csrf():
        # A rota do agendador usa token próprio no cabeçalho, não formulário
        if request.endpoint == 'tarefa_avisos':
            return
        if request.method == 'POST' and not app.config.get('TESTING_SEM_CSRF'):
            enviado = request.form.get('csrf')
            if not enviado or enviado != session.get('csrf'):
                abort(400)

    @app.context_processor
    def variaveis_do_template():
        hoje = validades.hoje_local()
        return {
            't': textos(),
            'idioma': idioma_atual(),
            'csrf': token_csrf(),
            'demo': app.config['DEMO'],
            'iniciais': iniciais,
            'pagina': request.endpoint,
            'hoje': hoje,
            'data': mostrar_data,
            'horas': validades.formatar_horas,
            'situacao': lambda doc: validades.situacao(doc.vencimento, hoje),
            'dias': lambda doc: validades.dias_restantes(doc.vencimento, hoje),
            'tipos': TIPOS_DOCUMENTO,
            'funcoes': FUNCOES,
        }

    @app.errorhandler(403)
    def proibido(_erro):
        flash(textos()['sem_permissao'], 'erro')
        return redirect(url_for('painel'))

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def pagina_de_erro(erro):
        codigo = getattr(erro, 'code', 500)
        if codigo == 500:
            db.session.rollback()
        return render_template('erro.html', codigo=codigo), codigo

    @app.after_request
    def cabecalhos(resposta):
        return aplicar_cabecalhos(resposta)

    @app.route('/idioma/<codigo>')
    def trocar_idioma(codigo):
        if codigo in TEXTOS:
            session['idioma'] = codigo
        destino = request.referrer or url_for('painel')
        # Só volta para páginas do próprio site
        if not destino.startswith(request.host_url):
            destino = url_for('painel')
        return redirect(destino)

    # ---------- Login ----------

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('painel'))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            chave = (request.remote_addr, email)
            if app.limitador.bloqueado(chave):
                flash(textos()['muitas_tentativas'], 'erro')
                return render_template('login.html', contas_demo=contas_demo()), 429
            usuario = Usuario.query.filter_by(email=email).first()
            if usuario and usuario.ativo and usuario.conferir_senha(request.form.get('senha', '')):
                app.limitador.limpar(chave)
                entrar_na_sessao(usuario)
                return redirect(url_for('painel'))
            app.limitador.registrar_falha(chave)
            # Mesma mensagem para e-mail inexistente e senha errada: não revela quem tem conta
            flash(textos()['login_invalido'], 'erro')
        return render_template('login.html', contas_demo=contas_demo())

    @app.route('/sair', methods=['POST'])
    @login_required
    def sair():
        logout_user()
        idioma = idioma_atual()
        session.clear()
        session['idioma'] = idioma
        return redirect(url_for('login'))

    @app.route('/saude')
    def saude():
        """O Render consulta esta página para saber se o site está no ar."""
        db.session.execute(db.text('SELECT 1'))
        return {'status': 'ok'}

    # ---------- Painel ----------

    @app.route('/')
    @login_required
    def painel():
        hoje = validades.hoje_local()
        if current_user.is_admin:
            documentos = documentos_ativos()
            return render_template(
                'painel_admin.html',
                contagem=validades.contar_situacoes(documentos, hoje),
                atencao=[d for d in documentos if validades.situacao(d.vencimento, hoje) != 'em_dia'],
                pendentes=len(avisos.pendentes(hoje)),
            )
        return render_template(
            'painel.html',
            contagem=validades.contar_situacoes(current_user.documentos, hoje),
            resumo=validades.totais(current_user.voos, hoje),
            ultimos=current_user.voos[:5],
        )

    # ---------- Documentos ----------

    @app.route('/documentos', methods=['GET', 'POST'])
    @login_required
    def documentos():
        t = textos()
        if request.method == 'POST':
            # A secretaria pode cadastrar para outro piloto (vem da página do piloto)
            dono_id = int(request.form.get('usuario_id') or current_user.id)
            pode_mexer(dono_id)
            tipo = request.form.get('tipo', '')
            vencimento = ler_data(request.form.get('vencimento'))
            if tipo not in TIPOS_DOCUMENTO or not vencimento or not db.session.get(Usuario, dono_id):
                flash(t['dados_invalidos'], 'erro')
            else:
                db.session.add(Documento(usuario_id=dono_id, tipo=tipo, vencimento=vencimento,
                                         descricao=request.form.get('descricao', '').strip()[:80]))
                db.session.commit()
                flash(t['documento_salvo'], 'ok')
            return redirect(voltar_para(dono_id))
        return render_template('documentos.html', lista=current_user.documentos)

    def voltar_para(dono_id):
        if dono_id != current_user.id:
            return url_for('piloto', usuario_id=dono_id)
        return url_for('documentos')

    @app.route('/documentos/<int:documento_id>/renovar', methods=['POST'])
    @login_required
    def renovar_documento(documento_id):
        doc = db.session.get(Documento, documento_id) or abort(404)
        pode_mexer(doc.usuario_id)
        vencimento = ler_data(request.form.get('vencimento'))
        if not vencimento:
            flash(textos()['dados_invalidos'], 'erro')
        else:
            doc.vencimento = vencimento
            db.session.commit()
            flash(textos()['documento_renovado'], 'ok')
        return redirect(voltar_para(doc.usuario_id))

    @app.route('/documentos/<int:documento_id>/excluir', methods=['POST'])
    @login_required
    def excluir_documento(documento_id):
        doc = db.session.get(Documento, documento_id) or abort(404)
        pode_mexer(doc.usuario_id)
        dono_id = doc.usuario_id
        db.session.delete(doc)
        db.session.commit()
        flash(textos()['documento_excluido'], 'ok')
        return redirect(voltar_para(dono_id))

    # ---------- Voos ----------

    @app.route('/voos', methods=['GET', 'POST'])
    @login_required
    def voos():
        t = textos()
        form = {}
        if request.method == 'POST':
            form = request.form
            dia = ler_data(form.get('data'))
            minutos = validades.ler_duracao(form.get('tempo'))
            matricula = form.get('matricula', '').strip().upper()
            funcao = form.get('funcao', '')
            try:
                pousos = int(form.get('pousos') or 0)
            except ValueError:
                pousos = -1
            erros = []
            if not dia or not matricula or funcao not in FUNCOES or not 0 <= pousos <= 99:
                erros.append(t['dados_invalidos'])
            elif dia > validades.hoje_local():
                erros.append(t['voo_futuro'])
            if minutos is None:
                erros.append(t['tempo_invalido'])
            if not erros:
                db.session.add(Voo(usuario_id=current_user.id, data=dia, matricula=matricula[:10],
                                   funcao=funcao, minutos=minutos, pousos=pousos,
                                   observacao=form.get('observacao', '').strip()[:200]))
                db.session.commit()
                flash(t['voo_salvo'], 'ok')
                return redirect(url_for('voos'))
            for erro in erros:
                flash(erro, 'erro')
        return render_template('voos.html', lista=current_user.voos, form=form,
                               resumo=validades.totais(current_user.voos)), 400 if request.method == 'POST' else 200

    @app.route('/voos/<int:voo_id>/excluir', methods=['POST'])
    @login_required
    def excluir_voo(voo_id):
        voo = db.session.get(Voo, voo_id) or abort(404)
        pode_mexer(voo.usuario_id)
        db.session.delete(voo)
        db.session.commit()
        flash(textos()['voo_excluido'], 'ok')
        return redirect(url_for('voos'))

    # ---------- Secretaria ----------

    @app.route('/pilotos', methods=['GET', 'POST'])
    @login_required
    def pilotos():
        somente_admin()
        t = textos()
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip().lower()
            senha = request.form.get('senha', '')
            papel = request.form.get('papel', 'piloto')
            if not nome or '@' not in email or papel not in PAPEIS:
                flash(t['dados_invalidos'], 'erro')
            elif len(senha) < 8:
                flash(t['senha_curta'], 'erro')
            elif Usuario.query.filter_by(email=email).first():
                flash(t['email_existe'], 'erro')
            else:
                u = Usuario(nome=nome[:100], email=email[:120], papel=papel)
                u.definir_senha(senha)
                db.session.add(u)
                db.session.commit()
                flash(t['usuario_salvo'], 'ok')
            return redirect(url_for('pilotos'))
        hoje = validades.hoje_local()
        lista = [{
            'usuario': u,
            'contagem': validades.contar_situacoes(u.documentos, hoje),
            'total': validades.totais(u.voos, hoje)['total'],
        } for u in Usuario.query.order_by(Usuario.papel.desc(), Usuario.nome).all()]
        return render_template('pilotos.html', lista=lista, papeis=PAPEIS)

    @app.route('/pilotos/<int:usuario_id>')
    @login_required
    def piloto(usuario_id):
        somente_admin()
        usuario = db.session.get(Usuario, usuario_id) or abort(404)
        return render_template('piloto.html', usuario=usuario, resumo=validades.totais(usuario.voos))

    @app.route('/pilotos/<int:usuario_id>/alternar', methods=['POST'])
    @login_required
    def alternar_usuario(usuario_id):
        somente_admin()
        usuario = db.session.get(Usuario, usuario_id) or abort(404)
        if usuario.id != current_user.id:  # Ninguém desativa a própria conta
            usuario.ativo = not usuario.ativo
            db.session.commit()
        return redirect(url_for('pilotos'))

    @app.route('/avisos')
    @login_required
    def lista_avisos():
        somente_admin()
        historico = Aviso.query.order_by(Aviso.enviado_em.desc()).limit(50).all()
        return render_template('avisos.html', pendentes=avisos.pendentes(), historico=historico,
                               smtp=bool(avisos.configuracao_smtp()['host']))

    @app.route('/avisos/enviar', methods=['POST'])
    @login_required
    def enviar_avisos():
        somente_admin()
        try:
            quantos = avisos.enviar_pendentes()
        except OSError:  # Servidor de e-mail fora do ar ou senha errada
            db.session.rollback()
            flash(textos()['email_falhou'], 'erro')
        else:
            flash(textos()['avisos_enviados'].format(n=quantos), 'ok')
        return redirect(url_for('lista_avisos'))

    @app.route('/tarefas/avisos', methods=['POST'])
    def tarefa_avisos():
        """Chamada uma vez por dia pelo GitHub Actions (ver .github/workflows/avisos.yml)."""
        token = app.config['AVISOS_TOKEN']
        enviado = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if not token or not hmac.compare_digest(enviado, token):
            abort(404)  # Sem token configurado, a rota nem "existe"
        return {'enviados': avisos.enviar_pendentes()}


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
