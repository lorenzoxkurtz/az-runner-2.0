import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOTENV_PATH = ROOT / ".env"
LOCAL_PKG_DIR = ROOT / ".pkg"
LOCAL_BROWSERS_DIR = ROOT / ".playwright-browsers"

BASE_URL = "https://app.redeaz.com.br/"
DEFAULT_CLASS_TEXT = "ENSINO MEDIO - 1A SERIE - ("
# Default answer queue. Each string is one AZ Check fire.
DEFAULT_ANSWER_SETS = [
    "CDACCEBCCB",
    "CDDCDDCACE",
    "AEAEEDCBCB",
    "DBEDCBECCA",
    "CDCDBCCBDD",
    "DCDBDAECAE",
    "ABBDDEEDEB",
    "CBBDADDECB",
    "EDCCADCCEB",
    "BDCCCCBCAA",
    "DADCECCCCC",
    "CABBDABCBB",
    "CECEBEDDBC",
    "CCCCDCBDCB",
    "CCCACDEDAC",
    "BEBEEDDDED",
    "CCCCCDBDAD",
    "BCCCDBDCCC",
    "DDDEABAAAD",
    "ADCDACBCEC",
    "CCECABCBDE",
    "EEDAEEDDBB",
    "DCAADCCDDC",
    "DCADDCCBAD",
    "CBCABDCABB",
    "DDBBAEDAED",
    "BCEEBCBEAC",
    "EBADCEDCCE",
    "ECEEDCCCEC",
    "EECDBAACDC",
    "BDDBBABDAD",
    "DCEBADECDB",
    "EAADBDDBCE",
    "AEADBDEDCB",
    "EDDABAACCB",
    "ADDCAACEDC",
    "DBEBEBBDDA",
    "CCDACCDEBB",
    "DDDBADEDCC",
    "ACCBADECBD",
    "CBCDDAADBA",
    "CDBAAAEACC",
    "BAACDEAABB",
    "ADDEACAADB",
    "DABEACEACA",
    "BDECABBAEA",
    "BECBCBABCA",
    "CEACAADDCA",
    "AEEDDCABDE",
    "CAADDADCBD",
    "DBACDCEEEE",
    "DCDCCABBBB",
    "CDEBDDCDBA",
    "EADCBDADEE",
    "AAECDCAACC",
    "BABAEEECCE",
    "ADCDBCCCEC",
    "BCDBDDCDBC",
    "BADADDBDBC",
    "ECCAEBEAEA",
    "BADABEBDBB",
    "ABDBBDBDEB",
    "BBCDECBECC",
    "DCBEBDCDAB",
    "DBCBADADDD",
]
# Subjects are processed in order; every subject gets five fires before moving on.
SUBJECTS = [
    "BIOLOGIA",
    "FISICA",
    "QUIMICA",
    "FILOSOFIA",
    "GEOGRAFIA",
    "HISTORIA",
    "SOCIOLOGIA",
    "ARTE",
    "INGLES",
    "LITERATURA",
    "PORTUGUES",
    "MATEMATICA 1",
    "MATEMATICA 2",
]
FIRES_PER_SUBJECT = 5

if LOCAL_PKG_DIR.exists():
    sys.path.insert(0, str(LOCAL_PKG_DIR))

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(LOCAL_BROWSERS_DIR))

from playwright.sync_api import Error, Page, Playwright, sync_playwright


class KillSwitch(Exception):
    # Raised when you press "e" in the browser to stop the run.
    pass


# Load local .env values without needing python-dotenv.
def load_dotenv() -> None:
    if not DOTENV_PATH.exists():
        return

    for raw_line in DOTENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Read required secrets/config from the environment.
def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name} in {DOTENV_PATH.name}")
    return value


# Allow REDEAZ_ANSWER_SETS to override the built-in queue.
def parse_answer_sets(value: str) -> list[str]:
    if not value.strip():
        return DEFAULT_ANSWER_SETS

    answer_sets = [
        item.strip()
        for item in value.replace(";", ",").split(",")
        if item.strip()
    ]
    return answer_sets or DEFAULT_ANSWER_SETS


