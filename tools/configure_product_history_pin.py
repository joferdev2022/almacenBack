"""Configura el hash del PIN en .env sin mostrar ni guardar el PIN en claro."""
import getpass
import re
from pathlib import Path

import bcrypt
from dotenv import dotenv_values, set_key


def main():
    env_path = Path(__file__).resolve().parents[1] / '.env'
    if dotenv_values(env_path).get('PRODUCT_HISTORY_PIN_HASH'):
        print('El hash del PIN del historial ya está configurado. No se modificó.')
        return
    pin = getpass.getpass('PIN de cuatro dígitos: ')
    if pin != getpass.getpass('Repite el PIN: '):
        raise SystemExit('Los PIN no coinciden.')
    if not re.fullmatch(r'[0-9]{4}', pin):
        raise SystemExit('El PIN debe contener exactamente cuatro dígitos.')
    encoded = bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()
    set_key(str(env_path), 'PRODUCT_HISTORY_PIN_HASH', encoded)
    print('Hash del PIN configurado. Reinicia el backend para cargarlo.')


if __name__ == '__main__':
    main()
