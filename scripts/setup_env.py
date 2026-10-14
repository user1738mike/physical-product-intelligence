"""Create development credentials without overwriting an existing .env (stdlib only)."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def setup_env(root=ROOT):
    destination = root / ".env"
    if destination.exists():
        print("Existing .env preserved; no credentials changed.")
        return False

    template = (root / ".env.example").read_text(encoding="utf-8")
    replacements = {
        "POSTGRES_PASSWORD=replace-with-local-password": f"POSTGRES_PASSWORD={secrets.token_hex(32)}",
        "DJANGO_SECRET_KEY=replace-with-local-development-key": (
            f"DJANGO_SECRET_KEY={secrets.token_hex(32)}"
        ),
    }
    for placeholder, replacement in replacements.items():
        if template.splitlines().count(placeholder) != 1:
            raise ValueError(
                "Expected exactly one credential placeholder in .env.example"
            )
        template = template.replace(placeholder, replacement)

    # Exclusive creation also protects against another setup process creating the file.
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as output:
            output.write(template)
    except FileExistsError:
        print("Existing .env preserved; no credentials changed.")
        return False
    print(
        "Created local .env with generated development credentials. Values are not displayed."
    )
    return True


if __name__ == "__main__":
    setup_env()