# Warn before the run if any answer set is not the expected 10 letters.
def warn_about_answer_sets(answer_sets: list[str]) -> None:
    for index, answers in enumerate(answer_sets, start=1):
        cleaned_answers = "".join(char.upper() for char in answers if char.isalpha())
        if len(cleaned_answers) != 10:
            print(
                f"Warning: answer set {index} has {len(cleaned_answers)} letters: {cleaned_answers}",
                flush=True,
            )


# Install the "press e to stop" listener in the current and future page loads.
def install_kill_switch(page: Page) -> None:
    script = """
        () => {
            window.__codexKillSwitchPressed = window.__codexKillSwitchPressed || false;

            if (window.__codexKillSwitchHandler) {
                document.removeEventListener("keydown", window.__codexKillSwitchHandler, true);
            }

            window.__codexKillSwitchHandler = (event) => {
                if ((event.key || "").toLowerCase() === "e") {
                    window.__codexKillSwitchPressed = true;
                }
            };

            document.addEventListener("keydown", window.__codexKillSwitchHandler, true);
        }
        """
    page.add_init_script(script)
    page.evaluate(script)
    print("Kill switch armed: press e to stop the runner.", flush=True)


# Check whether the browser-side kill switch has been pressed.
def kill_switch_pressed(page: Page) -> bool:
    try:
        return bool(page.evaluate("() => window.__codexKillSwitchPressed === true"))
    except Error:
        return True


# Stop immediately if the kill switch is active.
def check_kill_switch(page: Page) -> None:
    if kill_switch_pressed(page):
        raise KillSwitch("Kill switch pressed")


# Poll a browser condition while still allowing the kill switch to interrupt.
def wait_for_condition_or_kill(page: Page, expression: str, arg=None, timeout: int = 0) -> None:
    start = time.monotonic()
    while True:
        check_kill_switch(page)
        if arg is None:
            if page.evaluate(expression):
                return
        elif page.evaluate(expression, arg):
            return

        if timeout and (time.monotonic() - start) * 1000 >= timeout:
            raise TimeoutError("Timed out waiting for page condition")

        page.wait_for_timeout(250)


# Enter the student login flow from the public landing page.
def click_student_login(page: Page) -> None:
    page.get_by_role("link", name="Logo HUB Entrar com a LEX").click()
    page.locator("a").filter(has_text="AlunoAcesse com login e senha").click()


# Fill credentials and submit the login form.
def login(page: Page, username: str, password: str) -> None:
    page.get_by_role("textbox", name="Digite seu login/e-mail*").fill(username)
    page.get_by_role("textbox", name="Digite sua senha*").fill(password)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_load_state("networkidle")


# Click visible text using accent-insensitive matching as a fallback.
def click_normalized_text(page: Page, text: str) -> None:
    target = text.lower()
    page.locator("a, button, [role='button'], div, span, p, h1, h2, h3, h4").evaluate_all(
        """
        (elements, target) => {
            const normalize = (value) =>
                (value || "")
                    .normalize("NFD")
                    .replace(/[\\u0300-\\u036f]/g, "")
                    .replace(/\\u00aa/g, "a")
                    .replace(/\\u00ba/g, "o")
                    .replace(/[^\\p{L}\\p{N}]+/gu, "")
                    .toLowerCase();

            const wanted = normalize(target);
            const isVisible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
            };

            const match = elements.find((element) => {
                const value = normalize(element.innerText || element.textContent || "");
                return isVisible(element) && value.includes(wanted);
            });

            if (!match) {
                throw new Error(`Could not find visible text: ${target}`);
            }

            match.click();
        }
        """,
        target,
    )


# Open the class and then the Atividades section.
def open_activities(page: Page, class_text: str) -> None:
    try:
        page.get_by_text("ENSINO MEDIO - 1A SERIE - (").click(timeout=5000)
    except Exception:
        candidates = [
            class_text,
            DEFAULT_CLASS_TEXT,
            "ENSINO MEDIO - 1A SERIE",
            "ENSINO MEDIO - 1A SERIE",
        ]

        for candidate in candidates:
            try:
                page.get_by_text(candidate).first.click(timeout=5000)
                break
            except Exception:
                pass
        else:
            click_normalized_text(page, "ENSINO MEDIO 1A SERIE")

    page.get_by_role("button", name="Atividades").click()


