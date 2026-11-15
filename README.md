# DocBooker

DocBooker is a classroom chatbot for **Northshore Demo Hospital**, a fictional hospital. It books, finds, reschedules, and cancels **simulated** appointments. It does not give medical advice, it does not store real medical records, and it is not a production or HIPAA system.

The conversation is a fixed state machine with keyword intent matching. It does not call a language model. A separate `botpress/` folder explains how to rebuild the same flows in Botpress. Nothing in this project has been imported into a Botpress account.

## What you need

- Windows PowerShell, or a macOS/Linux terminal
- Python 3.11 or newer (this project was built with Python 3.12)
- No API key

## Windows PowerShell

Run these commands on your Windows computer, in Cursor's PowerShell terminal, from the `DocBooker` folder:

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

`tzdata` is in that install because Windows Python does not include the `America/New_York` timezone data.

Then open http://127.0.0.1:5000/ in a browser. The app listens only on `127.0.0.1`. Debug mode is off.

To reset the synthetic database, stop the app with Ctrl+C and run this in the same PowerShell window, still in the `DocBooker` folder:

```powershell
python reset_demo.py
```

There is no web address that resets the database.

To run the tests, in the same folder with the virtual environment active:

```powershell
python -m pytest
```

## Select the interpreter in Cursor

1. Press Ctrl+Shift+P.
2. Choose **Python: Select Interpreter**.
3. Pick `.venv\Scripts\python.exe` inside this `DocBooker` folder.

If that interpreter is not listed, choose **Enter interpreter path** and select that file.

## macOS or Linux

Run these commands in Terminal, from the `DocBooker` folder. Do not run them in the Windows PowerShell session above.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python run.py
```

Open http://127.0.0.1:5000/. Reset and tests:

```bash
python reset_demo.py
python -m pytest
```

In Cursor on macOS or Linux, select `.venv/bin/python` as the interpreter.

## Copy on the j3gdigital server

The same project is also at `/var/www/docbooker` on `j3gdigital-web` (`192.168.120.102`). Debug mode is off. For the class backup, that process listens on `192.168.120.102:8095` so Nginx Proxy Manager on the LAN can reach it. `FLASK_HOST` stays `127.0.0.1` on a laptop.

On November 15, 2026, these public checks returned success:

```powershell
curl.exe -sS https://j3gdigital.com/docbooker/health
```

Result: `{"service":"docbooker","status":"ok"}`. `https://j3gdigital.com/docbooker/` returned the DocBooker page, and the CSS and script returned 200. `https://j3gdigital.com/week11/` still returned 200. In the browser, Hospital information and then Hours returned the fictional reception hours.

Open that address in class if localhost is unavailable. It is the same DocBooker, not a second hospital. The Botpress edition is the same assistant and is not a separate site on this domain. Do not point Botpress Cloud at this address.

## Architecture

The browser talks to Flask. Flask keeps a random session id and a CSRF token in an HttpOnly cookie. The conversation state (department, doctor, selected time, and so on) is stored in SQLite on the server, keyed by that session id. Management codes are shown once and stored only as a salted hash. The page script does not use `localStorage` or `sessionStorage`.

Booking, rescheduling, and cancellation run inside `BEGIN IMMEDIATE` transactions. An active booking holds its slot through a partial unique index, so two confirms cannot keep the same time. Cancelling sets the status to `cancelled` and leaves the slot free. A cancelled booking cannot be managed again.

Dates and times use `America/New_York`. Seeded slots are generated from the current date for the next 14 days. Sunday is closed. Saturday has a shorter list of times.

Intent matching lives in `app/nlp.py`. Emergency and medical phrase lists live in `app/safety.py`. Hospital answers come only from `data/hospital_knowledge.md`.

## Safety limits

Before normal routing, the bot checks a short list of explicit emergency phrases in `app/safety.py` (for example chest pain, heart attack, stroke, trouble breathing, suicidal statements, severe bleeding, and 911). A match stops the booking flow and tells the person to call 911. That list is not clinical triage. Other wording may not match.

Other medical questions get a refusal. The bot does not diagnose or suggest treatment. It does not ask for symptoms, age, date of birth, Social Security number, or insurance.

## Environment

`.env.example` has empty values. If `SECRET_KEY` is empty, the app writes `instance/secret_key` on first launch. Do not commit `.env` or `instance/`.

| Variable | Role |
| --- | --- |
| `SECRET_KEY` | Cookie signing key |
| `DATABASE_PATH` | SQLite file. Default is `instance/docbooker.db` |
| `FLASK_PORT` | Local port. Default is 5000 |
| `FLASK_HOST` | Bind address. Default is `127.0.0.1`. Set a LAN address only for a reverse proxy on another machine |
| `URL_PREFIX` | Optional path prefix when a reverse proxy mounts the app, such as `/docbooker` |
| `COOKIE_SECURE` | Set to `1` only on HTTPS |

If SQLite reports a disk error because the project folder is on a network share, set `DATABASE_PATH` to a local file, for example `$env:LOCALAPPDATA\DocBooker\docbooker.db`.
