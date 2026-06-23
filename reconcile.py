#!/usr/bin/env python3
"""Сверка оплат с банком и доотправка пропущенных уведомлений.

Зачем: письмо организаторам отправляется только в момент возврата браузера на
/payment/callback. Если человек закрыл вкладку после оплаты, или SMTP/воркер
подвис — оплата в банке есть (APPROVED), а письма нет. Этот скрипт чинит оба
случая и идемпотентен (повторный запуск не шлёт дубли).

Шаг 1: записи в статусе pending/pending_manual с operation_id — проверяем в
        Точке; если APPROVED, переводим в approved.
Шаг 2: записи approved с notified=0 — досылаем письмо и ставим notified=1.

Запуск:  /var/www/echoes2026/.venv/bin/python reconcile.py
Подходит для cron/systemd timer (раз в 10–15 минут).
"""
import sqlite3

import app  # переиспользуем конфиг, verify_payment, send_notification_email, audit


def _reconcile_statuses():
    with sqlite3.connect(app.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM registrations "
            "WHERE payment_status IN ('pending', 'pending_manual') "
            "AND operation_id IS NOT NULL AND operation_id <> ''"
        ).fetchall()

    for row in rows:
        try:
            op = app.verify_payment(row['operation_id'])
            if op.get('status') == 'APPROVED':
                with sqlite3.connect(app.DB_PATH) as conn:
                    conn.execute(
                        "UPDATE registrations SET payment_status = 'approved' WHERE id = ?",
                        (row['id'],),
                    )
                    conn.commit()
                app.audit(
                    f"[RECONCILE] ✅ Оплата подтверждена сверкой | id={row['id']} | "
                    f"{row['email']} | ref={(row['payment_link_id'] or '')[:8]}..."
                )
        except Exception as e:  # noqa: BLE001
            app.audit(f"[RECONCILE-ERR] verify id={row['id']}: {e}", 'error')


def _resend_missing_emails():
    with sqlite3.connect(app.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM registrations "
            "WHERE payment_status = 'approved' AND COALESCE(notified, 0) = 0"
        ).fetchall()

    for row in rows:
        reg = dict(row)
        name = reg.get('full_name') or reg.get('representative_name') or reg.get('company_name') or '—'
        try:
            app.send_notification_email(reg)
            app._mark_notified(row['id'])
            app.audit(f"[RECONCILE] ✉️ Доотправлено уведомление | id={row['id']} | {name} | {reg.get('email')}")
        except Exception as e:  # noqa: BLE001
            app.audit(f"[RECONCILE-ERR] mail id={row['id']} | {name}: {e}", 'error')


def main():
    app.init_db()          # гарантирует наличие колонки notified
    _reconcile_statuses()  # pending → approved по данным банка
    _resend_missing_emails()  # approved без письма → досылаем


if __name__ == '__main__':
    main()