# Select the current subject from the subject list.
def open_subject(page: Page, subject: str) -> None:
    print(f"Opening subject {subject}.", flush=True)
    try:
        page.get_by_text(subject, exact=True).click(timeout=5000)
    except Exception:
        click_normalized_text(page, subject)
    page.wait_for_timeout(1000)


# Return from a subject back to the subject list.
def go_back_to_subjects(page: Page) -> None:
    print("Returning to subject list.", flush=True)
    page.get_by_role("main").locator("button").click()
    page.wait_for_timeout(1000)


# Open Cartao-resposta; the double click handles a flaky tab state.
def open_answer_card(page: Page, trigger_number: int, total_triggers: int) -> None:
    print(
        f"Opening Cartao-resposta for trigger {trigger_number}/{total_triggers}.",
        flush=True,
    )
    def click_cartao_resposta() -> None:
        try:
            page.get_by_role("tab", name="Cartao-resposta").click(timeout=5000)
        except Exception:
            try:
                page.get_by_text("Cartao-resposta").click(timeout=5000)
            except Exception:
                click_normalized_text(page, "cartao resposta")

    check_kill_switch(page)
    click_cartao_resposta()
    page.wait_for_timeout(350)
    check_kill_switch(page)
    click_cartao_resposta()
    page.wait_for_timeout(1000)


# Treat "Objetivos de aprendizagem" as the signal that a chapter is loaded.
def wait_for_learning_objectives(page: Page, trigger_number: int, total_triggers: int) -> None:
    print(
        f"Standing by for chapter trigger {trigger_number}/{total_triggers}: Objetivos de aprendizagem.",
        flush=True,
    )
    wait_for_condition_or_kill(
        page,
        """
        () => {
            const text = (document.body.innerText || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .toLowerCase();

            return text.includes("objetivos de aprendizagem");
        }
        """,
    )
    page.wait_for_timeout(500)


# From a chapter page, open Atividades AZ and then AZ Check.
def open_az_check_from_chapter(page: Page, trigger_number: int, total_triggers: int) -> None:
    print(
        f"Opening AZ Check for trigger {trigger_number}/{total_triggers}.",
        flush=True,
    )
    try:
        page.get_by_role("button", name="Atividades AZ 6 Atividades").click(timeout=5000)
    except Exception:
        click_normalized_text(page, "atividades az 6 atividades")

    check_kill_switch(page)
    page.get_by_text("AZ Check").click()
    try:
        click_normalized_text(page, "comecar")
    except Exception:
        pass
    page.wait_for_timeout(1000)


# Detect already-finished result pages so the runner can skip them.
def has_nota_geral(page: Page) -> bool:
    return page.evaluate(
        """
        () => {
            const text = (document.body.innerText || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .toLowerCase();

            return text.includes("nota geral");
        }
        """
    )


# Snapshot the current answer card/page to avoid filling the same card twice.
def answer_card_fingerprint(page: Page) -> str:
    return page.evaluate(
        """
        () => {
            const text = (document.body.innerText || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();

            return `${location.href}::${text}`;
        }
        """
    )


# Wait until navigation changes the answer card away from the previous one.
def wait_for_new_answer_card(page: Page, previous_fingerprint: str, trigger_number: int) -> None:
    print(
        f"Trigger {trigger_number} is armed, but waiting for a different answer card.",
        flush=True,
    )
    wait_for_condition_or_kill(
        page,
        """
        (previousFingerprint) => {
            const text = (document.body.innerText || "")
                .normalize("NFD")
                .replace(/[\\u0300-\\u036f]/g, "")
                .replace(/\\s+/g, " ")
                .trim()
                .toLowerCase();

            const currentFingerprint = `${location.href}::${text}`;
            return currentFingerprint !== previousFingerprint;
        }
        """,
        arg=previous_fingerprint,
    )
    page.wait_for_timeout(1000)


