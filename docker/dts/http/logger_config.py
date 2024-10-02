import logging

# Vytvořte logger
logger = logging.getLogger('app_logger')
logger.setLevel(logging.DEBUG)

# Vytvořte console handler a nastavte úroveň na DEBUG
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# Vytvořte formátovací objekt a přidejte jej do handleru
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

# Přidejte handler do loggeru
logger.addHandler(ch)

# Zajišťuje, že logger bude konfigurován pouze jednou
logging.basicConfig(level=logging.DEBUG)

# Pokud máte více handlerů, nezapomeňte případně na odstranění duplicit
if not logger.handlers:
    logger.addHandler(ch)
