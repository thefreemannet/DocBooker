# Test results

These are the checks that were actually run on November 15, 2026. Botpress emulator paths in `botpress/test-conversations.md` were not run. Those files are scripts only.

## Automated tests

On this Windows computer, in Cursor's PowerShell, from the `DocBooker` folder, after `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result: `18 passed in 8.14s`.

A later check, after the public path was added, created the app with `URL_PREFIX=/docbooker` and requested `/docbooker/health` and `/docbooker/`. Both returned 200. That check is separate from the 18-test run above.

An earlier run failed during collection because Windows Python had no `America/New_York` data (`ZoneInfoNotFoundError`). `tzdata` was added to `requirements.txt`, installed, and the command above was run again. That second run is the passing result.

The 18 tests cover:

1. A confirmed booking stores a reference and only a hash of the management code.
2. Cancel at the review inserts no booking.
3. Two reviews of the same slot cannot both confirm, and two concurrent database inserts of one slot produce one booking.
4. A nonsense date, a past date, the word "morning", and a past slot are rejected.
5. "Show me cardiologists" returns only the cardiology doctors.
6. Rescheduling onto a slot taken before confirm leaves the original booking in place. A later confirm onto an open slot moves it.
7. Cancel does not free the slot until the explicit confirm. After that, the old codes no longer open it.
8. A wrong management code does not reveal the fictional patient name. A cancelled booking gets the same generic miss.
9. Two browser sessions do not share conversation state.
10. "I have chest pain" during booking returns the 911 message and saves nothing.
11. "What medicine should I take for a fever?" gets the medical-advice refusal and no drug name or dose.
12. "purple elephant" gets the fallback and the five menu buttons.
13. A booking is still in the database after a new application instance opens the same file.
14. A chat post without the CSRF token returns 403. Confirm from the main menu inserts nothing. A non-JSON post returns 400. There is no `/api/reset` route.

Also covered: the sample phrases "I want to book a doctor", "Can I change my appointment?", "Cancel my booking", and "What are your hours?"; an insurance question is refused; restart during a review asks before discarding and saves nothing; the page script does not use browser storage; a strange patient string is stored as text and does not drop the table.

## Local app

From the `DocBooker` folder:

```powershell
.\.venv\Scripts\python.exe run.py
```

The process printed `Running on http://127.0.0.1:5000` with debug mode off.

```powershell
curl.exe -sS http://127.0.0.1:5000/health
```

Result: `{"service":"docbooker","status":"ok"}`.

```powershell
curl.exe -sS http://127.0.0.1:5000/api/bootstrap
```

Result: greeting for Northshore Demo Hospital, the statement that it cannot give medical advice, and the five menu buttons. A fresh session gets that greeting. The CSRF token from that response is not copied here.

## Browser

In the Cursor browser, at `http://127.0.0.1:5000/`, on a desktop-width window and again at a 390 by 844 phone size:

- The demo notice stayed visible.
- Help, Restart, the message box, and Send stayed on screen. On the phone, the quick replies wrap and the message box stays at the bottom.
- Book an appointment, consent, Cardiology, Dr. Helen Cho, Mon, Nov 16, and 9:00 AM were clicked.
- Jamie Rivera and 555-010-0142 were typed and sent.
- The review showed Cardiology, Dr. Helen Cho, Monday, November 16, 2026, 9:00 AM, and America/New_York.
- Confirm showed "Demo appointment saved", a booking reference (`NS-5CBFDB`), and a separate management code.
- Typing "What are your hours?" returned the fictional reception hours, including Sunday closed.

## j3gdigital server

On `j3gdigital-web`, after installing the app in `/var/www/docbooker`:

```bash
curl -sS http://127.0.0.1:8095/health
```

That earlier check returned `{"service":"docbooker","status":"ok"}` while the process listened on `127.0.0.1:8095`.

The class copy now listens on `192.168.120.102:8095` so Nginx Proxy Manager can reach it. Debug mode is off. On November 15, 2026:

```powershell
curl.exe -sS https://j3gdigital.com/docbooker/health
curl.exe -sS -o NUL -w "%{http_code}" https://j3gdigital.com/docbooker/
curl.exe -sS -o NUL -w "%{http_code}" https://j3gdigital.com/docbooker/static/css/style.css
curl.exe -sS -o NUL -w "%{http_code}" https://j3gdigital.com/docbooker/static/js/chat.js
curl.exe -sS -o NUL -w "%{http_code}" https://j3gdigital.com/week11/
```

Health returned `{"service":"docbooker","status":"ok"}`. The page, stylesheet, and script returned 200. Week 11 still returned 200. A request to `https://j3gdigital.com/docbooker` without the trailing slash returned 302 to `https://j3gdigital.com/docbooker/`.

In the Cursor browser at `https://j3gdigital.com/docbooker/`, the greeting and menu loaded. Hospital information, then Hours, returned the fictional reception hours, including Sunday closed. The message box stayed at the bottom of the desktop window.
