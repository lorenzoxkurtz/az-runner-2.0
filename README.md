# RedeAZ Runner

Playwright automation for a RedeAZ study flow.

## What It Does

- Opens RedeAZ and logs in through LEX.
- Opens the configured class and the `Atividades` area.
- Moves through subjects in order, five answer fires per subject.
- Waits for `Objetivos de aprendizagem` before starting each fire.
- Opens `Atividades AZ`, `AZ Check`, and `Cartao-resposta`.
- Fills the answer card from the built-in answer queue or `REDEAZ_ANSWER_SETS`.
- Waits for you to press `z` before submitting.
- Stops cleanly if you press `e`.
- Keeps the browser open after completion or errors for inspection.

## Setup

```powershell
python -m pip install -r requirements.txt
playwright install chromium
```

Create `.env` in this folder:

```env
REDEAZ_USERNAME=your-login
REDEAZ_PASSWORD=your-password
REDEAZ_CLASS_HINT=ENSINO MEDIO - 1A SERIE
```

Optional answer override:

```env
REDEAZ_ANSWER_SETS=AAAAAAAAAA,BBBBBBBBBB,CCCCCCCCCC
```

## Run

```powershell
python az_runner_2_0.py
```

## Controls

- Press `z` to submit after a card is filled.
- Press `e` to stop the runner.

## Public Repo Note

Do not publish `.env`. It is ignored by `.gitignore` because it contains credentials.
