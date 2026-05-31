"""
Real merchant locations for synthetic expense data.
Each entry: name, street, city, state, country, postal, mcc, category, amount_range (min, max CAD).
"""

# MCC → typical spend range for amount nudging when values are unrealistic for the category.
CATEGORY_AMOUNT_RANGES = {
    "Fuel": (35, 165),
    "Meals": (8, 95),
    "Travel": (25, 450),
    "Hotel": (120, 420),
    "Parking": (8, 45),
    "Shipping": (12, 85),
    "Retail": (15, 280),
    "Office Supplies": (12, 180),
    "Software & Telecom": (15, 120),
    "Business Services": (25, 350),
    "Vehicle Maintenance": (45, 220),
    "Fees & Permits": (15, 120),
}

# Weighted mix for corporate card spend (Montreal HQ).
CATEGORY_WEIGHTS = [
    ("Fuel", 0.18),
    ("Meals", 0.22),
    ("Travel", 0.08),
    ("Hotel", 0.10),
    ("Parking", 0.07),
    ("Shipping", 0.06),
    ("Retail", 0.08),
    ("Office Supplies", 0.06),
    ("Software & Telecom", 0.07),
    ("Business Services", 0.05),
    ("Vehicle Maintenance", 0.03),
]

MONTREAL_MERCHANTS = [
    # Fuel
    {"name": "PETRO-CANADA", "street": "1000 Boul. René-Lévesque O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 4W8", "mcc": 5541, "category": "Fuel"},
    {"name": "SHELL CANADA", "street": "5000 Rue Sherbrooke O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H4A 1T5", "mcc": 5541, "category": "Fuel"},
    {"name": "ESSO STATION", "street": "3400 Boul. Saint-Laurent", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2X 2T3", "mcc": 5542, "category": "Fuel"},
    {"name": "COUCHE-TARD", "street": "1455 Rue Peel", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3A 1T5", "mcc": 5541, "category": "Fuel"},
    {"name": "ULTRAMAR", "street": "1200 Rue Guy", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3H 2L8", "mcc": 5541, "category": "Fuel"},
    {"name": "IRVING OIL", "street": "8800 Boul. Henri-Bourassa E", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H1E 2S4", "mcc": 5541, "category": "Fuel"},
    # Meals
    {"name": "ST-HUBERT BBQ", "street": "1155 Blvd. René-Lévesque O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 2M6", "mcc": 5812, "category": "Meals"},
    {"name": "TIM HORTONS", "street": "4000 Rue Sainte-Catherine O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3Z 1P5", "mcc": 5814, "category": "Meals"},
    {"name": "STARBUCKS COFFEE", "street": "1500 Rue McGill College", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3A 3J6", "mcc": 5814, "category": "Meals"},
    {"name": "SCHWARTZ'S DELI", "street": "3895 Blvd. Saint-Laurent", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2W 1X9", "mcc": 5812, "category": "Meals"},
    {"name": "MCDONALD'S", "street": "5205 Boul. des Galeries-d'Anjou", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H1M 1W1", "mcc": 5814, "category": "Meals"},
    {"name": "RESTAURANT TOQUE", "street": "900 Place Jean-Paul-Riopelle", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2Z 0B1", "mcc": 5812, "category": "Meals"},
    {"name": "JOE BEEF", "street": "2491 Notre-Dame St W", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3J 1N6", "mcc": 5812, "category": "Meals"},
    {"name": "FAIM DE LOUP", "street": "1304 Rue Beaubien E", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2S 1T5", "mcc": 5812, "category": "Meals"},
    {"name": "CAFE MYRIADE", "street": "1432 Rue Mackay", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3G 2H7", "mcc": 5814, "category": "Meals"},
    {"name": "OLIVE ET GOURMANDO", "street": "351 Rue Saint-Paul O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2Y 2A7", "mcc": 5812, "category": "Meals"},
    # Hotels / travel
    {"name": "FAIRMONT THE QUEEN ELIZABETH", "street": "900 Rue de la Gauchetière O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3A 0A1", "mcc": 7011, "category": "Hotel"},
    {"name": "HOTEL BONAVENTURE", "street": "900 Rue de la Gauchetière O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H5A 1E4", "mcc": 7011, "category": "Hotel"},
    {"name": "DELTA HOTELS MONTREAL", "street": "475 Blvd René-Lévesque O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2Z 1A7", "mcc": 7011, "category": "Hotel"},
    {"name": "HILTON MONTREAL", "street": "900 Blvd René-Lévesque O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 4A5", "mcc": 7011, "category": "Hotel"},
    {"name": "LE WESTIN MONTREAL", "street": "270 Rue Saint-Antoine O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2Y 0A3", "mcc": 7011, "category": "Hotel"},
    {"name": "VIA RAIL CANADA", "street": "895 Rue de la Gauchetière O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 4G1", "mcc": 4111, "category": "Travel"},
    {"name": "STM OPUS RECHARGE", "street": "800 Rue de la Gauchetière O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H5A 1K6", "mcc": 4784, "category": "Travel"},
    {"name": "UBER TRIP", "street": "151 Rue Sainte-Catherine O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2X 1Y8", "mcc": 4121, "category": "Travel"},
    # Parking
    {"name": "INDIGO PARK - PVM", "street": "1 Place Ville Marie", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 2C3", "mcc": 7523, "category": "Parking"},
    {"name": "OPARK PLACE DES ARTS", "street": "175 Rue Sainte-Catherine O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2X 1Y8", "mcc": 7523, "category": "Parking"},
    {"name": "AEROPORT MTL PARKING", "street": "975 Boul. Romeo-Vachon N", "city": "DORVAL", "state": "QC", "country": "CAN", "postal": "H4Y 1H1", "mcc": 7523, "category": "Parking"},
    # Shipping
    {"name": "FEDEX OFFICE", "street": "1250 Blvd René-Lévesque O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 4W8", "mcc": 4215, "category": "Shipping"},
    {"name": "UPS STORE", "street": "2000 McGill College Ave", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3A 3H3", "mcc": 4215, "category": "Shipping"},
    {"name": "CANADA POST", "street": "1250 Rue Sainte-Catherine O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 1E9", "mcc": 4215, "category": "Shipping"},
    # Retail / office
    {"name": "COSTCO WHOLESALE #534", "street": "5555 Rue Metropolitain E", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H1P 1X3", "mcc": 5300, "category": "Retail"},
    {"name": "BUREAU EN GROS", "street": "7700 Rue Sherbrooke E", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H1L 6A8", "mcc": 5045, "category": "Office Supplies"},
    {"name": "CANADIAN TIRE", "street": "935 Rue Beaubien E", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2S 1T5", "mcc": 5533, "category": "Retail"},
    {"name": "SAQ", "street": "405 Rue Sainte-Catherine O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 1A4", "mcc": 5921, "category": "Retail"},
    {"name": "METRO RICHELIEU", "street": "11011 Blvd. Lacordaire", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H1G 4M7", "mcc": 5411, "category": "Retail"},
    # Telecom / software
    {"name": "BELL CANADA", "street": "1600 Blvd René-Lévesque O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3H 1R9", "mcc": 4814, "category": "Software & Telecom"},
    {"name": "VIDEOTRON LTEE", "street": "612 Rue Sainte-Catherine O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 1B7", "mcc": 4816, "category": "Software & Telecom"},
    {"name": "ADOBE SYSTEMS", "street": "1250 Blvd René-Lévesque O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3B 4W8", "mcc": 5734, "category": "Software & Telecom"},
    {"name": "MICROSOFT CANADA", "street": "2000 McGill College Ave", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3A 3H3", "mcc": 5045, "category": "Software & Telecom"},
    # Vehicle / business services
    {"name": "JIFFY LUBE", "street": "5985 Rue Sherbrooke O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H4A 1X6", "mcc": 7538, "category": "Vehicle Maintenance"},
    {"name": "CANADIAN TIRE AUTO", "street": "935 Rue Beaubien E", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2S 1T5", "mcc": 7538, "category": "Vehicle Maintenance"},
    {"name": "HERTZ RENT-A-CAR", "street": "635 Rue Saint-Jacques", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3C 1E8", "mcc": 7512, "category": "Travel"},
    {"name": "ENTERPRISE RENT-A-CAR", "street": "635 Rue Saint-Jacques", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3C 1E8", "mcc": 7512, "category": "Travel"},
    {"name": "KPMG MONTREAL", "street": "600 Blvd de Maisonneuve O", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H3A 0A3", "mcc": 7399, "category": "Business Services"},
    {"name": "REGISTRAIRE DES ENTREPRISES", "street": "393 Rue Saint-Jacques", "city": "MONTREAL", "state": "QC", "country": "CAN", "postal": "H2Y 1N9", "mcc": 9399, "category": "Fees & Permits"},
]

SECONDARY_CITY_MERCHANTS = {
    "LAVAL": [
        {"name": "PETRO-CANADA", "street": "3000 Boul. du Souvenir", "city": "LAVAL", "state": "QC", "country": "CAN", "postal": "H7V 1X1", "mcc": 5541, "category": "Fuel"},
        {"name": "ST-HUBERT BBQ", "street": "3050 Boul. Le Carrefour", "city": "LAVAL", "state": "QC", "country": "CAN", "postal": "H7T 2K7", "mcc": 5812, "category": "Meals"},
        {"name": "TIM HORTONS", "street": "1600 Boul. des Laurentides", "city": "LAVAL", "state": "QC", "country": "CAN", "postal": "H7N 2M7", "mcc": 5814, "category": "Meals"},
        {"name": "COSTCO WHOLESALE", "street": "3000 Boul. le Carrefour", "city": "LAVAL", "state": "QC", "country": "CAN", "postal": "H7T 2K7", "mcc": 5300, "category": "Retail"},
        {"name": "COUCHE-TARD", "street": "3200 Boul. des Laurentides", "city": "LAVAL", "state": "QC", "country": "CAN", "postal": "H7P 1W9", "mcc": 5541, "category": "Fuel"},
    ],
    "TORONTO": [
        {"name": "PETRO-CANADA", "street": "100 King St W", "city": "TORONTO", "state": "ON", "country": "CAN", "postal": "M5X 1A9", "mcc": 5541, "category": "Fuel"},
        {"name": "TIM HORTONS", "street": "130 King St W", "city": "TORONTO", "state": "ON", "country": "CAN", "postal": "M5X 1E3", "mcc": 5814, "category": "Meals"},
        {"name": "DELTA HOTELS TORONTO", "street": "75 Lower Simcoe St", "city": "TORONTO", "state": "ON", "country": "CAN", "postal": "M5J 3A6", "mcc": 7011, "category": "Hotel"},
        {"name": "INDIGO PARK", "street": "100 Queen St W", "city": "TORONTO", "state": "ON", "country": "CAN", "postal": "M5H 2N2", "mcc": 7523, "category": "Parking"},
        {"name": "STAPLES", "street": "55 Dundas St W", "city": "TORONTO", "state": "ON", "country": "CAN", "postal": "M5G 2C3", "mcc": 5045, "category": "Office Supplies"},
        {"name": "FEDEX OFFICE", "street": "200 Bay St", "city": "TORONTO", "state": "ON", "country": "CAN", "postal": "M5J 2J4", "mcc": 4215, "category": "Shipping"},
    ],
    "OTTAWA": [
        {"name": "ESSO STATION", "street": "150 Metcalfe St", "city": "OTTAWA", "state": "ON", "country": "CAN", "postal": "K2P 1P1", "mcc": 5541, "category": "Fuel"},
        {"name": "STARBUCKS COFFEE", "street": "90 Sparks St", "city": "OTTAWA", "state": "ON", "country": "CAN", "postal": "K1P 5B4", "mcc": 5814, "category": "Meals"},
        {"name": "FAIRMONT CHATEAU LAURIER", "street": "1 Rideau St", "city": "OTTAWA", "state": "ON", "country": "CAN", "postal": "K1N 8S7", "mcc": 7011, "category": "Hotel"},
        {"name": "CANADA POST", "street": "59 Sparks St", "city": "OTTAWA", "state": "ON", "country": "CAN", "postal": "K1P 5A5", "mcc": 4215, "category": "Shipping"},
        {"name": "VIA RAIL CANADA", "street": "200 Tremblay Rd", "city": "OTTAWA", "state": "ON", "country": "CAN", "postal": "K1G 3V8", "mcc": 4111, "category": "Travel"},
    ],
    "VANCOUVER": [
        {"name": "SHELL CANADA", "street": "1055 Canada Pl", "city": "VANCOUVER", "state": "BC", "country": "CAN", "postal": "V6C 0C3", "mcc": 5541, "category": "Fuel"},
        {"name": "STARBUCKS COFFEE", "street": "750 Burrard St", "city": "VANCOUVER", "state": "BC", "country": "CAN", "postal": "V6Z 1X5", "mcc": 5814, "category": "Meals"},
        {"name": "FAIRMONT HOTEL VANCOUVER", "street": "900 West Georgia St", "city": "VANCOUVER", "state": "BC", "country": "CAN", "postal": "V6C 2W6", "mcc": 7011, "category": "Hotel"},
        {"name": "INDIGO PARK", "street": "1055 West Georgia St", "city": "VANCOUVER", "state": "BC", "country": "CAN", "postal": "V6E 3P3", "mcc": 7523, "category": "Parking"},
        {"name": "BELL CANADA", "street": "768 Seymour St", "city": "VANCOUVER", "state": "BC", "country": "CAN", "postal": "V6B 3K9", "mcc": 4814, "category": "Software & Telecom"},
    ],
    "QUEBEC CITY": [
        {"name": "PETRO-CANADA", "street": "5401 Boul. des Galeries", "city": "QUEBEC CITY", "state": "QC", "country": "CAN", "postal": "G2K 1N4", "mcc": 5541, "category": "Fuel"},
        {"name": "ST-HUBERT BBQ", "street": "1200 Boul. Laurier", "city": "QUEBEC CITY", "state": "QC", "country": "CAN", "postal": "G1V 2M1", "mcc": 5812, "category": "Meals"},
        {"name": "FAIRMONT LE CHATEAU FRONTENAC", "street": "1 Rue des Carrières", "city": "QUEBEC CITY", "state": "QC", "country": "CAN", "postal": "G1R 4P5", "mcc": 7011, "category": "Hotel"},
        {"name": "COUCHE-TARD", "street": "825 Rue Saint-Jean", "city": "QUEBEC CITY", "state": "QC", "country": "CAN", "postal": "G1R 1R9", "mcc": 5541, "category": "Fuel"},
        {"name": "CANADA POST", "street": "1191 Rue Saint-Jean", "city": "QUEBEC CITY", "state": "QC", "country": "CAN", "postal": "G1R 1S3", "mcc": 4215, "category": "Shipping"},
    ],
}

# Dorval is part of greater Montreal — treat as Montreal for spend share.
MONTREAL_AREA_CITIES = {"MONTREAL", "DORVAL"}

MERCHANTS_BY_CATEGORY = {}
for m in MONTREAL_MERCHANTS:
    MERCHANTS_BY_CATEGORY.setdefault(m["category"], []).append(m)

for city_merchants in SECONDARY_CITY_MERCHANTS.values():
    for m in city_merchants:
        MERCHANTS_BY_CATEGORY.setdefault(m["category"], []).append(m)
