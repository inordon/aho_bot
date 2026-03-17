"""
Модуль email уведомлений
SMTP отправка, шаблоны писем
"""

import os
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)


class EmailService:
    """Сервис отправки email уведомлений"""
    
    def __init__(self):
        self.enabled = os.getenv("SMTP_ENABLED", "false").lower() == "true"
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM", self.user)
        self.use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    
    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False
    ) -> bool:
        """Отправить email"""
        if not self.enabled:
            logger.debug(f"Email отправка отключена. Пропуск: {subject}")
            return True
        
        if not self.user or not self.password:
            logger.warning("SMTP не настроен: отсутствуют учетные данные")
            return False
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to
            
            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))
            
            await asyncio.to_thread(self._send_sync, to, msg)
            
            logger.info(f"Email отправлен: {to} - {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отправки email: {e}")
            return False
    
    def _send_sync(self, to: str, msg: MIMEMultipart) -> None:
        """Синхронная отправка (выполняется в потоке)"""
        with smtplib.SMTP(self.host, self.port) as server:
            if self.use_tls:
                server.starttls()
            server.login(self.user, self.password)
            server.sendmail(self.from_email, to, msg.as_string())
    
    async def send_to_many(
        self,
        recipients: List[str],
        subject: str,
        body: str,
        html: bool = False
    ) -> Dict[str, bool]:
        """Отправить email нескольким получателям"""
        results = {}
        for recipient in recipients:
            results[recipient] = await self.send(recipient, subject, body, html)
        return results


class EmailTemplates:
    """Шаблоны email сообщений"""
    
    @staticmethod
    def new_ticket(
        ticket_id: int,
        ticket_type: str,
        priority: str,
        user_name: str,
        description: str
    ) -> tuple:
        """Шаблон для новой заявки"""
        subject = f"[АХО] Новая заявка #{ticket_id} - {ticket_type}"
        
        body = f"""
        <html>
        <body>
            <h2>Новая заявка #{ticket_id}</h2>
            <table>
                <tr><td><b>Тип:</b></td><td>{ticket_type}</td></tr>
                <tr><td><b>Приоритет:</b></td><td>{priority}</td></tr>
                <tr><td><b>От:</b></td><td>{user_name}</td></tr>
                <tr><td><b>Описание:</b></td><td>{description}</td></tr>
                <tr><td><b>Время:</b></td><td>{datetime.now().strftime('%d.%m.%Y %H:%M')}</td></tr>
            </table>
            <p>Обработайте заявку в Telegram боте.</p>
        </body>
        </html>
        """
        
        return subject, body
    
    @staticmethod
    def ticket_status_changed(
        ticket_id: int,
        old_status: str,
        new_status: str,
        changed_by: str,
        comment: Optional[str] = None
    ) -> tuple:
        """Шаблон для изменения статуса"""
        subject = f"[АХО] Заявка #{ticket_id} - статус изменен"
        
        comment_html = f"<p><b>Комментарий:</b> {comment}</p>" if comment else ""
        
        body = f"""
        <html>
        <body>
            <h2>Заявка #{ticket_id} - изменение статуса</h2>
            <p>Статус изменен: <b>{old_status}</b> → <b>{new_status}</b></p>
            <p>Изменил: {changed_by}</p>
            {comment_html}
            <p>Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        </body>
        </html>
        """
        
        return subject, body
    
    @staticmethod
    def ticket_completed(
        ticket_id: int,
        ticket_type: str,
        completed_by: str,
        comment: Optional[str] = None
    ) -> tuple:
        """Шаблон для завершенной заявки"""
        subject = f"[АХО] Заявка #{ticket_id} выполнена"
        
        comment_html = f"<p><b>Комментарий:</b> {comment}</p>" if comment else ""
        
        body = f"""
        <html>
        <body>
            <h2>✅ Заявка #{ticket_id} выполнена</h2>
            <p><b>Тип:</b> {ticket_type}</p>
            <p><b>Выполнил:</b> {completed_by}</p>
            {comment_html}
            <p><b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        </body>
        </html>
        """
        
        return subject, body
    
    @staticmethod
    def daily_summary(
        date: str,
        total_created: int,
        total_completed: int,
        pending_count: int,
        stats_by_type: Dict[str, int]
    ) -> tuple:
        """Шаблон ежедневной сводки"""
        subject = f"[АХО] Ежедневная сводка за {date}"
        
        type_rows = "".join([
            f"<tr><td>{t}</td><td>{c}</td></tr>"
            for t, c in stats_by_type.items()
        ])
        
        body = f"""
        <html>
        <body>
            <h2>Ежедневная сводка АХО за {date}</h2>
            <h3>Общая статистика</h3>
            <ul>
                <li>Создано заявок: {total_created}</li>
                <li>Выполнено заявок: {total_completed}</li>
                <li>В ожидании: {pending_count}</li>
            </ul>
            <h3>По типам</h3>
            <table border="1">
                <tr><th>Тип</th><th>Количество</th></tr>
                {type_rows}
            </table>
        </body>
        </html>
        """
        
        return subject, body


_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Получить экземпляр сервиса email"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
