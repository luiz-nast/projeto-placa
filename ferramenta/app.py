"""app.py: abre o Sianvolt como um app. Serve o repositorio so pra esta maquina e abre uma janela.

uso: python3 ferramenta/app.py               (abre a janela; fecha sozinho uns minutos depois da janela)
     python3 ferramenta/app.py --sem-janela  (so o servidor, ate o Ctrl+C)
"""
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import blocos
import catalogo
import loja

RAIZ = Path(__file__).resolve().parent.parent
PLACAS = RAIZ / "placas"
PORTA = 8765
OCIOSO = 180          # sem nenhum pedido por 3 min (janela fechada), o app fecha
HOSTS = {f"127.0.0.1:{PORTA}", f"localhost:{PORTA}"}   # so o navegador desta maquina; outro nome no Host e golpe (DNS rebinding)
SERVIDO = ("/bancada/", "/placas/")                     # o resto do repositorio (.git, .claude...) nao sai daqui
rodando = {}          # placa -> processo do testar.py
trava = threading.Lock()
ultimo = [time.monotonic()]


def python():
    """o python do .venv (tem o gerbonara), se existir"""
    venv = RAIZ / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def placa(nome):
    """pasta da placa, so se for uma pasta direto dentro de placas/ com placa.txt"""
    try:
        pasta = (PLACAS / nome).resolve()
        if nome and pasta.parent == PLACAS.resolve() and (pasta / "placa.txt").exists():
            return pasta
    except (ValueError, OSError):   # nome com byte nulo e afins
        pass
    return None


def usos():
    """codigo -> ["lanterna: R1", ...]: que placa usa cada peca do catalogo"""
    quem = {}
    for pasta in sorted(PLACAS.iterdir()) if PLACAS.exists() else []:
        proj = placa(pasta.name) and blocos.ler_projeto(pasta)
        for b in (proj or {}).get("blocos", []):
            if b.get("peca"):
                quem.setdefault(b["peca"], []).append(f"{pasta.name}: {b['ref']}")
    return quem


