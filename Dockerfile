# Используем официальный образ Python
FROM python:3.10-slim

# Устанавливаем системные зависимости
# ffmpeg - для конвертации видео
# libgl1 и libglib2.0-0 - критически важны для работы opencv-python
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Запуск
CMD ["python", "main.py"]
