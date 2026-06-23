import os
import re
import uuid
import json
import logging
import sqlite3
import smtplib
import threading
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, redirect

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# Email config
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
NOTIFY_EMAILS = [
    'misha.andreev.novo@gmail.com',
    'ehos.ru@mail.ru',
]

# Tochka Bank config
TOCHKA_CUSTOMER_CODE = os.environ.get('TOCHKA_CUSTOMER_CODE', '')
TOCHKA_SANDBOX = os.environ.get('TOCHKA_SANDBOX', 'true').lower() == 'true'

DB_PATH = os.path.join(os.path.dirname(__file__), 'registrations.db')

PARTICIPATION_AMOUNTS = {
    'in_person': 15000,
    'student': 5000,
    'accompanying': 10000,
    'remote': 1000,
}

PARTICIPATION_LABELS = {
    'in_person': 'Очное участие — 15 000 руб',
    'student': 'Студенты, аспиранты — 5 000 руб',
    'accompanying': 'Сопровождающее лицо — 10 000 руб',
    'remote': 'Заочное участие — 1 000 руб',
}

REPORT_LABELS = {
    'oral': 'Устный доклад',
    'poster': 'Стендовый доклад',
    'none': 'Без доклада',
}

# Таймаут на все SMTP-операции (сек). Без него зависший почтовый сервер
# блокировал воркер gunicorn до WORKER TIMEOUT и письмо терялось.
SMTP_TIMEOUT = int(os.environ.get('SMTP_TIMEOUT', '20'))

# ── Audit log ────────────────────────────────────────────────────────────────
# Важные события (регистрации, оплаты, успехи/неудачи, письма) пишутся в
# ОТДЕЛЬНЫЙ файл без ротации — он хранится вечно для последующих сверок.
# Это НЕ access-лог gunicorn (там только запросы страниц, и он ротируется).
AUDIT_LOG_PATH = os.environ.get(
    'AUDIT_LOG_PATH',
    os.path.join(os.path.dirname(__file__), 'logs', 'audit.log'),
)

audit_logger = logging.getLogger('ehos.audit')
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False
if not any(isinstance(h, logging.FileHandler) for h in audit_logger.handlers):
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
        _audit_fh = logging.FileHandler(AUDIT_LOG_PATH, encoding='utf-8')  # append, без ротации
        _audit_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        audit_logger.addHandler(_audit_fh)
    except Exception as _e:  # noqa: BLE001 — логирование не должно ронять приложение
        logging.getLogger(__name__).error(f'Audit log init failed: {_e}')


