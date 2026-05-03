import os

# Токен берется из переменных окружения (для Docker) или из строки ниже (для локального запуска)
TOKEN = os.getenv("TOKEN", "YOUR_TOKEN")
# URL для подключения к API MAX
API_URL = os.getenv("API_URL", "https://max.pager.dev")
