"""Hackathon brief data. These constants are the only simulation inputs."""

HORIZON = 8
BUDGET = 100
DECISIONS_REQUIRED = 5
MAX_PER_DIRECTION = 2

INDICATOR_NAMES = {
    "T1": "Разгрузка дорог",
    "T2": "Доступность общественного транспорта",
    "E1": "Озеленение",
    "E2": "Качество воздуха",
    "S1": "Школы и детсады",
    "S2": "Поликлиники и первичная медпомощь",
    "B1": "Безопасность улиц",
    "B2": "Безопасность дорожного движения",
    "C1": "Надёжность ЖКХ",
    "C2": "Скорость решения обращений жителей",
}

WEIGHTS = {
    "T1": 0.10, "T2": 0.10, "E1": 0.09, "E2": 0.11,
    "S1": 0.11, "S2": 0.11, "B1": 0.09, "B2": 0.09,
    "C1": 0.10, "C2": 0.10,
}

DISTRICTS = [
    {"id": "esil", "name": "Есиль", "pop_share": 0.27,
     "profile": "Богатый район, пробки на мостах, переполненные школы.",
     "indicators": {"T1": 45, "T2": 62, "E1": 68, "E2": 72, "S1": 48, "S2": 55, "B1": 78, "B2": 60, "C1": 75, "C2": 70}},
    {"id": "almaty", "name": "Алматы", "pop_share": 0.24,
     "profile": "Старый ЖКХ, пробки.",
     "indicators": {"T1": 40, "T2": 75, "E1": 50, "E2": 55, "S1": 60, "S2": 65, "B1": 62, "B2": 52, "C1": 50, "C2": 60}},
    {"id": "saryarka", "name": "Сарыарка", "pop_share": 0.20,
     "profile": "Смог от частного сектора, слабое озеленение.",
     "indicators": {"T1": 50, "T2": 70, "E1": 42, "E2": 40, "S1": 62, "S2": 68, "B1": 58, "B2": 55, "C1": 45, "C2": 55}},
    {"id": "baikonur", "name": "Байконур", "pop_share": 0.13,
     "profile": "Середняк без ярких перекосов.",
     "indicators": {"T1": 52, "T2": 68, "E1": 55, "E2": 50, "S1": 58, "S2": 60, "B1": 52, "B2": 58, "C1": 55, "C2": 58}},
    {"id": "nura", "name": "Нура", "pop_share": 0.16,
     "profile": "Аутсайдер по соцсфере и транспорту.",
     "indicators": {"T1": 55, "T2": 40, "E1": 45, "E2": 65, "S1": 38, "S2": 35, "B1": 55, "B2": 50, "C1": 60, "C2": 50}},
]

MEASURES = [
    {"id": "M1", "direction": "Транспорт", "name": "Выделенные полосы для автобусов", "type": "district", "cost": 18, "lag": 2, "effects": {"T1": 6, "T2": 9}},
    {"id": "M2", "direction": "Транспорт", "name": "Умные светофоры (адаптивное управление)", "type": "city", "cost": 22, "lag": 2, "effects": {"T1": 4, "B2": 3}},
    {"id": "M3", "direction": "Транспорт", "name": "Линия ЛРТ / расширение", "type": "district", "cost": 30, "lag": 4, "effects": {"T1": 16, "T2": 20, "E2": 4}},
    {"id": "M4", "direction": "Экология", "name": "Парк / сквер", "type": "district", "cost": 15, "lag": 2, "effects": {"E1": 12, "E2": 3, "B1": 2}},
    {"id": "M5", "direction": "Экология", "name": "Перевод частного сектора на чистое топливо", "type": "district", "cost": 25, "lag": 3, "effects": {"E2": 14, "C1": 4}},
    {"id": "M6", "direction": "Экология", "name": "Городская программа озеленения и ветрозащитных полос", "type": "city", "cost": 20, "lag": 4, "effects": {"E1": 5, "E2": 3}},
    {"id": "M7", "direction": "Соцсфера", "name": "Школа + детсад (модульное строительство)", "type": "district", "cost": 24, "lag": 3, "effects": {"S1": 16}},
    {"id": "M8", "direction": "Соцсфера", "name": "Центр семейного здоровья / поликлиника", "type": "district", "cost": 20, "lag": 3, "effects": {"S2": 14}},
    {"id": "M9", "direction": "Соцсфера", "name": "Дворовые спорт-хабы", "type": "district", "cost": 10, "lag": 1, "effects": {"S1": 3, "S2": 3, "B1": 3}},
    {"id": "M10", "direction": "Безопасность", "name": "Освещение и камеры (расширение Safe City)", "type": "district", "cost": 12, "lag": 1, "effects": {"B1": 12, "B2": 2}},
    {"id": "M11", "direction": "Безопасность", "name": "Безопасные переходы и школьные зоны", "type": "district", "cost": 10, "lag": 1, "effects": {"B2": 12, "T1": -2}},
    {"id": "M12", "direction": "Сервисы", "name": "Единая цифровая платформа обращений", "type": "city", "cost": 14, "lag": 1, "effects": {"C2": 5}},
    {"id": "M13", "direction": "Сервисы", "name": "Модернизация тепло- и водосетей", "type": "district", "cost": 28, "lag": 4, "effects": {"C1": 18, "E2": 2}},
    {"id": "M14", "direction": "Сервисы", "name": "Аварийные бригады ЖКХ + раннее оповещение", "type": "city", "cost": 16, "lag": 1, "effects": {"C1": 5, "C2": 2}},
]

SYNERGIES = [
    {"pair": ["M1", "M2"], "bonus": {"T1": 2}, "district_source": "M1"},
    {"pair": ["M10", "M12"], "bonus": {"B1": 2}, "district_source": "M10"},
    {"pair": ["M5", "M6"], "bonus": {"E2": 2}, "district_source": "M5"},
]

INCOMPATIBILITIES = [["M1", "M3"], ["M4", "M7"], ["M5", "M13"]]

DISTRICT_BY_ID = {item["id"]: item for item in DISTRICTS}
MEASURE_BY_ID = {item["id"]: item for item in MEASURES}

