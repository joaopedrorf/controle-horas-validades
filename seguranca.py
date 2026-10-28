"""Proteções extras do login e cabeçalhos de segurança das páginas."""
import time

# Depois de 5 senhas erradas em 15 minutos, o mesmo e-mail (vindo do mesmo
# endereço de internet) fica bloqueado por 15 minutos. Isso impede que alguém
# fique testando senhas sem parar.
MAX_TENTATIVAS = 5
JANELA_SEGUNDOS = 15 * 60


class LimitadorDeTentativas:
    """Guarda as falhas de login na memória do servidor.

    Simples de propósito: com um único processo (como no render.yaml) é
    suficiente. Com vários servidores, o ideal é guardar isso num Redis.
    """

    def __init__(self, maximo=MAX_TENTATIVAS, janela=JANELA_SEGUNDOS, relogio=time.monotonic):
        self.maximo = maximo
        self.janela = janela
        self.relogio = relogio
        self.falhas = {}

    def _recentes(self, chave):
        limite = self.relogio() - self.janela
        recentes = [t for t in self.falhas.get(chave, []) if t > limite]
        if recentes:
            self.falhas[chave] = recentes
        else:
            self.falhas.pop(chave, None)
        return recentes

    def bloqueado(self, chave):
        return len(self._recentes(chave)) >= self.maximo

    def registrar_falha(self, chave):
        self.falhas.setdefault(chave, []).append(self.relogio())

    def limpar(self, chave):
        self.falhas.pop(chave, None)


# Fontes e estilos do Google Fonts são as únicas coisas carregadas de fora.
POLITICA_CONTEUDO = "; ".join([
    "default-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "script-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
])


def aplicar_cabecalhos(resposta):
    resposta.headers.setdefault('Content-Security-Policy', POLITICA_CONTEUDO)
    resposta.headers.setdefault('X-Content-Type-Options', 'nosniff')      # não "adivinha" tipo de arquivo
    resposta.headers.setdefault('X-Frame-Options', 'DENY')                # ninguém embute o site em outro
    resposta.headers.setdefault('Referrer-Policy', 'same-origin')
    resposta.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    return resposta
