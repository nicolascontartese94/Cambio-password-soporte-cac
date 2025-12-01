import paramiko
import time
import random
import string
import re

# --- Parámetros globales ---
usuario = "WIFIGUEST"
contrasena = "Wireless2025"  # cargar desde variable de entorno

# --- Diccionario de controladoras ---
controladoras = {
    "oll-wlc01": "10.92.28.149",
    "oll-wlc02": "10.92.28.151",
    "cba-wlc01": "10.105.94.59",
    "cba-wlc02": "10.105.94.61",
}

PALABRAS = [
    "casa", "gato", "perro", "dado", "sol", "luna",
    "auto", "mate", "pan", "mesa", "rio", "nube",
    "cielo", "fuego", "agua", "tierra", "bici", "pelo",
    "flor", "cable", "dulce", "silla", "pasto", "cafe",
    "vino", "plato", "zorro", "tigre", "vaca", "huevo",
    "pera", "manos", "dedo", "sapo", "raton", "puma",
    "taza", "cuadro", "techo", "piedra", "circo", "campo",
    "barco", "tren", "robot", "fruta", "salto", "queso",
    "piano", "salsa", "carta", "torta", "cinta", "ritmo",
    "cesto", "boton", "perla", "nieve", "llave", "punto"
]

SIMBOLOS = "@#$*+="


def generar_password():
    # Filtramos solo palabras que permitan llegar a 8 caracteres
    # palabra + 1 símbolo + al menos 1 número → len(palabra) <= 6
    palabras_validas = [p for p in PALABRAS if len(p) <= 6]
    if not palabras_validas:
        raise ValueError(
            "No hay palabras válidas para una contraseña de 8 caracteres.")

    palabra = random.choice(palabras_validas)

    # Mezclamos mayúsculas/minúsculas en TODA la palabra
    base = ''.join(random.choice([c.upper(), c.lower()]) for c in palabra)

    simbolo = random.choice(SIMBOLOS)

    # Números necesarios para completar 8 caracteres
    cant_numeros = 8 - len(base) - 1  # 1 por el símbolo
    if cant_numeros < 1:
        raise ValueError("La palabra es demasiado larga para este formato.")

    numeros = ''.join(random.choice(string.digits)
                      for _ in range(cant_numeros))

    # Formato: PALABRA + símbolo + números
    return f"{base}{simbolo}{numeros}"


def send_cmd(channel, cmd, wait=1) -> str:
    """Envía comando a través del canal SSH y retorna salida."""
    channel.send(cmd + '\n')
    time.sleep(wait)
    output = channel.recv(9999).decode(
        'utf-8', errors='ignore') if channel.recv_ready() else ''
    print(output)
    return output


def obtener_estado_vrrp(ip: str, username: str, password: str) -> str:
    """Retorna el estado VRRP: Master / Backup / Unknown / Error."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password,
                       look_for_keys=False, timeout=5)

        channel = client.invoke_shell()
        time.sleep(1)
        channel.recv(9999)
        salida = send_cmd(channel, "display vrrp admin")
        client.close()

        match = re.search(
            r"Interface:\s+\S+,\s*admin-vrrp vrid: \d+,\s*state:\s*(\w+)", salida, re.IGNORECASE)
        return match.group(1).capitalize() if match else "Unknown"

    except Exception as e:
        print(f"❌ Error obteniendo VRRP de {ip}: {e}")
        return "Error"


def detectar_primaria(par_nombre: str, ip1: str, ip2: str, username: str, password: str) -> str | None:
    """Determina cuál controladora del par es la primaria."""
    print(f"\n🔍 Verificando estado de {par_nombre}...")
    estado1 = obtener_estado_vrrp(ip1, username, password)
    if estado1 == "Master":
        print(f"✅ {par_nombre}-01 ({ip1}) es PRIMARIA")
        return ip1
    elif estado1 == "Backup":
        estado2 = obtener_estado_vrrp(ip2, username, password)
        if estado2 == "Master":
            print(f"✅ {par_nombre}-02 ({ip2}) es PRIMARIA")
            return ip2
        else:
            print(f"⚠️ Ambas en BACKUP o {par_nombre}-02 no responde.")
    else:
        estado2 = obtener_estado_vrrp(ip2, username, password)
        if estado2 == "Master":
            print(f"✅ {par_nombre}-02 ({ip2}) es PRIMARIA")
            return ip2
        else:
            print(
                f"❌ Ninguna controladora de {par_nombre} respondió correctamente.")
    return None


def configurar_wlc(host: str, username: str, password: str, pwd_wifi: str):
    """Se conecta al WLC y aplica configuración WiFi."""
    try:
        print(f"\n🔧 Conectando a {host}...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=username, password=password,
                       look_for_keys=False, timeout=5)

        channel = client.invoke_shell()
        time.sleep(1)
        channel.recv(9999)

        # Comandos a aplicar (descomentar en producción)
        send_cmd(channel, 'system-view')
        send_cmd(channel, 'wlan')
        send_cmd(channel, 'security-profile name asesores_cac')
        send_cmd(
            channel, f"security wpa2-wpa3 psk-sae pass-phrase {pwd_wifi} aes")
        send_cmd(channel, 'y')
        send_cmd(channel, 'quit')
        send_cmd(channel, 'quit')

        print(f"✅ Configuración aplicada en {host}.")

    except Exception as e:
        print(f"❌ Error al configurar {host}: {e}")
    finally:
        try:
            channel.close()
            client.close()
        except:
            pass
        print("🔌 Sesión cerrada.\n")


# --- Ejecución principal ---
if __name__ == "__main__":
    password_wifi = generar_password()
    primaria_oll = detectar_primaria(
        "oll-wlc", controladoras["oll-wlc01"], controladoras["oll-wlc02"], usuario, contrasena)
    primaria_cba = detectar_primaria(
        "cba-wlc", controladoras["cba-wlc01"], controladoras["cba-wlc02"], usuario, contrasena)

    if primaria_oll:
        configurar_wlc(primaria_oll, usuario, contrasena, password_wifi)
    else:
        print("⚠️ No se pudo configurar OLL.")

    if primaria_cba:
        configurar_wlc(primaria_cba, usuario, contrasena, password_wifi)
    else:
        print("⚠️ No se pudo configurar CBA.")

    print(f"🔑 Contraseña WiFi generada: {password_wifi}")