def audit(msg, level='info'):
    """Пишет важное событие в вечный audit.log И в app.logger
    (чтобы оно также ушло в gunicorn error log и Telegram-форвардер)."""
    getattr(audit_logger, level, audit_logger.info)(msg)
    getattr(app.logger, level, app.logger.info)(msg)


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                report_type TEXT NOT NULL,
                participation_type TEXT NOT NULL,
                hotel INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                full_name TEXT,
                organization TEXT,
                company_name TEXT,
                inn TEXT,
                representative_name TEXT,
                representative_position TEXT,
                payment_link_id TEXT,
                operation_id TEXT,
                payment_status TEXT DEFAULT 'pending'
            )
        ''')
        conn.commit()
        for col, definition in [
            ('phone', 'TEXT'),
            ('payment_link_id', 'TEXT'),
            ('operation_id', 'TEXT'),
            ('payment_status', "TEXT DEFAULT 'pending'"),
            ('notified', 'INTEGER DEFAULT 0'),
        ]:
            try:
                conn.execute(f'ALTER TABLE registrations ADD COLUMN {col} {definition}')
                conn.commit()
            except sqlite3.OperationalError:
                pass


def _tochka_url(path):
    base = 'https://enter.tochka.com/sandbox/v2' if TOCHKA_SANDBOX else 'https://enter.tochka.com/uapi'
    return f'{base}{path}'


def _tochka_token():
    return 'sandbox.jwt.token' if TOCHKA_SANDBOX else os.environ.get('TOCHKA_JWT_TOKEN', '')


def create_payment_link(data, payment_link_id):
    amount = PARTICIPATION_AMOUNTS[data['participation_type']]
    client_name = data.get('full_name') or data.get('representative_name', '')

    payload = {
        'customerCode': TOCHKA_CUSTOMER_CODE,
        'amount': amount,
        'purpose': 'Регистрационный взнос ЭХОС-2026',
        'paymentMode': ['card', 'tinkoff', 'sbp'],
        'paymentLinkId': payment_link_id,
    }

    # Редиректы требуют HTTPS — добавляем только если есть настроенный BASE_URL
    configured_base = os.environ.get('BASE_URL', '').rstrip('/')
    if configured_base.startswith('https://'):
        payload['redirectUrl'] = f'{configured_base}/payment/callback?ref={payment_link_id}&result=success'
        payload['failRedirectUrl'] = f'{configured_base}/payment/callback?ref={payment_link_id}&result=failed'

    # ── WITHOUT RECEIPT (временная заглушка — раскомментировать если ОФД недоступен) ──
    # endpoint = '/acquiring/v1.0/payments'
    # ────────────────────────────────────────────────────────────────────────────────

    # ── WITH RECEIPT ─────────────────────────────────────────────────────────────────
    endpoint = '/acquiring/v1.0/payments_with_receipt'   # нижнее подчёркивание!
    payload['taxSystemCode'] = 'usn_income'              # УСН доходы 6%
    payload['Client'] = {                                # capital C — по документации
        'name': client_name,
        'phone': data.get('phone', ''),
        'email': data.get('email', ''),
    }
    payload['Items'] = [{                                # capital I — по документации
        'name': 'Участие в конференции ЭХОС-2026',
        'amount': amount,
        'quantity': 1,
        'vatType': 'vat5',                               # НДС 5%
        'paymentMethod': 'full_payment',
        'paymentObject': 'service',
    }]
    # ─────────────────────────────────────────────────────────────────────────────────

    req = urllib.request.Request(
        _tochka_url(endpoint),
        data=json.dumps({'Data': payload}).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {_tochka_token()}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        app.logger.error(f'Tochka HTTP {e.code}: {body}')
        raise


def verify_payment(operation_id):
    """Возвращает dict с полями операции из Data.Operation[0].
    Повторяет запрос до 4 раз с паузой 2 с — банк иногда обновляет статус
    чуть позже редиректа.
    """
    import time
    last_exc = None
    for attempt in range(4):
        if attempt:
            time.sleep(2)
        try:
            req = urllib.request.Request(
                _tochka_url(f'/acquiring/v1.0/payments/{operation_id}'),
                headers={'Authorization': f'Bearer {_tochka_token()}'},
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode('utf-8'))
            # Ответ: {"Data": {"Operation": [{"status": "APPROVED", ...}]}}
            operations = body.get('Data', {}).get('Operation', [])
            if not operations:
                raise ValueError(f'Empty Operation list in response: {body}')
            op = operations[0]
            status = op.get('status', '')
            if status == 'APPROVED' or attempt == 3:
                return op          # возвращаем весь объект операции
            # Статус ещё не APPROVED — повторим через 2 с
            app.logger.info(f'verify_payment attempt {attempt+1}: status={status!r}, retrying…')
        except Exception as e:
            last_exc = e
    if last_exc:
        raise last_exc
    return {}


def _mark_notified(reg_id):
    """Помечает регистрацию как «уведомление отправлено», чтобы доотправка
    (reconcile.py) не слала письмо повторно."""
    if reg_id is None:
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('UPDATE registrations SET notified = 1 WHERE id = ?', (reg_id,))
            conn.commit()
    except Exception as e:
        app.logger.error(f'mark_notified error for id={reg_id}: {e}')


def build_notification_message(reg):
    """Собирает письмо-уведомление организаторам об оплаченной регистрации."""
    entity_type = reg.get('entity_type')

    if entity_type == 'individual':
        details = (
            f"Тип участника: Физическое лицо\n"
            f"ФИО: {reg.get('full_name', '')}\n"
            f"Организация: {reg.get('organization', '')}\n"
            f"Телефон: {reg.get('phone', '')}\n"
            f"Email: {reg.get('email', '')}\n"
        )
    else:
        details = (
            f"Тип участника: Юридическое лицо\n"
            f"Наименование организации: {reg.get('company_name', '')}\n"
            f"ИНН: {reg.get('inn', '')}\n"
            f"ФИО представителя: {reg.get('representative_name', '')}\n"
            f"Должность: {reg.get('representative_position', '')}\n"
            f"Телефон: {reg.get('phone', '')}\n"
            f"Email: {reg.get('email', '')}\n"
        )

    body = (
        f"Новая оплаченная регистрация на ЭХОС-2026\n"
        f"{'=' * 40}\n"
        f"{details}"
        f"Вид доклада: {REPORT_LABELS.get(reg.get('report_type', ''), reg.get('report_type', ''))}\n"
        f"Тип участия: {PARTICIPATION_LABELS.get(reg.get('participation_type', ''), reg.get('participation_type', ''))}\n"
        f"Проживание в 7Peaks Family Resort: {'Да' if reg.get('hotel') else 'Нет'}\n"
    )

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = ', '.join(NOTIFY_EMAILS)
    msg['Subject'] = 'ЭХОС-2026: новая регистрация (оплата прошла)'
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    return msg


def send_notification_email(reg):
    """Синхронно отправляет письмо с таймаутом. Бросает исключение при ошибке.
    Используется как из фоновой отправки, так и из reconcile.py (доотправка)."""
    msg = build_notification_message(reg)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.sendmail(SMTP_USER, NOTIFY_EMAILS, msg.as_string())


def send_notification(reg, reg_id=None):
    """Отправляет уведомление В ФОНЕ, чтобы зависший SMTP не блокировал ответ
    пользователю и не приводил к WORKER TIMEOUT. По успеху ставит notified=1.
    Промах фиксируется в audit.log — потом досылается reconcile.py."""
    if not SMTP_USER or not SMTP_PASSWORD:
        audit('Email credentials not configured — skipping notification', 'warning')
        return

    name = reg.get('full_name') or reg.get('representative_name') or reg.get('company_name') or '—'

    def _worker():
        try:
            send_notification_email(reg)
            _mark_notified(reg_id)
            audit(f'[MAIL] ✉️ Уведомление отправлено | {name} | {reg.get("email")}')
        except Exception as e:
            audit(
                f'[MAIL-ERR] ❌ Не удалось отправить уведомление | {name} | '
                f'{reg.get("email")} | {e}',
                'error',
            )

    threading.Thread(target=_worker, daemon=True).start()


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Нет данных'}), 400

    entity_type = data.get('entity_type')
    if entity_type not in ('individual', 'legal'):
        return jsonify({'error': 'Неверный тип участника'}), 400

    field_labels = {
        'email': 'Электронная почта',
        'phone': 'Номер телефона',
        'report_type': 'Вид доклада',
        'participation_type': 'Тип участия',
        'full_name': 'ФИО',
        'organization': 'Организация',
        'company_name': 'Наименование организации',
        'inn': 'ИНН',
        'representative_name': 'ФИО представителя',
        'representative_position': 'Должность',
    }

    required_common = ['email', 'phone', 'report_type', 'participation_type']
    required_individual = ['full_name', 'organization']
    required_legal = ['company_name', 'inn', 'representative_name', 'representative_position']

    missing = [f for f in required_common if not data.get(f)]
    if entity_type == 'individual':
        missing += [f for f in required_individual if not data.get(f)]
    else:
        missing += [f for f in required_legal if not data.get(f)]

    if missing:
        labels = ', '.join(field_labels.get(f, f) for f in missing)
        return jsonify({'error': f'Заполните обязательные поля: {labels}'}), 400

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', data.get('email', '')):
        return jsonify({'error': 'Заполните обязательные поля: Электронная почта'}), 400

    if not re.match(r'^\+\d{10,15}$', data.get('phone', '')):
        return jsonify({'error': 'Заполните обязательные поля: Номер телефона'}), 400

    if entity_type == 'individual' and len(data.get('full_name', '').split()) < 2:
        return jsonify({'error': 'Заполните обязательные поля: ФИО'}), 400

    if entity_type == 'legal' and len(data.get('representative_name', '').split()) < 2:
        return jsonify({'error': 'Заполните обязательные поля: ФИО представителя'}), 400

    if data.get('report_type') not in ('oral', 'poster', 'none'):
        return jsonify({'error': 'Неверный вид доклада'}), 400

    if data.get('participation_type') not in ('in_person', 'student', 'accompanying', 'remote'):
        return jsonify({'error': 'Неверный тип участия'}), 400

    if not data.get('oferta'):
        return jsonify({'error': 'Необходимо подтвердить ознакомление с договором оферты'}), 400

    payment_link_id = str(uuid.uuid4())

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''
                INSERT INTO registrations (
                    entity_type, email, phone, report_type, participation_type, hotel,
                    full_name, organization,
                    company_name, inn, representative_name, representative_position,
                    payment_link_id, payment_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (
                entity_type,
                data.get('email'),
                data.get('phone'),
                data.get('report_type'),
                data.get('participation_type'),
                1 if data.get('hotel') else 0,
                data.get('full_name'),
                data.get('organization'),
                data.get('company_name'),
                data.get('inn'),
                data.get('representative_name'),
                data.get('representative_position'),
                payment_link_id,
            ))
            conn.commit()

        # Лог новой регистрации
        name = data.get('full_name') or data.get('representative_name') or data.get('company_name', '—')
        audit(
            f'[REG] Новая регистрация | {name} | {data.get("email")} | '
            f'{PARTICIPATION_LABELS.get(data.get("participation_type",""), data.get("participation_type",""))} | '
            f'ref={payment_link_id[:8]}...'
        )

    except Exception as e:
        app.logger.error(f'DB error: {e}')
        return jsonify({'error': 'Ошибка базы данных'}), 500

    try:
        tochka_resp = create_payment_link(data, payment_link_id)
        app.logger.info(f'Tochka response: {tochka_resp}')
        # Handle both flat and nested response formats
        d = tochka_resp.get('Data', tochka_resp)
        payment_url = d.get('paymentLink') or d.get('paymentUrl')
        operation_id = d.get('operationId')

        if operation_id:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    'UPDATE registrations SET operation_id = ? WHERE payment_link_id = ?',
                    (operation_id, payment_link_id),
                )
                conn.commit()

        if not payment_url:
            app.logger.error(f'No paymentUrl in Tochka response: {tochka_resp}')
            return jsonify({'error': 'Не удалось создать ссылку для оплаты. Попробуйте позже.'}), 500

        return jsonify({'paymentUrl': payment_url}), 200

    except Exception as e:
        app.logger.error(f'Tochka API error: {e}')
        return jsonify({'error': 'Не удалось создать ссылку для оплаты. Попробуйте позже.'}), 500


@app.route('/api/legal_inquiry', methods=['POST'])
def legal_inquiry():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Нет данных'}), 400

    company_name  = (data.get('company_name') or '').strip()
    contact_name  = (data.get('contact_name') or '').strip()
    email         = (data.get('email') or '').strip()
    phone         = (data.get('phone') or '').strip()

    if not company_name:
        return jsonify({'error': 'Укажите наименование организации'}), 400
    if len(contact_name.split()) < 2:
        return jsonify({'error': 'Укажите полное ФИО контактного лица'}), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'error': 'Некорректная электронная почта'}), 400
    if not re.match(r'^\+\d{10,15}$', phone):
        return jsonify({'error': 'Некорректный номер телефона'}), 400

    cnt_in_person    = max(0, int(data.get('cnt_in_person', 0) or 0))
    cnt_student      = max(0, int(data.get('cnt_student', 0) or 0))
    cnt_accompanying = max(0, int(data.get('cnt_accompanying', 0) or 0))
    cnt_remote       = max(0, int(data.get('cnt_remote', 0) or 0))

    body = (
        f"Заявка от юридического лица — ЭХОС-2026\n"
        f"{'=' * 40}\n"
        f"Организация: {company_name}\n"
        f"Контактное лицо: {contact_name}\n"
        f"Email: {email}\n"
        f"Телефон: {phone}\n"
        f"\nПланируемое количество участников:\n"
        f"  Очное участие:           {cnt_in_person}\n"
        f"  Студенты / аспиранты:    {cnt_student}\n"
        f"  Сопровождающие лица:     {cnt_accompanying}\n"
        f"  Заочное участие:         {cnt_remote}\n"
        f"  Итого:                   {cnt_in_person + cnt_student + cnt_accompanying + cnt_remote}\n"
    )

    audit(
        f'[LEGAL] Заявка от юрлица | {company_name} | {contact_name} | {email} | '
        f'очно={cnt_in_person}, студ={cnt_student}, сопр={cnt_accompanying}, заочно={cnt_remote}'
    )

    if SMTP_USER and SMTP_PASSWORD:
        try:
            msg = MIMEMultipart()
            msg['From']    = SMTP_USER
            msg['To']      = ', '.join(NOTIFY_EMAILS)
            msg['Subject'] = f'ЭХОС-2026: заявка от юрлица — {company_name}'
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
                smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.sendmail(SMTP_USER, NOTIFY_EMAILS, msg.as_string())
        except Exception as e:
            audit(f'[LEGAL-ERR] ❌ Email error (legal_inquiry) | {company_name} | {e}', 'error')
            return jsonify({'error': 'Ошибка при отправке. Попробуйте позже.'}), 500

    return jsonify({'ok': True}), 200


@app.route('/payment/callback')
def payment_callback():
    ref = request.args.get('ref', '')
    result = request.args.get('result', '')

    if not ref:
        return redirect('/participants')

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT * FROM registrations WHERE payment_link_id = ?', (ref,)
        ).fetchone()

    if not row:
        return redirect('/participants?msg=failed')

    current_status = row['payment_status']

    # Идемпотентность: уже подтверждённая регистрация не обрабатывается повторно.
    # Защищает от двойных писем при повторном вызове callback (браузер, Точка, refresh).
    if current_status == 'approved':
        return redirect('/participants?msg=success')

    if result == 'success':
        operation_id = row['operation_id']

        if not operation_id:
            # operationId не был получен от Точки — верифицировать невозможно.
            # Помечаем как pending_manual; организаторы сверяются вручную через ЛК Точки.
            audit(f'[PENDING] ⚠️ Callback success без operation_id | ref={ref[:8]}...', 'warning')
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "UPDATE registrations SET payment_status = 'pending_manual' WHERE payment_link_id = ?",
                    (ref,),
                )
                conn.commit()
            return redirect('/participants?msg=pending')

        confirmed = False
        status = None
        try:
            op = verify_payment(operation_id)
            status = op.get('status')
            confirmed = (status == 'APPROVED')
        except Exception as e:
            # Верификация не удалась — fail-closed: не подтверждаем оплату.
            # Организаторы сверяются вручную.
            audit(f'[PENDING] ⚠️ Ошибка верификации, ручная сверка | ref={ref[:8]}... | {e}', 'error')
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "UPDATE registrations SET payment_status = 'pending_manual' WHERE payment_link_id = ?",
                    (ref,),
                )
                conn.commit()
            return redirect('/participants?msg=pending')

        if confirmed:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "UPDATE registrations SET payment_status = 'approved' WHERE payment_link_id = ?",
                    (ref,),
                )
                conn.commit()
            name = row['full_name'] or row['representative_name'] or row['company_name'] or '—'
            amount = PARTICIPATION_AMOUNTS.get(row['participation_type'], 0)
            audit(
                f'[PAID] ✅ Оплата подтверждена | {name} | {row["email"]} | '
                f'{PARTICIPATION_LABELS.get(row["participation_type"], row["participation_type"])} | '
                f'{amount} руб | ref={ref[:8]}...'
            )
            # Отправка письма — в фоне (не блокирует редирект и не валит воркер).
            send_notification(dict(row), reg_id=row['id'])
            return redirect('/participants?msg=success')

        audit(
            f'[FAIL] ❌ Оплата не прошла | ref={ref[:8]}... | статус Точки: {status!r}',
            'warning',
        )
        return redirect('/participants?msg=failed')

    # result != 'success': помечаем как failed.
    # WHERE исключает регрессию статуса: approved не может откатиться в failed
    # (уже перехвачено выше, но WHERE — дополнительный барьер на уровне БД).
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE registrations SET payment_status = 'failed' "
            "WHERE payment_link_id = ? AND payment_status NOT IN ('approved', 'pending_manual')",
            (ref,),
        )
        conn.commit()
    audit(f'[FAIL] ❌ Платёж отменён/не прошёл | ref={ref[:8]}...', 'warning')
    return redirect('/participants?msg=failed')


@app.route('/')
def mainp(name=None):
    return render_template('00index.html', name=name)


@app.route('/about')
def about(name=None):
    return render_template('about.html', name=name)


@app.route('/participants')
def participants(name=None):
    msg = request.args.get('msg', '')
    return render_template('participants.html', name=name, msg=msg)


@app.route('/oferta')
def oferta():
    return render_template('oferta.html')


init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0')