# Wait until the visible answer grid has enough question rows.
def wait_for_answer_rows(page: Page, expected_rows: int) -> None:
    wait_for_condition_or_kill(
        page,
        """
        (expectedRows) => {
            const isVisible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return (
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            };

            const makeRows = (elements) => {
                const rows = [];

                for (const element of elements) {
                    if (!isVisible(element)) {
                        continue;
                    }

                    const rect = element.getBoundingClientRect();
                    const centerY = rect.top + rect.height / 2;
                    let row = rows.find((candidate) => Math.abs(candidate.centerY - centerY) < 18);

                    if (!row) {
                        row = {centerY, count: 0};
                        rows.push(row);
                    }

                    row.count += 1;
                    row.centerY = (row.centerY + centerY) / 2;
                }

                return rows.filter((row) => row.count >= 2).length;
            };

            const buttonRows = makeRows(Array.from(document.querySelectorAll('[id^="application_answer_button_"]')));
            const radioRows = makeRows(Array.from(document.querySelectorAll('input[type="radio"]')));
            return Math.max(buttonRows, radioRows) >= expectedRows;
        }
        """,
        arg=expected_rows,
        timeout=15000,
    )


# Convert answer letters into zero-based option columns.
def answer_button_number(letter: str) -> int:
    normalized = letter.strip().lower()
    if normalized not in "abcde":
        raise ValueError(f"Invalid answer letter: {letter}")
    return "abcde".index(normalized) + 1


# Click one answer by visual row and column, independent of messy RedeAZ selectors.
def click_answer(page: Page, zero_based_question_index: int, letter: str) -> None:
    option_index = answer_button_number(letter) - 1
    clicked = page.evaluate(
        """
        ({questionIndex, optionIndex}) => {
            const isVisible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return (
                    style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            };

            const clickElement = (element) => {
                if (!element) {
                    return false;
                }

                const clickTarget =
                    element.closest("label") ||
                    element.closest('[role="radio"]') ||
                    element.parentElement ||
                    element;

                clickTarget.scrollIntoView({block: "center", inline: "center"});
                clickTarget.click();
                element.dispatchEvent(new MouseEvent("click", {bubbles: true, cancelable: true}));
                element.dispatchEvent(new Event("change", {bubbles: true}));
                return true;
            };

            const makeRows = (elements) => {
                const rows = [];

                for (const element of elements) {
                    if (!isVisible(element)) {
                        continue;
                    }

                    const rect = element.getBoundingClientRect();
                    const centerY = rect.top + rect.height / 2;
                    let row = rows.find((candidate) => Math.abs(candidate.centerY - centerY) < 18);

                    if (!row) {
                        row = {centerY, options: []};
                        rows.push(row);
                    }

                    row.options.push({element, rect});
                    row.centerY = (row.centerY + centerY) / 2;
                }

                return rows
                    .filter((row) => row.options.length >= 2)
                    .sort((a, b) => a.centerY - b.centerY)
                    .map((row) =>
                        row.options
                            .sort((a, b) => a.rect.left - b.rect.left)
                            .map((option) => option.element)
                    );
            };

            const appButtons = Array.from(document.querySelectorAll('[id^="application_answer_button_"]'));
            let rows = makeRows(appButtons);

            if (!rows[questionIndex] || !rows[questionIndex][optionIndex]) {
                const inputs = Array.from(document.querySelectorAll('input[type="radio"]'));
                rows = makeRows(inputs);
            }

            if (clickElement(rows[questionIndex]?.[optionIndex])) {
                return true;
            }

            return false;
        }
        """,
        {"questionIndex": zero_based_question_index, "optionIndex": option_index},
    )
    if not clicked:
        raise RuntimeError(
            f"Could not find question {zero_based_question_index + 1} answer {letter.upper()}"
        )


# Fill one answer string into the current Cartao-resposta grid.
def fill_answers(page: Page, answers: str, trigger_number: int) -> None:
    cleaned_answers = "".join(char.lower() for char in answers if char.isalpha())
    if not cleaned_answers:
        raise ValueError("No answers were provided.")

    wait_for_answer_rows(page, len(cleaned_answers))

    for index, letter in enumerate(cleaned_answers):
        check_kill_switch(page)
        click_answer(page, index, letter)
        page.wait_for_timeout(100)

    print(
        f"Trigger {trigger_number} filled {cleaned_answers.upper()}. "
        "Ready to submit.",
        flush=True,
    )


