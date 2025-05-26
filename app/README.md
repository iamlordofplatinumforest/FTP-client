# FTP Клиент

Графический FTP клиент, написанный на Python с использованием tkinter.

## Возможности

- Подключение к FTP серверам
- Просмотр и навигация по файлам
- Загрузка и скачивание файлов
- История подключений
- Управление закладками
- Поиск файлов
- Настройка параметров приложения

## Требования

- Python 3.8 или выше
- Установленные зависимости из requirements.txt

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/ftp-client.git
cd ftp-client
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

## Запуск

```bash
python src/main.py
```

## Структура проекта

```
src/
├── core/           # Основная логика
│   ├── ftp_client.py
│   └── settings.py
├── gui/            # Графический интерфейс
│   ├── dialogs.py
│   ├── styles.py
│   └── widgets.py
├── utils/          # Вспомогательные функции
│   ├── crypto.py
│   └── helpers.py
└── main.py         # Точка входа
```

## Лицензия

MIT License 