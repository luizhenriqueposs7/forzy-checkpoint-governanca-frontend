"""Fixture de aquisicao simulada, congelada ao iniciar o processo.

Consultar nao atualiza o horario de aquisicao. Para novos dados simulados,
reinicie a API; para Forzy real, use SENSOR_PROVIDER conforme README.
"""
from datetime import datetime, timezone, timedelta
from math import sin
import os

SENSORS = {'TEMP-001': ('°C', 25, 28), 'VIB-001': ('mm/s', 2, 2.3)}
ACQUIRED_AT = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=int(os.getenv('SENSOR_SIMULATION_AGE_SECONDS', '5')))
READINGS = {}
for tag, (unit, base, threshold) in SENSORS.items():
    READINGS[tag] = [
        {'tag': tag, 'timestamp': (ACQUIRED_AT-timedelta(seconds=(599-i)*60)).isoformat(),
         'value': round(base + sin(i/5)*base*.2, 2), 'unit': unit,
         'severity': 'alerta' if base + sin(i/5)*base*.2 >= threshold else 'normal',
         'source': 'simulacao'}
        for i in range(600)
    ]

def history(tag, limit=30):
    return [dict(row) for row in READINGS[tag][-limit:]]

def current(tag):
    return dict(READINGS[tag][-1])