# Wait for "z", then submit and optionally confirm dialogs.
def submit_answers(page: Page, trigger_number: int) -> None:
    print(f"Trigger {trigger_number} ready. Press z to submit.", flush=True)
    page.evaluate(
        """
        () => {
            window.__submitKeyPressed = false;

            if (window.__submitKeyHandler) {
                document.removeEventListener("keydown", window.__submitKeyHandler, true);
            }

            window.__submitKeyHandler = (event) => {
                if ((event.key || "").toLowerCase() === "z") {
                    window.__submitKeyPressed = true;
                    document.removeEventListener("keydown", window.__submitKeyHandler, true);
                }
            };

            document.addEventListener("keydown", window.__submitKeyHandler, true);
        }
        """
    )
    wait_for_condition_or_kill(page, "() => window.__submitKeyPressed === true")
    print(f"Submitting trigger {trigger_number}.", flush=True)
    check_kill_switch(page)
    page.get_by_role("button").first.wait_for(state="visible", timeout=15000)
    page.get_by_role("button").first.click()
    page.wait_for_timeout(500)
    check_kill_switch(page)
    try:
        page.locator("span").filter(has_text="Sim").click(timeout=2500)
        page.wait_for_timeout(500)
    except Exception:
        pass
    page.locator("button").nth(4).click()
    page.wait_for_timeout(1000)


# Keep the browser alive after completion or errors for inspection.
def keep_browser_open(page: Page) -> None:
    print("Browser will stay open. Close the browser window when you are done.", flush=True)
    while not page.is_closed():
        try:
            page.wait_for_timeout(1000)
        except Error:
            break


# Main orchestration: login, iterate subjects, fill answers, submit.
def run(playwright: Playwright) -> None:
    load_dotenv()

    username = require_env("REDEAZ_USERNAME")
    password = require_env("REDEAZ_PASSWORD")
    class_text = os.getenv("REDEAZ_CLASS_HINT", DEFAULT_CLASS_TEXT).strip()
    answer_sets = parse_answer_sets(os.getenv("REDEAZ_ANSWER_SETS", ""))
    warn_about_answer_sets(answer_sets)

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(30000)
    install_kill_switch(page)

    try:
        page.goto(BASE_URL)
        check_kill_switch(page)
        click_student_login(page)
        login(page, username, password)
        open_activities(page, class_text)
        open_subject(page, SUBJECTS[0])

        previous_fingerprint = ""
        current_subject_index = 0

        for index, answers in enumerate(answer_sets, start=1):
            target_subject_index = (index - 1) // FIRES_PER_SUBJECT
            if target_subject_index >= len(SUBJECTS):
                raise RuntimeError(f"No subject configured for trigger {index}")
            check_kill_switch(page)
            if target_subject_index != current_subject_index:
                go_back_to_subjects(page)
                open_subject(page, SUBJECTS[target_subject_index])
                current_subject_index = target_subject_index
                previous_fingerprint = ""
            if previous_fingerprint:
                wait_for_new_answer_card(page, previous_fingerprint, index)
            wait_for_learning_objectives(page, index, len(answer_sets))
            open_az_check_from_chapter(page, index, len(answer_sets))
            open_answer_card(page, index, len(answer_sets))
            if has_nota_geral(page):
                print(
                    f"Trigger {index} found Nota Geral; skipping {answers}.",
                    flush=True,
                )
                previous_fingerprint = answer_card_fingerprint(page)
                continue
            fill_answers(page, answers, index)
            submit_answers(page, index)
            previous_fingerprint = answer_card_fingerprint(page)
    except KillSwitch as exc:
        print(f"Runner stopped: {exc}", flush=True)
    except Exception as exc:
        print(f"Runner stopped on error: {exc}", flush=True)
    finally:
        keep_browser_open(page)


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
