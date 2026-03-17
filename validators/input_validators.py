"""
Валидаторы входных данных
Проверка ФИО, дат, сумм, URL и т.д.
"""

import re
from datetime import datetime, date
from typing import Optional, Tuple, List
from dataclasses import dataclass

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Результат валидации"""
    is_valid: bool
    value: any = None
    error_message: Optional[str] = None


class InputValidators:
    """Класс с валидаторами входных данных"""
    
    # Паттерны
    FIO_PATTERN = re.compile(r"^[а-яА-ЯёЁa-zA-Z\s\-]{3,100}$")
    DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    URL_PATTERN = re.compile(r"^https?://[^\s]+$")
    PHONE_PATTERN = re.compile(r"^[\+]?[0-9\s\-\(\)]{10,20}$")
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    
    @classmethod
    def validate_fio(cls, text: str) -> ValidationResult:
        """Валидация ФИО"""
        text = text.strip()
        
        if not text:
            return ValidationResult(False, error_message="ФИО не может быть пустым")
        
        if len(text) < 3:
            return ValidationResult(False, error_message="ФИО слишком короткое (минимум 3 символа)")
        
        if len(text) > 100:
            return ValidationResult(False, error_message="ФИО слишком длинное (максимум 100 символов)")
        
        if not cls.FIO_PATTERN.match(text):
            return ValidationResult(
                False,
                error_message="ФИО содержит недопустимые символы. Используйте только буквы, пробелы и дефисы"
            )
        
        return ValidationResult(True, value=text)
    
    @classmethod
    def validate_fio_list(cls, text: str) -> ValidationResult:
        """Валидация списка ФИО через запятую"""
        if not text.strip():
            return ValidationResult(False, error_message="Список ФИО не может быть пустым")
        
        fio_list = [fio.strip() for fio in text.split(",") if fio.strip()]
        
        if not fio_list:
            return ValidationResult(False, error_message="Не указано ни одного ФИО")
        
        if len(fio_list) > 20:
            return ValidationResult(False, error_message="Максимум 20 человек в одной заявке")
        
        validated_list = []
        errors = []
        
        for i, fio in enumerate(fio_list, 1):
            result = cls.validate_fio(fio)
            if result.is_valid:
                validated_list.append(result.value)
            else:
                errors.append(f"Гость #{i}: {result.error_message}")
        
        if errors:
            return ValidationResult(False, error_message="\n".join(errors))
        
        return ValidationResult(True, value=validated_list)
    
    @classmethod
    def validate_date(cls, text: str) -> ValidationResult:
        """Валидация даты в формате ДД.ММ.ГГГГ"""
        text = text.strip()
        
        if not cls.DATE_PATTERN.match(text):
            return ValidationResult(
                False,
                error_message="Неверный формат даты. Используйте ДД.ММ.ГГГГ (например, 15.08.2025)"
            )
        
        try:
            parsed_date = datetime.strptime(text, "%d.%m.%Y").date()
        except ValueError:
            return ValidationResult(False, error_message="Некорректная дата")
        
        return ValidationResult(True, value=parsed_date)
    
    @classmethod
    def validate_future_date(cls, text: str) -> ValidationResult:
        """Валидация даты в будущем"""
        result = cls.validate_date(text)
        if not result.is_valid:
            return result
        
        if result.value < date.today():
            return ValidationResult(
                False,
                error_message="Дата не может быть в прошлом. Укажите сегодняшнюю или будущую дату"
            )
        
        # Ограничение на год вперед
        max_date = date.today().replace(year=date.today().year + 1)
        if result.value > max_date:
            return ValidationResult(
                False,
                error_message="Дата слишком далеко в будущем (максимум 1 год)"
            )
        
        return result
    
    @classmethod
    def validate_url(cls, text: str) -> ValidationResult:
        """Валидация URL"""
        text = text.strip()
        
        if not text:
            return ValidationResult(False, error_message="URL не может быть пустым")
        
        if not cls.URL_PATTERN.match(text):
            return ValidationResult(
                False,
                error_message="Неверный формат URL. Начните с http:// или https://"
            )
        
        if len(text) > 2000:
            return ValidationResult(False, error_message="URL слишком длинный")
        
        return ValidationResult(True, value=text)
    
    @classmethod
    def validate_text(
        cls,
        text: str,
        min_length: int = 1,
        max_length: int = 1000,
        field_name: str = "Текст"
    ) -> ValidationResult:
        """Валидация текстового поля"""
        text = text.strip()
        
        if not text:
            return ValidationResult(False, error_message=f"{field_name} не может быть пустым")
        
        if len(text) < min_length:
            return ValidationResult(
                False,
                error_message=f"{field_name} слишком короткий (минимум {min_length} символов)"
            )
        
        if len(text) > max_length:
            return ValidationResult(
                False,
                error_message=f"{field_name} слишком длинный (максимум {max_length} символов)"
            )
        
        return ValidationResult(True, value=text)
    
    @classmethod
    def validate_quantity(cls, text: str) -> ValidationResult:
        """Валидация количества товара"""
        text = text.strip()
        
        if not text:
            return ValidationResult(False, error_message="Количество не указано")
        
        if len(text) > 100:
            return ValidationResult(False, error_message="Слишком длинное описание количества")
        
        return ValidationResult(True, value=text)
    
    @classmethod
    def validate_amount(cls, text: str) -> ValidationResult:
        """Валидация суммы"""
        text = text.strip().replace(" ", "").replace(",", ".")
        
        try:
            amount = float(text)
        except ValueError:
            return ValidationResult(False, error_message="Неверный формат суммы")
        
        if amount < 0:
            return ValidationResult(False, error_message="Сумма не может быть отрицательной")
        
        if amount > 100_000_000:
            return ValidationResult(False, error_message="Сумма слишком большая")
        
        return ValidationResult(True, value=amount)
    
    @classmethod
    def validate_phone(cls, text: str) -> ValidationResult:
        """Валидация номера телефона"""
        text = text.strip()
        
        if not cls.PHONE_PATTERN.match(text):
            return ValidationResult(
                False,
                error_message="Неверный формат телефона. Пример: +7 999 123-45-67"
            )
        
        return ValidationResult(True, value=text)
    
    @classmethod
    def validate_email(cls, text: str) -> ValidationResult:
        """Валидация email"""
        text = text.strip().lower()
        
        if not cls.EMAIL_PATTERN.match(text):
            return ValidationResult(
                False,
                error_message="Неверный формат email. Пример: user@example.com"
            )
        
        return ValidationResult(True, value=text)
    
    @classmethod
    def validate_priority(cls, text: str) -> ValidationResult:
        """Валидация приоритета"""
        priorities = {
            "🔴 срочно": "urgent",
            "срочно": "urgent",
            "urgent": "urgent",
            "🟡 обычно": "normal",
            "обычно": "normal",
            "normal": "normal",
            "🟢 планово": "low",
            "планово": "low",
            "low": "low",
        }
        
        text = text.strip().lower()
        
        if text not in priorities:
            return ValidationResult(
                False,
                error_message="Неверный приоритет. Выберите: Срочно, Обычно или Планово"
            )
        
        return ValidationResult(True, value=priorities[text])
    
    @classmethod
    def validate_ticket_type(cls, text: str) -> ValidationResult:
        """Валидация типа заявки"""
        types = {
            "🪪 заказать пропуск": "pass",
            "заказать пропуск": "pass",
            "пропуск": "pass",
            "pass": "pass",
            "🛒 заявка на закупку": "purchase",
            "заявка на закупку": "purchase",
            "закупка": "purchase",
            "purchase": "purchase",
            "🔧 что-то сломалось": "repair",
            "что-то сломалось": "repair",
            "ремонт": "repair",
            "repair": "repair",
            "❓ другое": "other",
            "другое": "other",
            "other": "other",
        }
        
        text = text.strip().lower()
        
        if text not in types:
            return ValidationResult(
                False,
                error_message="Неверный тип заявки"
            )
        
        return ValidationResult(True, value=types[text])
    
    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Очистка текста от потенциально опасных символов"""
        # Удаляем управляющие символы кроме переводов строки
        text = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # Ограничиваем длину
        return text[:5000]