def rodar_testes(pasta, frase=None):
    """dispara o testar.py dessa placa (um por vez); chamar com a trava. frase = o que mudou, pra versao"""
    if pasta.name in rodando and rodando[pasta.name].poll() is None:
        return False
    rodando[pasta.name] = subprocess.Popen([python(), str(RAIZ / "ferramenta" / "testar.py"), str(pasta), *(["-m", frase] if frase else [])], cwd=RAIZ,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


class Bancada(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # a bancada sempre ve o arquivo que acabou de mudar
        super().end_headers()

    def log_message(self, *args):
        pass

    def responder(self, dado, codigo=200):
        corpo = json.dumps(dado, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def servido(self, url):
        """so bancada/ e placas/, ja resolvido (nada de /bancada/../.git)"""
        if not url.path.startswith(SERVIDO):
            return False
        alvo = Path(self.translate_path(url.path)).resolve()
        return any(alvo == RAIZ / d or (RAIZ / d) in alvo.parents for d in ("bancada", "placas"))

    def do_HEAD(self):
        url = urlparse(self.path)
        if self.headers.get("Host") not in HOSTS or not self.servido(url):
            self.send_response(404)
            self.end_headers()
            return
        super().do_HEAD()

    def do_GET(self):
        ultimo[0] = time.monotonic()
        url = urlparse(self.path)
        if self.headers.get("Host") not in HOSTS:
            return self.responder({"erro": "host"}, 403)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/projeto":
            pasta = placa(q.get("placa", ""))
            return self.responder(blocos.estado(pasta) if pasta else {"erro": "placa não existe"}, 200 if pasta else 404)
        if url.path == "/api/catalogo":
            return self.responder({**catalogo.ler(), "usos": usos(), "grupos": catalogo.GRUPOS, "traducoes": catalogo.TRADUCOES})
        if url.path == "/api/opcoes":
            pasta = placa(q.get("placa", ""))
            if not pasta:
                return self.responder({"erro": "placa não existe"}, 404)
            try:
                with trava:   # pode escrever no catalogo
                    return self.responder(blocos.opcoes(pasta, q.get("ref", ""), online=q.get("online") == "1"))
            except ValueError as e:
                return self.responder({"erro": str(e)}, 400)
            except loja.SemLoja as e:
                return self.responder({"erro": str(e)}, 502)
        if url.path == "/api/foto":
            return self.foto(q.get("codigo", ""))
        if url.path == "/":
            self.send_response(302)
            self.send_header("Location", "/bancada/")
            self.end_headers()
            return
        if url.path == "/api/placas":
            nomes = sorted(p.name for p in PLACAS.iterdir() if placa(p.name)) if PLACAS.exists() else []
            with trava:
                vivos = [n for n, p in rodando.items() if p.poll() is None]
            return self.responder({"placas": nomes, "rodando": vivos, "raiz": str(RAIZ)})
        if not self.servido(url):
            return self.responder({"erro": "não existe"}, 404)
        super().do_GET()

    def no_catalogo(self, caminho, corpo):
        """checar: preco e estoque agora, na loja; buscar: peca nova da loja entra na lista"""
        try:
            with trava:
                cat = catalogo.ler()
                if caminho == "/api/catalogo/checar":
                    pedidas = [c for c in corpo.get("codigos", []) if isinstance(c, str) and c in cat["pecas"]]
                    lcsc = [c for c in pedidas if cat["pecas"][c].get("loja", "LCSC") == "LCSC"][:60]
                    outras = [c for c in pedidas if c not in lcsc][:3]   # lojas brasileiras pedem 10 s entre paginas
                    mudaram = catalogo.checar(cat, lcsc + outras, avisar=lambda *_: None)
                    resposta = {"ok": True, "conferidas": len(lcsc) + len(outras), "mudaram": mudaram,
                                "ficaram": len(pedidas) - len(lcsc) - len(outras)}
                else:
                    bloco, texto = str(corpo.get("bloco", "")), str(corpo.get("texto", "")).strip()[:80]
                    if bloco not in cat["categorias"] or not texto:
                        return self.responder({"erro": "categoria ou busca inválida"}, 400)
                    achadas = [i for i in loja.buscar(texto, 30, validade=0) if catalogo.serve(cat, bloco, i)]
                    novas = catalogo.adicionar(cat, bloco, sorted(achadas, key=lambda i: -i["estoque"])[:12])
                    resposta = {"ok": True, "achadas": len(achadas), "novas": novas}
                catalogo.salvar(cat)
        except loja.SemLoja as e:
            return self.responder({"erro": str(e)}, 502)
        self.responder(resposta)

    def foto(self, codigo):
        """foto da peca na LCSC (fica no cache do loja.py)"""
        if not loja.CODIGO.match(codigo):
            return self.responder({"erro": "código"}, 400)
        try:
            url = loja.pagina(codigo)["foto"]
            jpg = loja.pedir(url, validade=None, binario=True) if url else None
        except loja.SemLoja:
            jpg = None
        if not jpg:
            return self.responder({"erro": "sem foto"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpg)))
        self.end_headers()
        self.wfile.write(jpg)

    def do_POST(self):
        ultimo[0] = time.monotonic()
        url = urlparse(self.path)
        if self.headers.get("Host") not in HOSTS:
            return self.responder({"erro": "host"}, 403)
        # o cabecalho proprio faz o navegador barrar pedido vindo de outro site
        if url.path not in ("/api/testar", "/api/escolher", "/api/responder", "/api/catalogo/checar", "/api/catalogo/buscar") \
                or self.headers.get("X-Bancada") != "1":
            return self.responder({"erro": "não existe"}, 404)
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(tamanho) or b"{}") if 0 <= tamanho <= 10_000 else None
        except ValueError:
            corpo = None
        if not isinstance(corpo, dict):
            return self.responder({"erro": "corpo inválido"}, 400)
        if url.path.startswith("/api/catalogo/"):
            return self.no_catalogo(url.path, corpo)
        nome = parse_qs(url.query).get("placa", [""])[0]
        pasta = placa(nome)
        if not pasta:
            return self.responder({"erro": f"a placa '{nome}' não existe"}, 404)
        with trava:   # uma rodada por placa de cada vez; a chave e a pasta de verdade, nao o texto da URL
            ocupada = pasta.name in rodando and rodando[pasta.name].poll() is None
            if url.path == "/api/testar":
                return self.responder({"ok": True, "ja_rodando": not rodar_testes(pasta)})
            if ocupada:   # nao mexe no placa.txt no meio de uma rodada
                return self.responder({"erro": "os testes estão rodando; tenta de novo em uns segundos"}, 409)
            try:
                if url.path == "/api/escolher":
                    ref, codigo = str(corpo.get("ref", "")), str(corpo.get("codigo", ""))
                    if not re.fullmatch(r"[A-Za-z_]\w*", ref) or not loja.CODIGO.match(codigo):
                        return self.responder({"erro": "ref ou código inválido"}, 400)
                    feito = blocos.escolher(pasta, ref, codigo)
                else:
                    feito = blocos.responder(pasta, str(corpo.get("pergunta", "")), str(corpo.get("resposta", "")))
            except ValueError as e:
                return self.responder({"erro": str(e)}, 400)
            except loja.SemLoja as e:
                return self.responder({"erro": str(e)}, 502)
            rodar_testes(pasta, (feito or {}).get("frase"))
        self.responder({"ok": True, **(feito or {})})


def abrir_janela(url):
    """janela de app (sem abas) no Chrome/Chromium; senao, o navegador padrao"""
    for nome in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        exe = shutil.which(nome)
        if exe:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1400,900"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return
    webbrowser.open(url)


def fechar_quando_ocioso(servidor):
    while time.monotonic() - ultimo[0] < OCIOSO:
        time.sleep(10)
    servidor.shutdown()


if __name__ == "__main__":
    janela = "--sem-janela" not in sys.argv
    url = f"http://127.0.0.1:{PORTA}/bancada/"
    servidor = None
    for tentativa in range(2):
        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), partial(Bancada, directory=str(RAIZ)))
            break
        except OSError:   # porta ocupada: e um app nosso? (o pedido tambem renova o relogio de ociosidade dele)
            try:   # e este mesmo repositorio? (outra copia do Sianvolt abriria as placas erradas)
                with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/api/placas", timeout=2) as r:
                    vivo = json.loads(r.read()).get("raiz") == str(RAIZ)
            except (OSError, ValueError):
                vivo = False
            if vivo:
                if janela:
                    abrir_janela(url)   # so abre outra janela no que ja esta rodando
                sys.exit()
            time.sleep(1)   # pode ter acabado de fechar; tenta a porta de novo
    if servidor is None:
        sys.exit(f"a porta {PORTA} está ocupada por outro programa")
    if janela:
        threading.Thread(target=fechar_quando_ocioso, args=(servidor,), daemon=True).start()
        abrir_janela(url)
    print(f"bancada em {url}" + ("" if janela else " (Ctrl+C fecha)"))
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
